#!/usr/bin/env python3
"""
ci_rehearsal.py — reproduce the CI condition locally, in one command.

Two incidents (the Phase-27 health workflow failure and the four-red window closed by the
metrics fresh-checkout fix) shared one failure class: a check passes on a built workspace
but fails on CI's fresh checkout, and the manual "hide the build artifacts, rerun, restore"
ritual was performed from memory. This harness makes the rehearsal mechanical:

  1. crash-recovery: if .ci-rehearsal-stash/ exists from an interrupted run, restore it first;
  2. move the gitignored build outputs (cross-mapping/output/*, cross-mapping/nist-catalog/
     output/*) into .ci-rehearsal-stash/ so the tree looks like a fresh checkout;
  3. run every step of .github/workflows/health.yml — the STEPS list below MIRRORS that file
     verbatim (health.yml is the authority; a drift self-check greps it and warns on mismatch);
  4. restore the stash unconditionally (finally:), report a per-step PASS/FAIL table, exit 1
     if any step failed.

`--standards-watch` mirrors the OTHER workflow instead (monthly standards-watch.yml, which
builds on the runner and therefore needs the generated catalog + OSCAL cache produced first
— the fresh-checkout mode that turned that workflow red on 2026-08-03). Slow and opt-in:
run it when touching that workflow, the generators, or the benchmark.

Run it before every push (merge bar: changes/CHANGE_MANAGEMENT.md). Deliberately NOT a
pre-commit hook — it moves directories, which is hostile per-commit; it is the pre-PUSH step.
NEVER run concurrently with build_db.py: the stash move would pull the build's output paths
out from under it (the standing rule is sequential builds only).
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STASH = ROOT / ".ci-rehearsal-stash"
HEALTH_YML = ROOT / ".github" / "workflows" / "health.yml"

# Build-output dirs CI never has (gitignored). Relative to ROOT.
HIDE_DIRS = ("cross-mapping/output", "cross-mapping/nist-catalog/output")

# Mirrors .github/workflows/health.yml step-for-step — keep in sync (drift check below).
STEPS = [
    ("secret-scan backstop", "python3 tools/secret_scan.py --range c3192c8..HEAD"),
    ("drift guard (sync_check)", "python3 tools/sync_check.py"),
    ("health audit — scan", "python3 tools/health_audit.py --scan"),
    ("health audit — full", "python3 tools/health_audit.py --full"),
    ("auditor golden self-test", "python3 skills/health-auditor/tests/run_golden.py"),
    ("instruction blocks self-test", "python3 skills/health-auditor/scripts/instruction_blocks.py --self-test"),
    ("instruction audit — structure", "python3 skills/health-auditor/scripts/instruction_blocks.py --audit-all"),
    ("orchestration scenario", "python3 skills/multi-agent-orchestrator/tests/run_scenario.py"),
    # health.yml runs the catalog validator only when the build output exists; in the
    # rehearsal the artifacts are hidden, so CI's skip path is what we exercise.
    ("catalog validators (CI-conditional)", None),
]

# Mirrors .github/workflows/standards-watch.yml (--standards-watch). That workflow is
# monthly and BUILDS on the runner, so its fresh-checkout failure mode is different from
# health.yml's: it needs the generated catalog and the OSCAL cache produced first. The
# 2026-08-03 run went red exactly here. Slow (~build + a ~5MB OSCAL fetch) — opt-in.
WATCH_STEPS = [
    ("standards drift check", "python3 tools/standards_refresh.py --check"),
    ("generate catalog", "python3 cross-mapping/nist-catalog/ingestion/generate_controls.py"),
    ("warm OSCAL cache", "python3 cross-mapping/engine/oscal_diff.py "
                         "--oscal-cache cross-mapping/output/oscal_v5.2.0_cache.json --dry-run"),
    ("build grc.db", "python3 cross-mapping/engine/build_db.py"),
    ("oracle benchmark", "python3 cross-mapping/tests/benchmark_oracles.py --check"),
    ("scenario battery", "python3 cross-mapping/tests/run_scenarios.py"),
    ("alias contract", "python3 cross-mapping/tests/test_alias_contract.py"),
]


def _restore():
    if not STASH.exists():
        return
    for item in sorted(STASH.rglob("*")):
        if item.is_file():
            dest = ROOT / item.relative_to(STASH)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(dest))
    shutil.rmtree(STASH, ignore_errors=True)


def _hide():
    for rel in HIDE_DIRS:
        src = ROOT / rel
        if not src.exists():
            continue
        for f in sorted(src.iterdir()):
            if f.is_file():
                dest = STASH / rel / f.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(dest))


def _drift_check():
    """health.yml is the authority — warn (not fail) when a mirrored command drifts."""
    text = HEALTH_YML.read_text(encoding="utf-8")
    for label, cmd in STEPS:
        if cmd and cmd not in text:
            print(f"  [warn] step '{label}' not found verbatim in health.yml — "
                  "the workflow changed; update STEPS in tools/ci_rehearsal.py")


def main():
    # Doctor line (phase 41): the pre-push hook only protects installed clones.
    import subprocess as _sp
    _hp = _sp.run(["git", "config", "core.hooksPath"], capture_output=True, text=True).stdout.strip()
    if _hp != "tools/hooks":
        print("WARN: pre-push hook not installed — run: git config core.hooksPath tools/hooks")
    watch = "--standards-watch" in sys.argv
    steps, yml = (WATCH_STEPS, "standards-watch.yml") if watch else (STEPS, "health.yml")
    tracked = subprocess.run(
        ["git", "status", "--porcelain", *HIDE_DIRS],
        capture_output=True, text=True, cwd=ROOT).stdout.strip()
    if tracked:
        print("[abort] build-output paths show up in git status — resolve before rehearsing:")
        print(tracked)
        return 2

    if STASH.exists():
        print("[recover] restoring stash from an interrupted run first")
        _restore()

    if not watch:
        _drift_check()
    results = []
    try:
        _hide()
        for label, cmd in steps:
            if cmd is None:  # CI-conditional step: artifacts hidden -> CI's skip path
                results.append((label, 0, "skipped (build artifacts absent, as on CI)"))
                continue
            p = subprocess.run(cmd.split(), capture_output=True, text=True, cwd=ROOT)
            tail = (p.stdout or p.stderr).strip().splitlines()
            results.append((label, p.returncode, tail[-1][:88] if tail else ""))
    finally:
        _restore()

    print(f"\nCI REHEARSAL (mirrors .github/workflows/{yml}, artifacts hidden):")
    failed = 0
    for label, rc, tail in results:
        status = "PASS" if rc == 0 else f"FAIL rc={rc}"
        if rc != 0:
            failed += 1
        print(f"  {status:9} {label:36} {tail}")
    print(f"\n{'[REHEARSAL PASS] — safe to push' if not failed else f'[{failed} STEP(S) WOULD FAIL ON CI] — fix before pushing'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
