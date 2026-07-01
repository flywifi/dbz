#!/usr/bin/env python3
"""
verify.py — deterministic tally for adversarial verification of high-materiality findings.

The adversarial-verify pattern (as used by Claude Code's /deep-research): before a
high-stakes finding is promoted into the consolidated result, spawn independent skeptic
agents each prompted to REFUTE it. This script does not run the skeptics — the agents
supply the judgments; this script does the *arithmetic* (the "LLM judges, script computes"
split), so the promote/drop decision is reproducible.

Rules (adversarial stance):
  - "unable to check" wins when it is a majority — a claim the skeptics could not evaluate
    (rate limit, missing source) is 'unverified', NOT refuted. Mirrors Claude Code's
    v2.1.196 behavior: unverifiable != refuted.
  - otherwise ties go to REFUTED — the burden of proof is on the finding.
  - a finding survives only with a strict majority of confirming votes.

Dependency-free (stdlib only).

Usage:
    from verify import tally, apply_verdicts
    verdict = tally(refuting=2, confirming=1)            # -> {"verdict": "refuted", ...}
    updated = apply_verdicts(consolidated, verdicts)     # fold verdicts back into a result
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List


def tally(refuting: int, confirming: int, unable: int = 0) -> Dict[str, Any]:
    """Resolve one finding's skeptic votes into a verdict. Deterministic."""
    refuting = max(0, int(refuting))
    confirming = max(0, int(confirming))
    unable = max(0, int(unable))
    total = refuting + confirming + unable

    if total == 0:
        verdict = "unverified"
    elif unable >= math.ceil(total / 2):
        verdict = "unverified"
    elif confirming > refuting:
        verdict = "confirmed"
    else:
        # ties and refuting-majority both drop — burden of proof is on the finding
        verdict = "refuted"

    return {
        "verdict": verdict,
        "refuting_votes": refuting,
        "confirming_votes": confirming,
        "unable_votes": unable,
        "human_review_required": True,
    }


def apply_verdicts(consolidated: Dict[str, Any],
                   verdicts: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fold per-key verdicts back into a consolidated result.

    - confirmed  -> finding kept, annotated verdict: confirmed
    - unverified -> finding kept but annotated verdict: unverified + a residual_uncertainty note
    - refuted    -> finding REMOVED from findings[] and recorded in minority_report.failed_to_merge
                    (never silently dropped, never fabricated back in)

    Deterministic: outputs are re-sorted by key. Non-mutating (returns a new dict).
    """
    result = json.loads(json.dumps(consolidated))  # deep copy, stable
    kept: List[Dict[str, Any]] = []
    refuted_notes: List[Dict[str, Any]] = []
    uncertainty_notes: List[Dict[str, Any]] = []

    for f in result.get("findings", []):
        v = verdicts.get(f["key"])
        if not v:
            kept.append(f)
            continue
        verdict = v.get("verdict", "unverified")
        f["verdict"] = verdict
        if verdict == "refuted":
            refuted_notes.append({
                "interpretation_a": f"finding '{f['key']}' as reported",
                "interpretation_b": "adversarial skeptics refuted it",
                "why_not_mergeable": "removed from findings by adversarial verification",
                "affected_keys": [f["key"]],
            })
        else:
            kept.append(f)
            if verdict == "unverified":
                uncertainty_notes.append({
                    "statement": f"finding '{f['key']}' could not be verified",
                    "what_would_resolve_it": "re-run skeptics with a reachable source",
                    "impact_if_wrong": "finding may not hold",
                })

    result["findings"] = sorted(kept, key=lambda x: x["key"])

    if refuted_notes or uncertainty_notes:
        mr = result.get("minority_report") or {
            "decision_log": {"chosen_interpretation": "adversarial verification applied",
                             "why_it_won": "high-materiality findings were skeptic-checked",
                             "confidence": "high"},
            "conflicts": [], "failed_to_merge": [], "residual_uncertainty": [],
        }
        mr["failed_to_merge"] = mr.get("failed_to_merge", []) + refuted_notes
        mr["residual_uncertainty"] = mr.get("residual_uncertainty", []) + uncertainty_notes
        result["minority_report"] = mr

    # Keys that were verified are no longer pending — prune them so the field stays honest.
    if isinstance(result.get("pending_verification"), list):
        result["pending_verification"] = sorted(
            k for k in result["pending_verification"] if k not in verdicts
        )

    result["verification_applied"] = True
    return result


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: verify.py <payload.json | ->   "
              "(payload: {consolidated, verdicts}) OR {refuting, confirming, unable}",
              file=sys.stderr)
        return 2
    raw = sys.stdin.read() if argv[0] == "-" else Path(argv[0]).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if "consolidated" in payload:
        out = apply_verdicts(payload["consolidated"], payload.get("verdicts", {}))
    else:
        out = tally(payload.get("refuting", 0), payload.get("confirming", 0), payload.get("unable", 0))
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
