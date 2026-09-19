#!/usr/bin/env python3
"""
standards_refresh.py — one-command standards currency pipeline.

Chains the existing monitors into a four-stage refresh loop so framework drift
is caught mechanically instead of by memory:

  check   framework_monitor + announcement_monitor version/announcement signals,
          then classify every feed_registry entry into a drift report:
            current | registry_stale | artifact_stale | licensed_pinned |
            metadata_only | on_demand | check_failed
  fetch   (--fetch) re-download ONLY feeds whitelisted `auto_fetch: true` in
          feed_registry (free, versioned, machine-readable sources). Records
          sha256; bumps nothing semantic — mapping changes always go through
          a human-reviewed loader phase.
  diff    version transitions observed by `check` are appended to
          framework_changelog.json as human_confirmed=false stubs.
  gate    (--gate) rebuild grc.db + run the deterministic gate battery;
          non-zero exit on any regression.

Offline-safe: network failures degrade to `check_failed` per feed, exit 0
(the report is the deliverable; CI surfaces failures via the drift issue).

Usage:
    python3 tools/standards_refresh.py --check
    python3 tools/standards_refresh.py --check --fetch
    python3 tools/standards_refresh.py --check --fetch --gate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "canonical-sources" / "feed_registry.json"
CHANGELOG = ROOT / "canonical-sources" / "framework_changelog.json"
REPORT = ROOT / "cross-mapping" / "output" / "standards_drift_report.json"
ENGINE = ROOT / "cross-mapping" / "engine"

GATES = [
    [sys.executable, str(ROOT / "tools" / "sync_check.py")],
    [sys.executable, str(ROOT / "tools" / "health_audit.py"), "--scan"],
    [sys.executable, str(ROOT / "cross-mapping" / "tests" / "test_spine.py")],
    [sys.executable, str(ROOT / "cross-mapping" / "tests" / "validate_spine.py")],
    [sys.executable, str(ROOT / "skills" / "health-auditor" / "tests" / "run_golden.py")],
]

# auto-fetchable artifact recipes: feed id fragment -> (loader argv | direct url, dest)
FETCHERS = {
    "kev":        {"loader": [sys.executable, str(ENGINE / "kev_loader.py"), "--format", "summary"]},
    "attack":     {"loader": [sys.executable, str(ENGINE / "attack_stix_loader.py"),
                              "--stix-url",
                              "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json"]},
    "disa-cci":   {"url": "https://dl.dod.cyber.mil/wp-content/uploads/stigs/zip/U_CCI_List.zip",
                   "dest": "canonical-sources/source_data/U_CCI_List.zip",
                   "note": "unzip U_CCI_List.xml into source_data/ after download"},
    "nist-800-53": {"url": "https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
                    "dest": "cross-mapping/output/oscal_v5.2.0_cache.json"},
    "scf":        {"note": "SCF releases are versioned FILE SETS, not just the controls xlsx — fetch "
                           "the FULL repo file set. Since 2026.2 the repo uses kebab-case names: "
                           "'secure-controls-framework-scf-<ver-with-dashes>.xlsx' and a plain "
                           "'errata.txt' at the repo root (older 'Secure Controls Framework (SCF) - "
                           "<ver>.xlsx' names live under Archived Versions/). Also compare the "
                           "Overview & Practitioner Guidebook (versioned independently!), CDPAS/MADSS, "
                           "scrms-pig, and the CAP docs — fetching only the xlsx misses errata and "
                           "doc revisions."},
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(argv: list[str], timeout: int = 900) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
        return p.returncode, (p.stdout + p.stderr)[-4000:]
    except Exception as e:  # noqa: BLE001 — report, never crash the pipeline
        return 1, f"{type(e).__name__}: {e}"


def stage_stig_check() -> dict:
    """Compare the live trackr STIG catalog against the committed artifact.
    Offline-safe: a fetch failure degrades to check_failed, never crashes."""
    rc, out = _run([sys.executable, str(ROOT / "tools" / "stig_harvest.py"), "--check", "--json"])
    try:
        payload = json.loads(out.strip().splitlines()[-1])
    except Exception:
        payload = {"status": "check_failed"}
    status = payload.get("status", "check_failed")
    if status == "drift":
        n = (len(payload.get("new_titles", [])) + len(payload.get("changed_titles", []))
             + len(payload.get("stale_harvested", [])))
        print(f"[check] stig: DRIFT — {n} signals "
              f"({len(payload.get('stale_harvested', []))} harvested benchmarks stale; "
              "run standards_refresh.py --fetch to re-harvest changed titles)")
    elif status == "current":
        print("[check] stig: current — no drift vs the live trackr catalog")
    else:
        print("[check] stig: check_failed (trackr unreachable)")
    return {"stig_status": status}


def stage_cci_check() -> dict:
    """Compare the live CCI-list currency (trackr enum size) against the committed
    snapshot; the authoritative XML version is reported. Offline-safe."""
    rc, out = _run([sys.executable, str(ROOT / "tools" / "cci_harvest.py"), "--check", "--json"])
    try:
        payload = json.loads(out[out.index("{"):])
    except Exception:
        payload = {"status": "check_failed"}
    st = payload.get("status", "check_failed")
    if st == "drift":
        print(f"[check] cci: DRIFT — committed trackr enum {payload.get('committed_trackr_enum')} "
              f"vs live {payload.get('live_trackr_enum')} (run --fetch to re-snapshot)")
    elif st == "current":
        print(f"[check] cci: current — list v{payload.get('committed_cci_list_version')}, "
              f"trackr enum {payload.get('live_trackr_enum')}")
    else:
        print("[check] cci: check_failed (trackr unreachable)")
    return {"cci_status": st}


def stage_horizon() -> dict:
    """Surface the anticipated-updates horizon: overdue/due-review items that must be
    re-investigated so an expected update is never missed. Offline-safe (pure registry
    intelligence, no network)."""
    rc, out = _run([sys.executable, str(ENGINE / "horizon_monitor.py"), "--summary"])
    try:
        counts = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except Exception:
        counts = {}
    overdue = int(counts.get("overdue", 0))
    due_review = int(counts.get("due_review", 0))
    draft = int(counts.get("draft_observed", 0))
    elapsed = int(counts.get("elapsed_open", 0))
    if overdue or due_review or elapsed:
        print(f"[check] horizon: {elapsed} elapsed-but-open + {overdue} overdue + {due_review} "
              f"due-for-review + {draft} draft-observed — run `horizon_monitor.py --overdue` "
              "and re-investigate the source (an elapsed window is a fact, whatever grace says)")
    else:
        print(f"[check] horizon: nothing elapsed/overdue/due ({draft} draft-observed on the horizon)")
    return {"horizon_overdue": overdue, "horizon_due_review": due_review,
            "horizon_elapsed_open": elapsed}


GITHUB_LATEST = "https://api.github.com/repos/{repo}/releases/latest"


def _latest_release_tag(repo: str) -> tuple:
    """(tag, None) from the GitHub releases API, or (None, reason).

    In CI (standards-watch.yml) GITHUB_TOKEN authenticates the call; in a session
    environment the proxy intercepts api.github.com with a structured 403 — the
    caller MUST classify that as check_failed, never as current (the ci_status.py
    error/empty/data discipline). The releases HTML page and releases.atom both
    403 scripted fetches (measured 2026-09-19), so the API is the one signal."""
    headers = {"User-Agent": "dbz-standards-refresh/1.0",
               "Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(GITHUB_LATEST.format(repo=repo), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8"))
        tag = payload.get("tag_name") or payload.get("name")
        return (tag, None) if tag else (None, "no tag_name in release payload")
    except Exception as e:  # noqa: BLE001 — classify, never crash the report
        return None, f"{type(e).__name__}:{getattr(e, 'code', '')}"


def _classify_release_feed(current_version: str, tag, err) -> tuple:
    """current | registry_stale | check_failed for a github_release feed.

    Boundary-guarded match (the count_truth._patterns_for idiom) so a shorter
    live tag ('2026.1') can never satisfy a longer pin ('2026.1.1'); a missing
    tag FAILS CLOSED — the fail-open stored-status default was how SCF 2026.2
    stayed classified 'current' for ten weeks (phase 45, defect T1)."""
    if tag is None:
        return "check_failed", err
    norm = re.sub(r"(?i)^(scf|v)\s*", "", str(tag).strip())
    if norm and re.search(r"(?<![\d.])" + re.escape(norm) + r"(?![\d.])",
                          current_version or ""):
        return "current", f"release tag {tag!r} matches"
    return "registry_stale", f"live tag {tag!r} not in current_version {current_version!r}"


def selftest_release_check() -> int:
    """Prove the release classifier goes RED on a stale pin and CLOSED on no signal.
    The first fixture is the real phase-45 incident verbatim: pin 'SCF 2026.1.1'
    vs live tag '2026.2' (released 2026-07-08), which the stored-status
    classifier called current for ten weeks."""
    cases = [
        ("SCF 2026.1.1 (2026-04-22)", "2026.2", None, "registry_stale"),
        ("SCF 2026.1.1 (2026-04-22)", "SCF 2026.1.1", None, "current"),
        ("SCF 2026.1.1 (2026-04-22)", "SCF 2026.1", None, "registry_stale"),  # boundary guard
        ("SCF 2026.2 (2026-07-08)", "2026.2", None, "current"),
        ("v4.1", "v4.1", None, "current"),
        ("v4.1", None, "HTTPError:403", "check_failed"),  # fail closed, never current
    ]
    bad = 0
    for cv, tag, err, want in cases:
        got, why = _classify_release_feed(cv, tag, err)
        ok = got == want
        bad += 0 if ok else 1
        print(f"  [{'ok' if ok else 'FAIL'}] cv={cv!r} tag={tag!r} -> {got} ({why})")
    print(f"[selftest] release-check: {len(cases) - bad}/{len(cases)} passed")
    return 1 if bad else 0


def stage_check() -> dict:
    """Run the monitors, then classify every registry feed. Feeds with
    check_strategy=github_release get a LIVE version comparison; every other
    row is explicitly labeled stored_status_only so the report never again
    reads a stored status as a live verdict (phase 45, defect T1)."""
    monitor_rc, monitor_out = _run([sys.executable, str(ENGINE / "framework_monitor.py"), "--dry-run"])
    ann_rc, ann_out = _run([sys.executable, str(ENGINE / "announcement_monitor.py"), "--dry-run"])
    stig_signal = stage_stig_check()
    cci_signal = stage_cci_check()
    horizon_signal = stage_horizon()

    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    feeds = reg["feeds"]
    rows = []
    for fid, e in sorted(feeds.items()):
        if not isinstance(e, dict):
            continue
        status = e.get("artifact_status", "metadata_only")
        cls, reason, signal = status, None, "stored_status_only"
        if e.get("check_strategy") == "github_release" and e.get("github_repo"):
            signal = "github_release_api"
            tag, err = _latest_release_tag(e["github_repo"])
            cls, reason = _classify_release_feed(e.get("current_version", ""), tag, err)
        elif status == "current" and e.get("auto_fetch") and monitor_rc != 0:
            cls = "check_failed"
        rows.append({
            "framework_id": fid,
            "current_version": e.get("current_version"),
            "artifact_status": status,
            "auto_fetch": bool(e.get("auto_fetch")),
            "last_changed": e.get("last_changed"),
            "last_verified": e.get("last_verified"),
            "classification": cls,
            "signal": signal,
            "reason": reason,
        })
    report = {
        "generated_at": _now(),
        "monitor_exit": monitor_rc,
        "announcements_exit": ann_rc,
        "stig_status": stig_signal.get("stig_status"),
        "cci_status": cci_signal.get("cci_status"),
        "horizon_overdue": horizon_signal.get("horizon_overdue"),
        "feeds": rows,
        "summary": {},
    }
    for r in rows:
        report["summary"][r["classification"]] = report["summary"].get(r["classification"], 0) + 1
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[check] monitor rc={monitor_rc} announcements rc={ann_rc}")
    print(f"[check] {len(rows)} feeds -> {report['summary']}")
    stale = [r for r in rows if r["classification"] == "registry_stale"]
    for r in stale:
        print(f"[check] REGISTRY STALE {r['framework_id']}: {r['reason']} — "
              "re-verify at origin and update the feed via registry_io")
    print(f"[check] report: {REPORT.relative_to(ROOT)}")
    return report


def stage_stig_fetch() -> int:
    """Re-harvest only the STIG benchmarks that drifted (per-title DISA zip, trackr
    fallback). The multi-hundred-MB library compilation is NOT pulled here — that
    is an explicit operator step (stig_harvest.py --full --from-zip); this stage
    keeps the committed artifact current between quarterly library refreshes."""
    rc, out = _run([sys.executable, str(ROOT / "tools" / "stig_harvest.py"),
                    "--refresh-stale", "--max-delta", "40"], timeout=3600)
    print(f"[fetch] stig refresh-stale rc={rc}")
    if rc != 0:
        print(out[-600:])
    return 1 if rc != 0 else 0


def stage_cci_fetch() -> int:
    """Re-snapshot the CCI corroboration artifacts (acasehs republications + trackr
    enrichment). The authoritative CCI-list XML is refreshed separately (operator
    downloads U_CCI_List.zip; the loader reads it on rebuild)."""
    rc1, _ = _run([sys.executable, str(ROOT / "tools" / "cci_harvest.py"), "--acasehs"])
    rc2, _ = _run([sys.executable, str(ROOT / "tools" / "cci_harvest.py"),
                   "--trackr", "--enrich", "--resume"], timeout=3600)
    print(f"[fetch] cci acasehs rc={rc1} trackr rc={rc2}")
    return (1 if rc1 else 0) + (1 if rc2 else 0)


def stage_fetch() -> int:
    """Re-fetch auto_fetch feeds via their loaders/urls. Returns failure count."""
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    failures = stage_stig_fetch() + stage_cci_fetch()
    for fid, e in sorted(reg["feeds"].items()):
        if not (isinstance(e, dict) and e.get("auto_fetch")):
            continue
        recipe = next((r for frag, r in FETCHERS.items() if frag in fid), None)
        if recipe is None:
            print(f"[fetch] {fid}: auto_fetch set but no recipe — skipped")
            continue
        if "loader" in recipe:
            rc, out = _run(recipe["loader"])
            print(f"[fetch] {fid}: loader rc={rc}")
            if rc != 0:
                failures += 1
                print(out[-500:])
        elif "url" in recipe:
            # fetchkit: per-host pacing + conditional-GET cache. Canonical artifacts
            # must be live — the wayback prong is explicitly disabled here.
            dest = ROOT / recipe["dest"]
            sys.path.insert(0, str(ENGINE))
            import fetchkit
            status, body, meta = fetchkit.resilient_get(
                recipe["url"], allow_wayback=False, timeout=300)
            if meta.get("cache") == "unchanged" and dest.exists():
                print(f"[fetch] {fid}: unchanged (304/sha cache hit)")
            elif status == 200 and body is not None:
                dest.write_bytes(body)
                digest = hashlib.sha256(body).hexdigest()[:16]
                print(f"[fetch] {fid}: {dest.name} sha256={digest} ({meta['source']})")
            else:
                failures += 1
                print(f"[fetch] {fid}: FAILED status={status} trail={meta.get('trail')}")
            fetchkit.save_state()
        if recipe.get("note"):
            print(f"[fetch] {fid}: NOTE — {recipe['note']}")
    return failures


def stage_gate() -> int:
    """Rebuild the DB and run the deterministic gates. Returns failure count."""
    rc, out = _run([sys.executable, str(ENGINE / "build_db.py")], timeout=1800)
    print(f"[gate] build_db rc={rc}")
    if rc != 0:
        print(out[-800:])
        return 1
    failures = 0
    for argv in GATES:
        rc, out = _run(argv)
        name = Path(argv[1]).name
        print(f"[gate] {name} rc={rc}")
        if rc != 0:
            failures += 1
            print(out[-500:])
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="run monitors + write drift report")
    ap.add_argument("--fetch", action="store_true", help="re-fetch auto_fetch artifacts")
    ap.add_argument("--gate", action="store_true", help="rebuild grc.db + run gate battery")
    ap.add_argument("--selftest-release-check", action="store_true",
                    help="prove the github_release classifier fails red/closed (fixtures)")
    args = ap.parse_args()
    if args.selftest_release_check:
        return selftest_release_check()
    if not (args.check or args.fetch or args.gate):
        ap.error("choose at least one of --check / --fetch / --gate")

    failures = 0
    if args.check:
        stage_check()
    if args.fetch:
        failures += stage_fetch()
    if args.gate:
        failures += stage_gate()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
