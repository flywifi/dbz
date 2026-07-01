#!/usr/bin/env python3
"""
consolidate.py — deterministic merge of agent envelopes into one consolidated result.

Implements skills/shared/consolidation.md. The rule that makes this trustworthy:
the LLM judges with evidence, this script does the arithmetic. The same set of
envelopes always merges to byte-identical output (findings sorted by key), so the
manager can read one small consolidated object instead of the raw transcripts, and a
verification test can assert reproducibility.

Merge policy (never violated):
  - agree on a key      -> one merged finding; confidence FLOORED (weakest link)
  - disagree on a key   -> preserved as a conflict; NEVER averaged or blended
  - any partial/blocked -> coverage.state is 'partial', never 'complete'
  - a key no agent found is absent (a gap), never fabricated to look complete

Dependency-free (stdlib only).

Usage:
    from consolidate import consolidate
    result = consolidate(run_id, envelopes, stop_condition)

CLI:
    python3 consolidate.py run.json      # {"run_id","envelopes","stop_condition"}
    echo '<json>' | python3 consolidate.py -
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_CONF_RANK = {"high": 3, "medium": 2, "low": 1, "uncertain": 0}
_RANK_CONF = {v: k for k, v in _CONF_RANK.items()}


def _canon(value: Any) -> str:
    """Canonical JSON form for value comparison (order-independent)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _uncertainty_id(kind: str, **fields: Any) -> str:
    """Deterministic 16-hex id for a minority-report entry, keyed to the confirmation
    ledger (matches cross-mapping/engine/uncertainty.py)."""
    import hashlib
    payload = json.dumps({"kind": kind, **fields}, sort_keys=True,
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _floor_conf(confs: List[str]) -> str:
    if not confs:
        return "uncertain"
    return _RANK_CONF[min(_CONF_RANK.get(c, 0) for c in confs)]


def _sig(scope: str) -> str:
    return " ".join(str(scope).lower().split())


def _run_of(task_id: Any) -> Optional[str]:
    if isinstance(task_id, str) and "." in task_id:
        return task_id.split(".", 1)[0]
    return task_id if isinstance(task_id, str) else None


def consolidate(run_id: str, envelopes: List[Dict[str, Any]],
                stop_condition: Optional[str] = None,
                covered_scopes: Optional[List[str]] = None) -> Dict[str, Any]:
    # covered_scopes: scope signatures already dispatched across all waves. A residual lead
    # whose scope was later covered is no longer "residual" — reconciling against this keeps
    # cumulative coverage honest (a wave-1 lead answered in wave 2 stops showing as open).
    covered = {_sig(s) for s in (covered_scopes or [])}
    # Guard: all envelopes must belong to one run (derived from task_id prefix).
    runs = {_run_of(e.get("task_id")) for e in envelopes if isinstance(e, dict)}
    runs.discard(None)
    if len(runs) > 1:
        return {
            "run_id": run_id,
            "error": "mixed run_ids among envelopes: " + ", ".join(sorted(str(r) for r in runs)),
            "human_review_required": True,
        }

    agents_total = len(envelopes)
    counts = {"complete": 0, "partial": 0, "blocked": 0}
    sources: set[str] = set()
    frontier: Dict[str, Dict[str, str]] = {}
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    carried_conflicts: List[Any] = []
    carried_failed: List[Any] = []
    carried_uncertainty: List[Any] = []

    for e in envelopes:
        if not isinstance(e, dict):
            continue
        counts[e.get("status", "blocked")] = counts.get(e.get("status", "blocked"), 0) + 1
        prov = e.get("provenance", {}) or {}
        for s in prov.get("sources_read", []) or []:
            sources.add(str(s))
        for lead in e.get("residual_frontier", []) or []:
            if isinstance(lead, dict) and "scope" in lead:
                frontier.setdefault(_sig(lead["scope"]), {
                    "scope": lead["scope"], "reason": lead.get("reason", ""),
                })
        for f in e.get("findings", []) or []:
            if isinstance(f, dict) and "key" in f:
                by_key.setdefault(f["key"], []).append(f)
        mr = e.get("minority_report")
        if isinstance(mr, dict):
            carried_conflicts.extend(mr.get("conflicts", []) or [])
            carried_failed.extend(mr.get("failed_to_merge", []) or [])
            carried_uncertainty.extend(mr.get("residual_uncertainty", []) or [])

    # Merge findings by key (sorted for determinism).
    findings: List[Dict[str, Any]] = []
    cross_conflicts: List[Dict[str, Any]] = []
    for key in sorted(by_key):
        group = by_key[key]
        variants: Dict[str, List[Dict[str, Any]]] = {}
        for f in group:
            variants.setdefault(_canon(f.get("value")), []).append(f)
        provs = sorted({str(f.get("provenance", "")) for f in group})
        confs = [f.get("confidence", "uncertain") for f in group]
        if len(variants) == 1:
            findings.append({
                "key": key, "status": "merged",
                "value": group[0].get("value"),
                "provenance": provs, "confidence": _floor_conf(confs),
            })
        else:
            variant_list = [
                {"value": json.loads(cv), "provenance": sorted({str(f.get("provenance", "")) for f in fs})}
                for cv, fs in sorted(variants.items())
            ]
            findings.append({
                "key": key, "status": "conflict",
                "value": variant_list,
                "provenance": provs, "confidence": _floor_conf(confs),
            })
            cross_conflicts.append({
                "uncertainty_id": _uncertainty_id("cross_conflict", key=key, sources=sorted(provs)),
                "why_conflict": "provenance_tier",
                "affected_keys": [key],
                "conflict_summary": f"{len(variants)} sources disagree on '{key}' — preserved, not merged",
                "positions": [
                    {"claim_value": v["value"], "citation": {"locator": ", ".join(v["provenance"])},
                     "provenance_tier": "unspecified"}
                    for v in variant_list
                ],
                "sources": provs, "materiality": "high", "status": "open",
            })

    # Residual = open leads whose scope was NOT later covered (reconciled against covered).
    residual = [frontier[s] for s in sorted(frontier) if s not in covered]
    # 'complete' requires at least one agent AND no partial/blocked AND an empty frontier.
    # An empty run is never 'complete' — nothing was covered (see findings-consolidate MAINTAINER).
    state = "complete" if (agents_total > 0
                           and counts.get("partial", 0) == 0
                           and counts.get("blocked", 0) == 0
                           and not residual) else "partial"

    # High-materiality findings that should be adversarially verified before they are
    # trusted: any conflict, or any finding merged at low/uncertain confidence. The manager
    # routes these keys to the finding-verify atom (skeptics); nothing here is auto-trusted.
    pending_verification = sorted({
        f["key"] for f in findings
        if f["status"] == "conflict" or f["confidence"] in ("low", "uncertain")
    })

    all_conflicts = carried_conflicts + cross_conflicts
    if agents_total == 0:
        carried_uncertainty.append({
            "statement": "no envelopes were consolidated",
            "what_would_resolve_it": "dispatch at least one agent",
            "impact_if_wrong": "no coverage",
        })
    has_mr = bool(all_conflicts or carried_failed or carried_uncertainty)
    minority_report = None
    if has_mr:
        minority_report = {
            "decision_log": {
                "chosen_interpretation": f"run consolidated; stopped on '{stop_condition or 'unspecified'}'",
                "why_it_won": "deterministic merge per consolidation.md",
                "confidence": "high",
            },
            "conflicts": all_conflicts,
            "failed_to_merge": carried_failed,
            "residual_uncertainty": carried_uncertainty,
        }

    return {
        "run_id": run_id,
        "coverage": {
            "state": state,
            "agents_total": agents_total,
            "agents_complete": counts.get("complete", 0),
            "agents_partial": counts.get("partial", 0),
            "agents_blocked": counts.get("blocked", 0),
            "sources_read": sorted(sources),
            "stop_condition": stop_condition,
        },
        "findings": findings,
        "residual_frontier": residual,
        "pending_verification": pending_verification,
        "minority_report": minority_report,
        "human_review_required": True,
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: consolidate.py <run.json | ->", file=sys.stderr)
        return 2
    raw = sys.stdin.read() if argv[0] == "-" else Path(argv[0]).read_text(encoding="utf-8")
    payload = json.loads(raw)
    result = consolidate(
        payload.get("run_id", "unnamed-run"),
        payload.get("envelopes", []),
        payload.get("stop_condition"),
        payload.get("covered_scopes"),
    )
    # Deterministic serialization: sort_keys so repeated runs are byte-identical.
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
