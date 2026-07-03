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


# ── durable uncertainty ledger (committed, deterministic) ───────────────────────

def _source_citation(filename: str) -> dict:
    """Map a bare source filename to a repo-relative, resolvable citation path.
    Probes the known artifact directories (source_data, its cprt/ subdir, and
    canonical-sources root) and cites the first that exists — a citation must
    resolve to a real committed file (health_audit blocks otherwise)."""
    if not filename:
        return {"file": "", "locator": ""}
    repo_root = Path(__file__).resolve().parent.parent.parent
    for rel in (f"canonical-sources/source_data/{filename}",
                f"canonical-sources/source_data/cprt/{filename}",
                f"canonical-sources/{filename}"):
        if (repo_root / rel).exists():
            return {"file": rel, "locator": filename}
    return {"file": f"canonical-sources/source_data/{filename}", "locator": filename}


def _stamp_status(row: dict, confirmations: Dict[str, dict]) -> dict:
    rec = confirmations.get(row["uncertainty_id"])
    if not rec:
        row["status"] = "open"
        return row
    decision = rec.get("decision")
    if decision == "confirmed":
        row["status"] = "confirmed"
        row["needs_confirmation"] = 0
        if "winning_citation" in rec:
            row["winning_citation"] = rec["winning_citation"]
        if "resolution_note" in rec:
            row["why_it_won"] = rec["resolution_note"]
    elif decision == "refuted":
        row["status"] = "refuted"
    else:
        row["status"] = "open"
    return row


def build_ledger_rows(conn, confirmations: Optional[Dict[str, dict]] = None) -> List[dict]:
    """
    Build the durable uncertainty ledger from the built db: one entry per overlap
    pair (review-worthy at the pair level, not per hub edge) and one per pinned ODP
    value.  Deterministic, sorted by uncertainty_id, no timestamps.  Every entry
    carries a resolvable citation so the health auditor can verify it.  Confirmations
    (keyed by these ledger uncertainty_ids) stamp each entry's status.
    """
    confirmations = confirmations or {}
    rows: List[dict] = []

    # a representative committed source file per framework (for the pair citation)
    fw_src: Dict[str, str] = {}
    for framework, sfile in conn.execute(
            "SELECT framework, MIN(source_file) FROM framework_projection GROUP BY framework"):
        fw_src[framework] = sfile or ""

    for r in conn.execute("""
            SELECT framework_a, framework_b, basis, jaccard_pct, confidence,
                   needs_confirmation FROM overlap_matrix"""):
        fa, fb, basis, pct, conf, needs = r
        uid = uncertainty_id("overlap_pair", a=fa, b=fb, basis=basis)
        cit = _source_citation(fw_src.get(fa) or fw_src.get(fb, ""))
        if not cit["file"] and basis in ("inferred_er", "none"):
            # ER-only pairs (SOC 1, HITRUST CSF) have no projection source; the
            # co-occurrence signal derives from the committed ER crosswalk CSVs.
            cit = {"file": "cross-mapping/core-audit/mappings",
                   "locator": "er_mappings (aggregate co-occurrence)"}
        rows.append({
            "uncertainty_id": uid,
            "kind": "overlap_pair",
            "framework_a": fa, "framework_b": fb, "basis": basis,
            "overlap_pct": pct, "confidence": conf,
            "needs_confirmation": int(needs),
            "citation": cit,
            "status": "open",
        })

    for r in conn.execute("""
            SELECT control_id, baseline, value_norm, value_raw, source_file, source_row,
                   extraction_confidence FROM odp_values ORDER BY control_id, value_norm"""):
        cid, baseline, vnorm, vraw, sfile, srow, econf = r
        uid = uncertainty_id("odp_value", control_id=cid, baseline=baseline, value=vnorm)
        cit = _source_citation(sfile)
        cit["locator"] = f"{sfile}:{srow}"
        rows.append({
            "uncertainty_id": uid,
            "kind": "odp_value",
            "control_id": cid, "baseline": baseline, "value": vnorm, "value_raw": vraw,
            "extraction_confidence": econf,
            "needs_confirmation": 1,
            "citation": cit,
            "status": "open",
            "note": "single baseline pins this value; cross-framework alignment undetermined",
        })

    for r in rows:
        _stamp_status(r, confirmations)
    rows.sort(key=lambda x: x["uncertainty_id"])
    return rows


def write_ledger(conn, path: Path, confirmations: Optional[Dict[str, dict]] = None) -> int:
    rows = build_ledger_rows(conn, confirmations)
    lines = [_canon(r) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(rows)


def load_ledger(path: Path) -> List[dict]:
    out: List[dict] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
