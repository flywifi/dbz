"""
uncertainty.py — deterministic uncertainty ids + the confirmation cascade.

Every questionable thing the engine emits (a hub-mediated / inferred projection edge,
an ODP-value divergence, a derived relationship, an agent-dissent) gets a stable
`uncertainty_id = sha256(canon(salient fields))[:16]`.  A single committed ledger of
human confirmations, keyed by that id, is applied at build time and re-derives every
dependent field — so confirming once cascades everywhere on the next build.

Stdlib only; deterministic (no wall-clock).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _canon(value: Any) -> str:
    """Canonical JSON form for hashing (order-independent). Matches the orchestration
    bucket's _canon convention."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def uncertainty_id(kind: str, **fields: Any) -> str:
    """A stable 16-hex id for an uncertainty of the given kind + salient fields."""
    payload = {"kind": kind, **fields}
    return hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()[:16]


def edge_uncertainty_id(edge: Dict[str, Any]) -> str:
    """Uncertainty id for a projection edge — stable across runs (no row numbers)."""
    return uncertainty_id(
        "projection_edge",
        framework=edge.get("framework"),
        native_id=edge.get("native_id"),
        spine=edge.get("r5_subpart") or edge.get("r5_control"),
        provenance=edge.get("provenance"),
    )


def odp_clash_uncertainty_id(control_id: str, odp_id: Optional[str]) -> str:
    return uncertainty_id("odp_value_divergence", control_id=control_id, odp_id=odp_id)


# ── confirmations ledger ────────────────────────────────────────────────────────

def load_confirmations(path: Path) -> Dict[str, dict]:
    """
    Read a confirmations JSONL ledger into {uncertainty_id -> decision record}.
    Lines whose keys all start with '_' (schema/doc lines) or blank lines are ignored.
    Tolerant of a missing file (returns {}).
    """
    out: Dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        uid = rec.get("uncertainty_id")
        if not uid:
            continue  # skip schema/doc lines that have no uncertainty_id
        out[uid] = rec
    return out


def apply_confirmations_to_edges(edges: List[dict], confirmations: Dict[str, dict]) -> dict:
    """
    Stamp every edge with its uncertainty_id, then apply confirmations in place:
      * confirmed -> needs_confirmation=0, confidence lifted to >= 0.9, status='confirmed'
      * refuted   -> status='refuted', confidence dropped to <= 0.3 (kept for the audit
                     trail; the overlap engine can exclude refuted edges)
      * otherwise -> status='open'
    Returns cascade stats.  Pure w.r.t. the ledger — same ledger + edges => same result.
    """
    confirmed = refuted = 0
    for e in edges:
        uid = edge_uncertainty_id(e)
        e["uncertainty_id"] = uid
        rec = confirmations.get(uid)
        if not rec:
            e["status"] = "open"
            continue
        decision = rec.get("decision")
        if decision == "confirmed":
            e["needs_confirmation"] = 0
            e["confidence"] = max(float(e.get("confidence", 0.0)), 0.9)
            e["status"] = "confirmed"
            confirmed += 1
        elif decision == "refuted":
            e["confidence"] = min(float(e.get("confidence", 1.0)), 0.3)
            e["status"] = "refuted"
            refuted += 1
        else:
            e["status"] = "open"
    return {"edges": len(edges), "confirmed": confirmed, "refuted": refuted,
            "ledger_entries": len(confirmations)}
