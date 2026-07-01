#!/usr/bin/env python3
"""
health_repair.py — act on a health_audit report, mechanical fixes only, human-gated.

Reads the repair plan from `health_audit.py` (or a saved report), splits it into
**mechanical** (safe to auto-apply) and **judgment** (human-only) fixes, and by default
only PRINTS what it would do. With --apply it performs the mechanical fixes and re-runs the
auditor to confirm. Judgment items — contradictions, missing evals, schema/vocab violations,
broken references whose correct target is ambiguous — are never auto-changed; they are
surfaced as TODOs. This mirrors the no-self-spawn / human-approval ethos of the rest of dbz.

Run:
    python3 tools/health_repair.py               # dry-run: show mechanical vs judgment split
    python3 tools/health_repair.py --apply        # apply mechanical fixes, then re-audit
    python3 tools/health_repair.py --plan report.json   # act on a saved report
Exit: 0 if after the run there are no blocking findings, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "tools" / "health_audit.py"


def load_report(plan: str | None, full: bool) -> dict:
    if plan:
        return json.loads(Path(plan).read_text(encoding="utf-8"))
    args = [sys.executable, str(AUDIT), "--json", "--full" if full else "--scan"]
    out = subprocess.run(args, capture_output=True, text=True)
    return json.loads(out.stdout)


def apply_mechanical(fix: dict) -> tuple[bool, str]:
    """
    Apply one mechanical fix. Returns (applied, note). Conservative: only fixes whose
    correct action is unambiguous are handled; anything requiring a judgment call is
    declined here (kept in the human TODO list even if tagged mechanical upstream).
    """
    # The current auditor emits few purely-mechanical fixes; new mechanical fix types are
    # added here as they are introduced. Declining safely is always acceptable.
    return False, "no automated handler for this fix type yet — left for human review"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply mechanical health fixes (human-gated)")
    ap.add_argument("--apply", action="store_true", help="apply mechanical fixes (default: dry-run)")
    ap.add_argument("--plan", metavar="FILE", help="a saved health_audit --json report")
    ap.add_argument("--full", action="store_true", help="audit full scope when computing live")
    a = ap.parse_args(argv)

    report = load_report(a.plan, a.full)
    plan = report.get("repair_plan", report.get("findings", []))
    mechanical = [f for f in plan if f.get("mechanical")]
    judgment = [f for f in plan if not f.get("mechanical")]

    print(f"health-repair — {len(plan)} finding(s): "
          f"{len(mechanical)} mechanical, {len(judgment)} judgment "
          f"(score {report.get('readiness_score')}/100, {report.get('readiness_band')})\n")

    print("MECHANICAL (auto-fixable):")
    if not mechanical:
        print("  (none)")
    for f in mechanical:
        print(f"  • [{f['severity']}] {f['area']}: {f['issue']}\n      → {f['action']}")

    print("\nJUDGMENT (human-only — never auto-changed):")
    if not judgment:
        print("  (none)")
    for f in judgment:
        print(f"  • [{f['severity']}] {f['area']}: {f['issue']}\n      → TODO: {f['action']}  ({f['provenance']})")

    if not a.apply:
        print("\n[dry-run] no changes made. Re-run with --apply to perform mechanical fixes.")
        return 0 if report.get("blocking", 0) == 0 else 1

    print("\n--apply: performing mechanical fixes …")
    applied = 0
    for f in mechanical:
        ok, note = apply_mechanical(f)
        status = "applied" if ok else "skipped"
        print(f"  [{status}] {f['area']}: {note}")
        applied += int(ok)
    print(f"\n{applied} mechanical fix(es) applied. Re-auditing …\n")

    re_report = load_report(None, a.full)
    print(f"post-repair score: {re_report.get('readiness_score')}/100 "
          f"({re_report.get('readiness_band')}) — {re_report.get('blocking')} blocking")
    if re_report.get("blocking", 0):
        print("Blocking findings remain — resolve the judgment items above by hand.")
    return 0 if re_report.get("blocking", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
