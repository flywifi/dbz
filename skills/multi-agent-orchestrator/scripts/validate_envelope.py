#!/usr/bin/env python3
"""
validate_envelope.py — the run-time anti-drift gate for multi-agent orchestration.

Checks a single agent envelope against the structural contract in
skills/shared/orchestration-envelope.schema.json. A malformed envelope is a hard
stop — it is blocked from consolidation, never patched or merged in a degraded form.

Dependency-free (stdlib only): the check is hand-rolled against the schema's required
fields and enums rather than pulling in `jsonschema`, so it runs anywhere the rest of
the pipeline runs. It is deliberately structural only — it says nothing about whether
the findings are *correct* (that would fabricate a quality signal).

Usage:
    from validate_envelope import validate_envelope
    result = validate_envelope(envelope_dict)   # -> {"valid": bool, "violations": [...], "task_id": ...}

CLI:
    python3 validate_envelope.py envelope.json
    echo '<envelope json>' | python3 validate_envelope.py -
Exit: 0 if valid, 1 if any violation (so it can gate a shell pipeline).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

CONF_ENUM = {"high", "medium", "low", "uncertain"}
STATUS_ENUM = {"complete", "partial", "blocked"}
MODE_ENUM = {"read-fanout", "mutate", "external"}

TOP_REQUIRED = [
    "task_id", "scope", "mode", "status", "findings", "residual_frontier",
    "provenance", "confidence", "minority_report", "human_review_required", "metrics",
]
TOP_ALLOWED = set(TOP_REQUIRED) | {"parent_task_id"}


def _v(path: str, message: str) -> Dict[str, str]:
    return {"path": path, "message": message}


def validate_envelope(env: Any) -> Dict[str, Any]:
    """Return {valid, violations[], task_id}. Violations are sorted by path (deterministic)."""
    violations: List[Dict[str, str]] = []

    if not isinstance(env, dict):
        return {"valid": False, "violations": [_v("$", "envelope is not an object")], "task_id": None}

    task_id = env.get("task_id") if isinstance(env.get("task_id"), str) else None

    # Unknown top-level keys are drift (additionalProperties: false).
    for k in env:
        if k not in TOP_ALLOWED:
            violations.append(_v(f"$.{k}", "unknown field (additionalProperties: false)"))

    # Required top-level keys.
    for k in TOP_REQUIRED:
        if k not in env:
            violations.append(_v(f"$.{k}", "required field missing"))

    # Enums / types on scalars.
    if "mode" in env and env["mode"] not in MODE_ENUM:
        violations.append(_v("$.mode", f"must be one of {sorted(MODE_ENUM)}"))
    if "status" in env and env["status"] not in STATUS_ENUM:
        violations.append(_v("$.status", f"must be one of {sorted(STATUS_ENUM)}"))
    if "confidence" in env and env["confidence"] not in CONF_ENUM:
        violations.append(_v("$.confidence", f"must be one of {sorted(CONF_ENUM)}"))
    if "task_id" in env and not isinstance(env["task_id"], str):
        violations.append(_v("$.task_id", "must be a string"))
    if "scope" in env and not isinstance(env["scope"], str):
        violations.append(_v("$.scope", "must be a string"))
    if "parent_task_id" in env and not (env["parent_task_id"] is None or isinstance(env["parent_task_id"], str)):
        violations.append(_v("$.parent_task_id", "must be a string or null"))

    # human_review_required is pinned to const true.
    if "human_review_required" in env and env["human_review_required"] is not True:
        violations.append(_v("$.human_review_required", "must be exactly true (const)"))

    # findings[]
    if "findings" in env:
        if not isinstance(env["findings"], list):
            violations.append(_v("$.findings", "must be an array"))
        else:
            for i, f in enumerate(env["findings"]):
                base = f"$.findings[{i}]"
                if not isinstance(f, dict):
                    violations.append(_v(base, "must be an object"))
                    continue
                for k in ("key", "value", "provenance", "confidence"):
                    if k not in f:
                        violations.append(_v(f"{base}.{k}", "required field missing"))
                if "provenance" in f and (not isinstance(f["provenance"], str) or not f["provenance"].strip()):
                    violations.append(_v(f"{base}.provenance", "must be a non-empty string"))
                if "confidence" in f and f["confidence"] not in CONF_ENUM:
                    violations.append(_v(f"{base}.confidence", f"must be one of {sorted(CONF_ENUM)}"))

    # residual_frontier[]
    if "residual_frontier" in env:
        if not isinstance(env["residual_frontier"], list):
            violations.append(_v("$.residual_frontier", "must be an array"))
        else:
            for i, lead in enumerate(env["residual_frontier"]):
                base = f"$.residual_frontier[{i}]"
                if not isinstance(lead, dict):
                    violations.append(_v(base, "must be an object"))
                    continue
                for k in ("scope", "reason"):
                    if k not in lead:
                        violations.append(_v(f"{base}.{k}", "required field missing"))

    # provenance
    if "provenance" in env:
        p = env["provenance"]
        if not isinstance(p, dict):
            violations.append(_v("$.provenance", "must be an object"))
        else:
            if not isinstance(p.get("sources_read"), list):
                violations.append(_v("$.provenance.sources_read", "must be an array"))
            if not isinstance(p.get("method"), str):
                violations.append(_v("$.provenance.method", "must be a string"))

    # minority_report: null or object with the 4 buckets
    if "minority_report" in env:
        mr = env["minority_report"]
        if mr is not None:
            if not isinstance(mr, dict):
                violations.append(_v("$.minority_report", "must be null or an object"))
            else:
                for k in ("decision_log", "conflicts", "failed_to_merge", "residual_uncertainty"):
                    if k not in mr:
                        violations.append(_v(f"$.minority_report.{k}", "required when minority_report is not null"))

    # metrics
    if "metrics" in env:
        m = env["metrics"]
        if not isinstance(m, dict):
            violations.append(_v("$.metrics", "must be an object"))
        elif not isinstance(m.get("items_found"), int):
            violations.append(_v("$.metrics.items_found", "required integer"))

    violations.sort(key=lambda x: x["path"])
    return {"valid": len(violations) == 0, "violations": violations, "task_id": task_id}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: validate_envelope.py <envelope.json | ->", file=sys.stderr)
        return 2
    raw = sys.stdin.read() if argv[0] == "-" else Path(argv[0]).read_text(encoding="utf-8")
    try:
        env = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"valid": False, "violations": [{"path": "$", "message": f"invalid JSON: {e}"}], "task_id": None}, indent=2))
        return 1
    result = validate_envelope(env)
    result["human_review_required"] = True
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
