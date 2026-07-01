#!/usr/bin/env python3
"""
run_golden.py — self-test for the health auditor (who audits the auditor).

Runs the REAL detector functions from tools/health_audit.py over a golden set of
intentionally-broken fixtures and a clean control, and validates against a hand-authored
oracle. This is "validate independent of the answer": the oracle states exactly which
findings each fixture must produce (authored from the fixtures, not generated), property
checks hold for any correct run, and a pinned sha256 proves byte-for-byte determinism.

Run:
    python3 skills/health-auditor/tests/run_golden.py           # check; exit 0/1
    python3 skills/health-auditor/tests/run_golden.py --emit     # print findings + sha256 (to pin)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
ROOT = HERE.parents[2]  # repo root
sys.path.insert(0, str(ROOT / "tools"))

import health_audit as HA  # noqa: E402


def _valid_targets() -> set:
    reg = json.loads((ROOT / "skills" / "atoms" / "atoms.json").read_text())
    reg_ids = {a["id"] for a in reg.get("atoms", [])}
    skills_dir = ROOT / "skills"
    skill_names = {p.name for p in skills_dir.iterdir()
                   if p.is_dir() and p.name != "shared" and not p.name.startswith(".")}
    atom_names = {p.name for p in HA.atom_dirs()}
    return reg_ids | skill_names | atom_names


def _detect(detector: str, path: Path) -> list:
    """Run one named detector over one fixture and return its findings."""
    if detector == "backtick_refs":
        return HA.check_backtick_refs(path, GOLDEN)
    if detector == "forbidden_tokens":
        return HA.check_forbidden_tokens(path)
    if detector == "evals_shape":
        return HA.check_evals_shape(path, "golden")
    if detector == "vocab":
        return HA.check_vocab_file(path)
    if detector == "registry_scripts":
        return HA.registry_script_findings(json.loads(path.read_text()), ROOT, rel=path.name)
    if detector == "workflow":
        return HA.workflow_findings(json.loads(path.read_text()), _valid_targets(), "golden", path.name)
    raise ValueError(f"unknown detector {detector}")


def run() -> dict:
    oracle = json.loads((GOLDEN / "oracle.json").read_text())
    all_findings = []      # for the determinism pin
    fails = []

    # broken fixtures: every planted defect must be caught
    for fname, spec in sorted(oracle["broken"].items()):
        found = _detect(spec["detector"], GOLDEN / "broken" / fname)
        all_findings += [(fname, f["severity"], f["issue"]) for f in found]
        for exp in spec["expect"]:
            hit = any(f["severity"] == exp["severity"] and exp["contains"] in f["issue"] for f in found)
            if not hit:
                fails.append(f"[{fname}] MISSED {exp['severity']} finding containing "
                             f"\"{exp['contains']}\" (got: {[f['issue'] for f in found]})")

    # clean fixtures: ZERO findings (no false positives)
    for fname, spec in sorted(oracle["clean"].items()):
        found = []
        for det in spec.get("detectors", [spec.get("detector")]):
            found += _detect(det, GOLDEN / "clean" / fname)
        if found:
            fails.append(f"[{fname}] FALSE POSITIVE on clean fixture: {[f['issue'] for f in found]}")

    # negative control: swap the defect for a real path → detector must go silent
    nc = oracle["negative_control"]
    text = (GOLDEN / "broken" / nc["file"]).read_text().replace(nc["replace"], nc["with"])
    tmp = GOLDEN / "broken" / (nc["file"] + ".nc")
    tmp.write_text(text)
    try:
        nc_found = HA.check_backtick_refs(tmp, GOLDEN)
    finally:
        tmp.unlink()
    if nc_found:
        fails.append(f"[negative_control] detector still fired after fix: {[f['issue'] for f in nc_found]}")

    pin = hashlib.sha256(json.dumps(sorted(all_findings), ensure_ascii=False).encode()).hexdigest()
    expected_pin = oracle.get("final_sha256")
    if expected_pin and expected_pin != "PIN" and pin != expected_pin:
        fails.append(f"[pin] sha256 mismatch: got {pin} want {expected_pin}")

    return {"fails": fails, "pin": pin, "defects_caught": len(all_findings)}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    r = run()
    if "--emit" in argv:
        print(f"defects_caught={r['defects_caught']}  sha256={r['pin']}")
        return 0
    if r["fails"]:
        print(f"golden self-test: FAIL — {len(r['fails'])} problem(s)")
        for f in r["fails"]:
            print(f"  ✗ {f}")
        return 1
    print(f"golden self-test: PASS — every planted defect caught, zero false positives, "
          f"negative control clean (sha256 {r['pin'][:12]}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
