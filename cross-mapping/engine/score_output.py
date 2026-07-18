#!/usr/bin/env python3
"""
score_output.py — deterministic quality scorer for GRC analysis output.

Consumes a findings report from tools/output_validate.py (plus optional judge
sub-scores per dimension, 0-5) and produces a computed verdict. The same inputs
always produce the same verdict — no vibes.

Authority for the model (weights, thresholds, bands): protocol-layer/quality-gates.md.
The weights there and here are machine-cross-checked (count_truth claim
'scorer_weights') so the doc and the code cannot drift apart.

Model:
  HARD-FAIL FIRST — any HIGH fabrication (id_reality) or leak finding => REJECTED
  before any composite arithmetic. Integrity > completeness > convenience.

  Dimensions (weight): citation_integrity .30, mapping_accuracy .25, coverage .15,
  source_currency .10, scope_correctness .10, honesty_about_gaps .10.
  Sub-scores default to 5.0 and are reduced mechanically by validator findings;
  judge sub-scores (if provided) override the mechanical defaults per dimension.

  Named thresholds (all reported): no_dimension_below_2,
  citation_integrity_at_least_4, composite_at_least_3_5.
  Verdict: all true -> APPROVED; composite >= 3.5 and exactly one other threshold
  false -> CONDITIONAL (human review); otherwise REJECTED.

Usage:
  python3 tools/output_validate.py REPORT.md --format json > findings.json
  python3 cross-mapping/engine/score_output.py findings.json [--judge judge.json]
  python3 cross-mapping/engine/score_output.py --selftest
"""

import argparse
import json
import sys
from pathlib import Path

# Single source of truth for weights IN CODE; the protocol doc mirrors this table
# and count_truth cross-checks the two (claim: scorer_weights).
WEIGHTS = {
    "citation_integrity": 0.30,
    "mapping_accuracy": 0.25,
    "coverage": 0.15,
    "source_currency": 0.10,
    "scope_correctness": 0.10,
    "honesty_about_gaps": 0.10,
}

HARD_FAIL_CHECKS = {"id_reality", "leak"}

# Mechanical deductions per validator finding, by check -> (dimension, per-finding penalty)
_DEDUCTIONS = {
    "unsourced_number": ("citation_integrity", 1.0),
    "overconfident_phrasing": ("mapping_accuracy", 1.0),
}


def score(findings_report: dict, judge_scores: dict | None = None) -> dict:
    findings = findings_report.get("findings", [])

    # 1. hard-fail first
    hard = [f for f in findings
            if f.get("severity") == "HIGH" and f.get("check") in HARD_FAIL_CHECKS]
    if hard:
        return {
            "verdict": "REJECTED",
            "hard_fail": True,
            "hard_fail_findings": hard,
            "composite": None,
            "dimensions": None,
            "thresholds": None,
            "human_review_required": True,
        }

    # 2. mechanical sub-scores (start at 5, deduct per finding), judge overrides
    dims = {d: 5.0 for d in WEIGHTS}
    for f in findings:
        hit = _DEDUCTIONS.get(f.get("check"))
        if hit:
            dim, pen = hit
            dims[dim] = max(0.0, dims[dim] - pen)
    for d, v in (judge_scores or {}).items():
        if d in dims:
            dims[d] = max(0.0, min(5.0, float(v)))

    composite = round(sum(dims[d] * w for d, w in WEIGHTS.items()), 3)
    thresholds = {
        "no_dimension_below_2": all(v >= 2.0 for v in dims.values()),
        "citation_integrity_at_least_4": dims["citation_integrity"] >= 4.0,
        "composite_at_least_3_5": composite >= 3.5,
    }
    if all(thresholds.values()):
        verdict = "APPROVED"
    elif thresholds["composite_at_least_3_5"] and sum(
            1 for v in thresholds.values() if not v) == 1:
        verdict = "CONDITIONAL"
    else:
        verdict = "REJECTED"
    return {
        "verdict": verdict,
        "hard_fail": False,
        "composite": composite,
        "dimensions": {d: round(v, 3) for d, v in sorted(dims.items())},
        "thresholds": thresholds,
        "human_review_required": verdict != "APPROVED" or bool(findings),
    }


def selftest() -> int:
    fails = []

    def expect(label, got, want):
        if got != want:
            fails.append(f"{label}: got {got}, want {want}")
        else:
            print(f"  ok: {label}")

    # hard-fail preempts composite (even with perfect judge scores)
    r = score({"findings": [{"severity": "HIGH", "check": "id_reality", "detail": "x"}]},
              judge_scores={d: 5 for d in WEIGHTS})
    expect("fabrication hard-fails to REJECTED", (r["verdict"], r["hard_fail"]), ("REJECTED", True))
    r = score({"findings": [{"severity": "HIGH", "check": "leak", "detail": "x"}]})
    expect("leak hard-fails to REJECTED", r["verdict"], "REJECTED")

    # clean report approves
    r = score({"findings": []})
    expect("clean report APPROVED at composite 5.0", (r["verdict"], r["composite"]), ("APPROVED", 5.0))

    # one unsourced number: citation_integrity 4.0 -> still APPROVED (boundary)
    r = score({"findings": [{"severity": "MEDIUM", "check": "unsourced_number", "detail": "x"}]})
    expect("single unsourced number stays APPROVED at the 4.0 boundary",
           (r["verdict"], r["dimensions"]["citation_integrity"]), ("APPROVED", 4.0))

    # two unsourced numbers: citation 3.0 -> threshold false, composite >=3.5 -> CONDITIONAL
    r = score({"findings": [{"severity": "MEDIUM", "check": "unsourced_number", "detail": "x"}] * 2})
    expect("two unsourced numbers -> CONDITIONAL", r["verdict"], "CONDITIONAL")

    # judged collapse: low citation integrity + low accuracy -> REJECTED
    r = score({"findings": []}, judge_scores={"citation_integrity": 1, "mapping_accuracy": 1})
    expect("judged 1/1 collapse -> REJECTED", r["verdict"], "REJECTED")

    # determinism
    payload = {"findings": [{"severity": "MEDIUM", "check": "overconfident_phrasing", "detail": "x"}]}
    expect("determinism (same input, same verdict)", score(payload), score(payload))

    print("selftest:", "PASS" if not fails else "FAIL")
    for f in fails:
        print("  FAIL:", f)
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="deterministic GRC output quality scorer")
    ap.add_argument("findings", nargs="?", help="JSON report from tools/output_validate.py --format json")
    ap.add_argument("--judge", help="optional JSON of judge sub-scores {dimension: 0-5}")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.findings:
        ap.error("provide a findings file or --selftest")
    report = json.loads(Path(a.findings).read_text(encoding="utf-8"))
    judge = json.loads(Path(a.judge).read_text(encoding="utf-8")) if a.judge else None
    result = score(report, judge)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "APPROVED" else 1


if __name__ == "__main__":
    sys.exit(main())
