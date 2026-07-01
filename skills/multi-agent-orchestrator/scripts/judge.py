#!/usr/bin/env python3
"""
judge.py — deterministic rubric composite for the "is this wave good enough to stop?" call.

Modeled on Anthropic's multi-agent research finding that a single LLM-as-judge call
emitting rubric scores is the most consistent quality signal, and on the educator-tools
pattern of splitting judgment from arithmetic: the LLM (the wave-judge atom) supplies a
0.0–1.0 score per dimension WITH evidence; this script computes the weighted composite and
the stop/continue recommendation. Same scores in → same recommendation out.

This is a stop *signal that complements* frontier saturation — not a replacement. The
manager stops when the frontier is dry OR the judge says quality is sufficient; it keeps
going when either says there is more to do.

Dimensions (weights sum to 1.0):
    coverage      0.35  — how much of the intended scope the wave actually reached
    consistency   0.25  — how free of unresolved conflicts the merged findings are
    provenance    0.20  — how well findings are sourced (no blank/weak provenance)
    saturation    0.20  — confidence the residual frontier is genuinely exhausted

Recommendation:
    stop      when composite >= STOP_THRESHOLD (0.80) AND coverage >= COVERAGE_FLOOR (0.70)
    continue  otherwise (a strong composite cannot paper over thin coverage)

Dependency-free (stdlib only).

Usage:
    from judge import composite
    r = composite({"coverage":0.9,"consistency":0.8,"provenance":0.85,"saturation":0.7})
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

WEIGHTS = {"coverage": 0.35, "consistency": 0.25, "provenance": 0.20, "saturation": 0.20}
STOP_THRESHOLD = 0.80
COVERAGE_FLOOR = 0.70


def composite(scores: Dict[str, float]) -> Dict[str, Any]:
    """Weighted composite + stop/continue recommendation. Deterministic."""
    clamped = {}
    missing = []
    for dim in WEIGHTS:
        if dim not in scores:
            missing.append(dim)
            clamped[dim] = 0.0
        else:
            try:
                clamped[dim] = max(0.0, min(1.0, float(scores[dim])))
            except (TypeError, ValueError):
                missing.append(dim)
                clamped[dim] = 0.0

    value = round(sum(clamped[d] * WEIGHTS[d] for d in WEIGHTS), 4)
    weakest = min(WEIGHTS, key=lambda d: clamped[d])
    recommend = "stop" if (value >= STOP_THRESHOLD and clamped["coverage"] >= COVERAGE_FLOOR) else "continue"

    result = {
        "composite": value,
        "recommendation": recommend,
        "weakest_dimension": weakest,
        "dimension_scores": clamped,
        "thresholds": {"stop_threshold": STOP_THRESHOLD, "coverage_floor": COVERAGE_FLOOR},
        "human_review_required": True,
    }
    if missing:
        # A missing dimension scored 0.0 pushes toward 'continue' — never fabricate a pass.
        result["missing_dimensions"] = sorted(missing)
    return result


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: judge.py <scores.json | ->   "
              "(scores: {coverage, consistency, provenance, saturation})", file=sys.stderr)
        return 2
    raw = sys.stdin.read() if argv[0] == "-" else Path(argv[0]).read_text(encoding="utf-8")
    scores = json.loads(raw)
    print(json.dumps(composite(scores), indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
