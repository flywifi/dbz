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
LEDGER_DIR = ROOT / ".fetch-cache" / "ledger"
_SIG_KEYS = ("status", "reason", "library", "last_modified", "joined", "entries", "entry_digest",
             "newest_modified", "feed_sha256", "retained_behind", "mirror_lag")

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


def _run_stdout(argv: list[str], timeout: int = 900) -> tuple[int, str]:
    """Full, untruncated stdout. The STIG verdict is one JSON line of ~100 KB; _run keeps only
    the last 4,000 characters of stdout+stderr, which cut that line's head off — the second cause
    (with the multi-line parse) of the July-November blind spot, found by the phase-50 live run."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
        return p.returncode, p.stdout
    except Exception as e:  # noqa: BLE001 — report, never crash the pipeline
        return 1, f"{type(e).__name__}: {e}"


def _last_json_line(out: str):
    """The last line that is a complete JSON object. The phase-21 parser took the very last line
    of an INDENTED document (always '}') and so reported check_failed on every reachable run from
    2026-07-04 until phase 50."""
    for line in reversed((out or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def stage_stig_check(_runner=None) -> dict:
    """Three-signal STIG currency (DISA library quarter, NIST NCP, trackr). Offline-safe:
    every failed signal carries its reason; check_failed only when all three fail."""
    rc, out = (_runner or _run_stdout)([sys.executable, str(ROOT / "tools" / "stig_harvest.py"), "--check", "--json"])
    payload = _last_json_line(out)
    if payload is None:
        payload = {"status": "check_failed",
                   "basis": [f"unparseable stig_harvest output (rc={rc}): {(out or '')[-160:]!r}"], "signals": {}}
    status = payload.get("status", "check_failed")
    signals = {}
    for name, s in sorted((payload.get("signals") or {}).items()):
        n = len(s.get("newer") or s.get("stale") or [])
        signals[name] = {**{k: s[k] for k in _SIG_KEYS if k in s}, "n_newer": n}
        print(f"[check] stig/{name}: {s.get('status')} {s.get('library') or s.get('reason') or ''}"
              + (f" — {n} benchmark(s) newer" if n else ""))
    print(f"[check] stig: {status.upper()} (basis: {', '.join(payload.get('basis') or []) or '-'})"
          + (" — re-harvest: stig_harvest.py --full --retain-absent (library) or --refresh-stale" if status == "drift" else ""))
    return {"stig_status": status, "stig_signals": signals}


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


def _collect_ledgers(ledger_dir: Path | None = None) -> dict:
    """Sum the per-tool fetch ledgers this run wrote (each monitor runs in its own process)."""
    merged = {}
    d = ledger_dir or LEDGER_DIR
    for f in (sorted(d.glob("*.json")) if d.exists() else []):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for host, v in data.items():
            m = merged.setdefault(host, {"requests": 0, "refused": 0, "reasons": []})
            m["requests"] += int(v.get("requests", 0))
            m["refused"] += int(v.get("refused", 0))
            m["reasons"] = sorted(set(m["reasons"]) | set(v.get("reasons", [])))
    return merged


GITHUB_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_TAGS = "https://api.github.com/repos/{repo}/tags"


def _gh_get(url: str):
    if str(ENGINE) not in sys.path:
        sys.path.insert(0, str(ENGINE))
    import fetchkit
    headers = {"User-Agent": "dbz-standards-refresh/1.0", "Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    with fetchkit.polite_urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _latest_release_tag(repo: str) -> tuple:
    """(tag, note) or (None, reason). Releases first. A 404 there means 'this repository publishes
    no releases' (9 of 19 November rows), so the tags API is tried before failing. Still fail-closed:
    no tag from either endpoint -> (None, reason) -> check_failed, never current."""
    try:
        payload = _gh_get(GITHUB_LATEST.format(repo=repo))
        tag = payload.get("tag_name") or payload.get("name")
        return (tag, "latest release") if tag else (None, "no tag_name in release payload")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return None, f"HTTPError:{e.code}"
    except Exception as e:  # noqa: BLE001 — classify, never crash the report
        return None, f"{type(e).__name__}: {getattr(e, 'code', '') or str(e)[:90]}"
    try:
        tags = _gh_get(GITHUB_TAGS.format(repo=repo))
    except Exception as e:  # noqa: BLE001
        return None, f"releases:404 tags:{type(e).__name__}:{getattr(e, 'code', '')}"
    if isinstance(tags, list) and tags and tags[0].get("name"):
        return tags[0]["name"], "no releases; first entry of the tags API"
    return None, "releases:404 tags:none"


def _norm_tag(t) -> str:
    return re.sub(r"(?i)^(scf|v)\s*", "", str(t).strip())


def _classify_release_feed(current_version: str, tag, err, pin=None) -> tuple:
    """current | registry_stale | check_failed. With github_tag_pin set, ONLY equality with the
    pin is current (free-text versions like 'v2.0 (2025)' never match a tag like '2024').
    Without a pin: the boundary-guarded match of phase 45 (a shorter tag never satisfies a longer
    pin). A missing tag fails CLOSED."""
    if tag is None:
        return "check_failed", err
    if pin:
        if _norm_tag(tag) == _norm_tag(pin):
            return "current", f"live tag {tag!r} equals github_tag_pin"
        return "registry_stale", f"live tag {tag!r} != github_tag_pin {pin!r} - verify at the issuer, then re-pin"
    norm = _norm_tag(tag)
    if norm and re.search(r"(?<![\d.])" + re.escape(norm) + r"(?![\d.])", current_version or ""):
        return "current", f"release tag {tag!r} matches"
    return "registry_stale", f"live tag {tag!r} not in current_version {current_version!r}"


def selftest_release_check() -> int:
    """The six phase-45 fixtures plus pin and tags-fallback fixtures (fake governor, no network)."""
    cases = [
        ("SCF 2026.1.1 (2026-04-22)", "2026.2", None, None, "registry_stale"),
        ("SCF 2026.1.1 (2026-04-22)", "SCF 2026.1.1", None, None, "current"),
        ("SCF 2026.1.1 (2026-04-22)", "SCF 2026.1", None, None, "registry_stale"),
        ("SCF 2026.2 (2026-07-08)", "2026.2", None, None, "current"),
        ("v4.1", "v4.1", None, None, "current"),
        ("v4.1", None, "HTTPError:403", None, "check_failed"),
        ("v2.0 (2025)", "2024", None, "2024", "current"),            # owasp-llm-top10 shape
        ("v2.0 (2025)", "2025", None, "2024", "registry_stale"),
        ("ATT&CK v20.0", "v20.0", None, "20.0", "current"),
    ]
    bad = 0
    for cv, tag, err, pin, want in cases:
        got, why = _classify_release_feed(cv, tag, err, pin)
        bad += got != want
        print(f"  [{'ok' if got == want else 'FAIL'}] cv={cv!r} tag={tag!r} pin={pin!r} -> {got}")
    import io as _io
    sys.path.insert(0, str(ENGINE))
    import fetchkit

    class _R(_io.BytesIO):
        status = 200
        headers: dict = {}
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener_for(tags_body):
        def op(req, timeout):
            if req.full_url.endswith("/robots.txt") or "/releases/latest" in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, _io.BytesIO(b""))
            if tags_body is None:
                raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, _io.BytesIO(b""))
            return _R(tags_body)
        return op
    saved = fetchkit._GOV
    for label, body, want in (("404 releases -> tags", b'[{"name": "v1.0"}]', ("v1.0", "current")),
                              ("404 releases, 404 tags", None, (None, "check_failed"))):
        fetchkit._GOV = fetchkit.RateGovernor(state_path=None, opener=opener_for(body), sleeper=lambda s: None,
                                              policies={"_default": {"enforced": {"run_cap": 99, "min_interval_s": 0}}, "hosts": {}})
        tag, note = _latest_release_tag("o/r")
        cls = _classify_release_feed("v1.0", tag, note)[0]
        bad += (tag, cls) != want
        print(f"  [{'ok' if (tag, cls) == want else 'FAIL'}] {label}: tag={tag!r} ({note}) -> {cls}")
    fetchkit._GOV = saved
    total = len(cases) + 2
    print(f"[selftest] release-check: {total - bad}/{total} passed")
    return 1 if bad else 0


def selftest_stig_check() -> int:
    """Prove the STIG verdict cannot go blind again: the parser and the three-signal classifier."""
    sys.path.insert(0, str(ROOT / "tools"))
    import stig_harvest
    one_line = json.dumps({"status": "drift", "basis": ["library", "ncp"], "signals": {
        "library": {"status": "newer", "library": "U_SRG-STIG_Library_October_2026"},
        "ncp": {"status": "newer", "newer": [{"benchmark_id": "X"}]},
        "trackr": {"status": "failed", "reason": "URLError"}}})
    long_line = json.dumps({"status": "drift", "basis": ["trackr"], "signals": {"trackr": {
        "status": "newer", "stale": [{"benchmark_id": f"B{i}", "harvested": "v1r1", "live": "v1r2",
                                      "title": f"T{i}"} for i in range(1500)]}}}) + "\n"
    parse_cases = [
        ("phase-50 one-line drift", "[warn] noise\n" + one_line + "\n", "drift"),
        ("legacy trackr-down line", '[check] trackr unreachable (URLError: x)\n{"status": "check_failed"}\n', "check_failed"),
        ("legacy INDENTED drift (the July-November blind spot)", '{\n "changed_titles": [],\n "status": "drift"\n}', "check_failed"),
        ("traceback", "Traceback (most recent call last):\n  boom\n", "check_failed"),
        ("100 KB one-line payload, untruncated (_run_stdout)", long_line, "drift"),
        ("same payload truncated to 4,000 chars (the old _run)", long_line[-4000:], "check_failed"),
    ]
    bad = 0
    for label, out, want in parse_cases:
        got = stage_stig_check(_runner=lambda argv, out=out: (0, out))["stig_status"]
        bad += got != want
        print(f"  [{'ok' if got == want else 'FAIL'}] parse: {label} -> {got}")
    m = {"status": "newer"}
    sig_cases = [
        ("all three newer", {"library": m, "ncp": m, "trackr": m}, "drift"),
        ("trackr down, DISA+NCP newer", {"library": m, "ncp": m, "trackr": {"status": "failed", "reason": "URLError"}}, "drift"),
        ("all same", {k: {"status": "same"} for k in ("library", "ncp", "trackr")}, "current"),
        ("all down", {k: {"status": "failed", "reason": "timeout"} for k in ("library", "ncp", "trackr")}, "check_failed"),
    ]
    for label, sig, want in sig_cases:
        got = stig_harvest.classify_signals(sig)[0]
        bad += got != want
        print(f"  [{'ok' if got == want else 'FAIL'}] classify: {label} -> {got}")
    print(f"[selftest] stig-check: {len(parse_cases) + len(sig_cases) - bad}/{len(parse_cases) + len(sig_cases)} passed")
    return 1 if bad else 0


def stage_check() -> dict:
    """Run the monitors, then classify every registry feed. github_release feeds get a LIVE
    comparison (against github_tag_pin when set); every other row is labeled stored_status_only.
    The report carries the STIG signals and the per-host fetch ledger of the whole run."""
    if LEDGER_DIR.exists():
        for f in LEDGER_DIR.glob("*.json"):
            f.unlink()
    monitor_rc, monitor_out = _run([sys.executable, str(ENGINE / "framework_monitor.py"), "--dry-run"])
    ann_rc, ann_out = _run([sys.executable, str(ENGINE / "announcement_monitor.py"), "--dry-run"])
    stig_signal = stage_stig_check()
    cci_signal = stage_cci_check()
    horizon_signal = stage_horizon()
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rows = []
    for fid, e in sorted(reg["feeds"].items()):
        if not isinstance(e, dict):
            continue
        status = e.get("artifact_status", "metadata_only")
        cls, reason, signal = status, None, "stored_status_only"
        if e.get("check_strategy") == "github_release" and e.get("github_repo"):
            signal = "github_release_api"
            tag, note = _latest_release_tag(e["github_repo"])
            cls, reason = _classify_release_feed(e.get("current_version", ""), tag, note, e.get("github_tag_pin"))
        elif status == "current" and e.get("auto_fetch") and monitor_rc != 0:
            cls = "check_failed"
        rows.append({"framework_id": fid, "current_version": e.get("current_version"),
                     "artifact_status": status, "auto_fetch": bool(e.get("auto_fetch")),
                     "last_changed": e.get("last_changed"), "last_verified": e.get("last_verified"),
                     "classification": cls, "signal": signal, "reason": reason})
    sys.path.insert(0, str(ENGINE))
    import fetchkit
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    fetchkit.save_ledger("standards_refresh")
    ledger = _collect_ledgers()
    report = {"generated_at": _now(), "monitor_exit": monitor_rc, "announcements_exit": ann_rc,
              "stig_status": stig_signal.get("stig_status"), "stig_signals": stig_signal.get("stig_signals"),
              "cci_status": cci_signal.get("cci_status"), "horizon_overdue": horizon_signal.get("horizon_overdue"),
              "fetch_ledger": ledger, "policy_refusals": sum(v["refused"] for v in ledger.values()),
              "feeds": rows, "summary": {}}
    for r in rows:
        report["summary"][r["classification"]] = report["summary"].get(r["classification"], 0) + 1
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[check] monitor rc={monitor_rc} announcements rc={ann_rc}")
    print(f"[check] {len(rows)} feeds -> {report['summary']}")
    print(f"[check] fetch: {sum(v['requests'] for v in ledger.values())} requests to {len(ledger)} hosts, "
          f"{report['policy_refusals']} refused by host rules")
    for r in rows:
        if r["classification"] == "registry_stale":
            print(f"[check] REGISTRY STALE {r['framework_id']}: {r['reason']} — re-verify at origin and update via registry_io")
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
    ap.add_argument("--selftest-stig-check", action="store_true",
                    help="prove the STIG verdict parser + three-signal classifier (fixtures)")
    args = ap.parse_args()
    if args.selftest_release_check or args.selftest_stig_check:
        rc = 0
        if args.selftest_release_check:
            rc |= selftest_release_check()
        if args.selftest_stig_check:
            rc |= selftest_stig_check()
        return rc
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
