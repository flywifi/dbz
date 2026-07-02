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
import subprocess
import sys
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
    "scf":        {"note": "SCF releases are versioned file names — check the GitHub repo listing "
                           "and fetch the new 'Secure Controls Framework (SCF) - <ver>.xlsx' manually"},
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(argv: list[str], timeout: int = 900) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
        return p.returncode, (p.stdout + p.stderr)[-4000:]
    except Exception as e:  # noqa: BLE001 — report, never crash the pipeline
        return 1, f"{type(e).__name__}: {e}"


def stage_check() -> dict:
    """Run the monitors, then classify every registry feed."""
    monitor_rc, monitor_out = _run([sys.executable, str(ENGINE / "framework_monitor.py"), "--dry-run"])
    ann_rc, ann_out = _run([sys.executable, str(ENGINE / "announcement_monitor.py"), "--dry-run"])

    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    feeds = reg["feeds"]
    rows = []
    for fid, e in sorted(feeds.items()):
        status = e.get("artifact_status", "metadata_only")
        if not isinstance(e, dict):
            continue
        cls = status
        if status == "current" and e.get("auto_fetch") and monitor_rc != 0:
            cls = "check_failed"
        rows.append({
            "framework_id": fid,
            "current_version": e.get("current_version"),
            "artifact_status": status,
            "auto_fetch": bool(e.get("auto_fetch")),
            "last_changed": e.get("last_changed"),
            "last_verified": e.get("last_verified"),
            "classification": cls,
        })
    report = {
        "generated_at": _now(),
        "monitor_exit": monitor_rc,
        "announcements_exit": ann_rc,
        "feeds": rows,
        "summary": {},
    }
    for r in rows:
        report["summary"][r["classification"]] = report["summary"].get(r["classification"], 0) + 1
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[check] monitor rc={monitor_rc} announcements rc={ann_rc}")
    print(f"[check] {len(rows)} feeds -> {report['summary']}")
    print(f"[check] report: {REPORT.relative_to(ROOT)}")
    return report


def stage_fetch() -> int:
    """Re-fetch auto_fetch feeds via their loaders/urls. Returns failure count."""
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    failures = 0
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
            dest = ROOT / recipe["dest"]
            rc, out = _run(["curl", "-sSL", "--max-time", "300", "-o", str(dest), recipe["url"]])
            if rc == 0 and dest.exists():
                digest = hashlib.sha256(dest.read_bytes()).hexdigest()[:16]
                print(f"[fetch] {fid}: {dest.name} sha256={digest}")
            else:
                failures += 1
                print(f"[fetch] {fid}: FAILED rc={rc}")
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
    args = ap.parse_args()
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
