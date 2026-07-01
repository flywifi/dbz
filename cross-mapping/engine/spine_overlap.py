"""
spine_overlap.py — CCI / sub-part-anchored framework overlap (Phase 5).

Replaces the old ER-set Jaccard with a spine-anchored engine that:
  * always returns a real number (never errors on cross-framework), via a
    degradation ladder cci -> subpart -> control -> inferred_er -> none;
  * reports per-control full / partial / none with the exact met vs. unmet
    sub-parts, and flags parameter (ODP) divergence;
  * carries provenance + a confidence tier on every result.

Read-only over grc.db; stdlib + sqlite only.  Deterministic (sorted output).
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Set, Tuple

# ── framework name resolution ───────────────────────────────────────────────────

_ALIASES = {
    "soc2": "SOC 2", "soc 2": "SOC 2", "soc-2": "SOC 2",
    "soc1": "SOC 1", "soc 1": "SOC 1",
    "iso": "ISO 27001/2 (2022)", "iso27001": "ISO 27001/2 (2022)",
    "iso 27001": "ISO 27001/2 (2022)", "iso 27001/2": "ISO 27001/2 (2022)",
    "hipaa": "HIPAA Security", "hipaa security": "HIPAA Security",
    "gdpr": "GDPR", "cmmc": "CMMC 2.0", "fedramp": "FedRAMP r5",
    "cis": "CIS CSC v8.0", "800-171": "NIST SP 800-171 r2", "171": "NIST SP 800-171 r2",
}


def _projection_frameworks(conn) -> List[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT framework FROM framework_projection ORDER BY framework")]


def _er_frameworks(conn) -> List[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT framework FROM er_mappings ORDER BY framework")]


def resolve_framework(conn, name: str) -> Optional[str]:
    """Canonical framework label, or None if unresolvable."""
    if not name:
        return None
    proj = _projection_frameworks(conn)
    er = _er_frameworks(conn)
    known = proj + [f for f in er if f not in proj]
    lower = {k.lower(): k for k in known}
    n = name.strip()
    if n in known:
        return n
    if n.lower() in lower:
        return lower[n.lower()]
    if n.lower() in _ALIASES and _ALIASES[n.lower()] in known:
        return _ALIASES[n.lower()]
    # substring
    for k in known:
        if n.lower() in k.lower() or k.lower() in n.lower():
            return k
    return None


# ── spine footprints ────────────────────────────────────────────────────────────

# edges that a human confirmation has refuted are excluded from overlap footprints
_NOT_REFUTED = "status <> 'refuted'"


def footprint_controls(conn, fw: str) -> Set[str]:
    return {r[0] for r in conn.execute(
        f"SELECT DISTINCT r5_control FROM framework_projection WHERE framework=? AND {_NOT_REFUTED}", (fw,))}


def footprint_subparts(conn, fw: str) -> Set[str]:
    """Sub-part keys a framework covers: exact sub-parts it projects to, plus, for
    control-level edges, that control's enumerated sub-parts and the whole-control
    token."""
    out: Set[str] = set()
    for (sp,) in conn.execute(
            f"SELECT DISTINCT r5_subpart FROM framework_projection WHERE framework=? AND r5_subpart IS NOT NULL AND {_NOT_REFUTED}", (fw,)):
        out.add(sp)
    # control-level edges -> expand to enumerated sub-parts + the control token
    ctrl_level = [r[0] for r in conn.execute(
        f"SELECT DISTINCT r5_control FROM framework_projection WHERE framework=? AND r5_subpart IS NULL AND {_NOT_REFUTED}", (fw,))]
    for c in ctrl_level:
        out.add(c)
        for (sp,) in conn.execute(
                "SELECT subpart_id FROM nist_subparts WHERE r5_control=? AND path<>''", (c,)):
            out.add(sp)
    return out


def footprint_ccis(conn, fw: str) -> Set[str]:
    out: Set[str] = set()
    for (cci,) in conn.execute(f"""
            SELECT DISTINCT cb.cci_id FROM framework_projection fp
            JOIN cci_bridge cb ON cb.r5_subpart = fp.r5_subpart
            WHERE fp.framework=? AND fp.r5_subpart IS NOT NULL AND fp.{_NOT_REFUTED}""", (fw,)):
        out.add(cci)
    for (cci,) in conn.execute(f"""
            SELECT DISTINCT cb.cci_id FROM framework_projection fp
            JOIN cci_bridge cb ON cb.r5_control = fp.r5_control
            WHERE fp.framework=? AND fp.r5_subpart IS NULL AND fp.{_NOT_REFUTED}""", (fw,)):
        out.add(cci)
    return out


def _er_id_set(conn, fw: str) -> Set[str]:
    """The set of evidence-request ids a framework participates in — the axis the
    ER co-occurrence fallback compares (native ids are framework-local and never
    overlap across frameworks)."""
    return {r[0] for r in conn.execute(
        "SELECT DISTINCT er_id FROM er_mappings WHERE framework=?", (fw,))}


# ── metrics + confidence ────────────────────────────────────────────────────────

def _jaccard(sa: Set[str], sb: Set[str]) -> dict:
    shared = sa & sb
    union = sa | sb
    return {
        "shared_count": len(shared),
        "a_count": len(sa),
        "b_count": len(sb),
        "union_count": len(union),
        "jaccard_pct": round(len(shared) / len(union) * 100, 1) if union else 0.0,
        "a_covers_b_pct": round(len(shared) / len(sb) * 100, 1) if sb else 0.0,
        "b_covers_a_pct": round(len(shared) / len(sa) * 100, 1) if sa else 0.0,
    }


def confidence_tier(conf: float) -> str:
    if conf >= 0.9:
        return "high"
    if conf >= 0.7:
        return "medium"
    if conf >= 0.5:
        return "low"
    return "uncertain"


def _framework_best_conf(conn, fw: str) -> Tuple[float, int]:
    row = conn.execute(
        "SELECT MAX(confidence), MIN(hop_count) FROM framework_projection WHERE framework=?",
        (fw,)).fetchone()
    conf = row[0] if row and row[0] is not None else 0.5
    hop = row[1] if row and row[1] is not None else 2
    return float(conf), int(hop)


def _pair_confidence(conn, a: str, b: str) -> Tuple[float, int]:
    """Each framework reaches the spine by its strongest edge; the joint claim is
    gated by the WEAKER of the two sides (min), with the larger hop count."""
    ca, ha = _framework_best_conf(conn, a)
    cb, hb = _framework_best_conf(conn, b)
    return min(ca, cb), max(ha, hb)


# ── per-control classification ──────────────────────────────────────────────────

def _control_footprint_subparts(conn, fw: str, native_id: str) -> Set[str]:
    out: Set[str] = set()
    rows = conn.execute("""
        SELECT r5_control, r5_subpart FROM framework_projection
        WHERE framework=? AND native_id=?""", (fw, native_id))
    for r5c, sp in rows:
        if sp:
            out.add(sp)
        else:
            out.add(r5c)
            for (s,) in conn.execute(
                    "SELECT subpart_id FROM nist_subparts WHERE r5_control=? AND path<>''", (r5c,)):
                out.add(s)
    return out


def _odp_status(conn, control_ids: Set[str], fw_a: str, fw_b: str) -> dict:
    """ODP posture for the controls a finding touches.  Only DAAPM pins values, so
    most comparisons are 'undetermined'.  Returns any pinned values for transparency."""
    if not control_ids:
        return {"status": "not_applicable"}
    qs = ",".join("?" * len(control_ids))
    vals = conn.execute(
        f"SELECT DISTINCT control_id, baseline, value_norm FROM odp_values WHERE control_id IN ({qs})",
        tuple(control_ids)).fetchall()
    if not vals:
        return {"status": "no_pinned_values"}
    by_base: Dict[str, Set[str]] = {}
    for cid, base, vnorm in vals:
        by_base.setdefault(base, set()).add(f"{cid}:{vnorm}")
    if len(by_base) < 2:
        return {"status": "undetermined",
                "note": "only one baseline pins values; the other side is unset",
                "pinned": {b: sorted(v) for b, v in by_base.items()}}
    sets = list(by_base.values())
    status = "aligned" if all(s == sets[0] for s in sets) else "divergent"
    return {"status": status, "pinned": {b: sorted(v) for b, v in by_base.items()}}


def per_control(conn, a: str, b: str, limit: int = 200) -> List[dict]:
    """Classify each of A's native controls against B's sub-part footprint."""
    sb = footprint_subparts(conn, b)
    a_natives = [r[0] for r in conn.execute(
        "SELECT DISTINCT native_id FROM framework_projection WHERE framework=? ORDER BY native_id", (a,))]
    out: List[dict] = []
    for na in a_natives:
        fa = _control_footprint_subparts(conn, a, na)
        if not fa:
            continue
        met = fa & sb
        unmet = fa - sb
        if not met:
            classification = "none"
        elif not unmet:
            classification = "full"
        else:
            classification = "partial"
        if classification == "none":
            continue  # only report where there is some correspondence
        # B natives that cover the met sub-parts (the corresponding controls)
        corresponds: Set[str] = set()
        if met:
            qs = ",".join("?" * len(met))
            for (nb,) in conn.execute(
                    f"""SELECT DISTINCT native_id FROM framework_projection
                        WHERE framework=? AND r5_subpart IN ({qs})""", (b, *sorted(met))):
                corresponds.add(nb)
        control_ids = {sp.split(" ")[0] for sp in fa}
        out.append({
            "framework_a_control": na,
            "classification": classification,
            "corresponds_to": sorted(corresponds)[:12],
            "shared_subparts": sorted(met)[:20],
            "a_unmet_subparts": sorted(unmet)[:20],
            "odp": _odp_status(conn, control_ids, a, b),
        })
        if len(out) >= limit:
            break
    # partials first, then full; deterministic
    order = {"partial": 0, "full": 1}
    out.sort(key=lambda r: (order.get(r["classification"], 2), r["framework_a_control"]))
    return out


# ── the never-error entry point ─────────────────────────────────────────────────

def compute(conn, a_in: str, b_in: str, want_per_control: bool = False,
            basis_pref: str = "auto") -> dict:
    a = resolve_framework(conn, a_in)
    b = resolve_framework(conn, b_in)
    if not a or not b:
        missing = [x for x, r in ((a_in, a), (b_in, b)) if not r]
        return {
            "tool": "overlap-query",
            "overlap_pct": None,
            "error": f"unknown framework name(s): {missing}",
            "known_frameworks": _projection_frameworks(conn) + _er_frameworks(conn),
            "human_review_required": True,
        }

    a_proj = a in set(_projection_frameworks(conn))
    b_proj = b in set(_projection_frameworks(conn))
    caveats: List[str] = []
    result_basis = None
    metrics = None
    provenance = None
    needs_conf = False

    if a_proj and b_proj:
        conf, hop = _pair_confidence(conn, a, b)
        # ladder: cci -> subpart -> control
        order = ["cci", "subpart", "control"] if basis_pref == "auto" else [basis_pref, "cci", "subpart", "control"]
        for basis in order:
            if basis == "cci":
                sa, sb = footprint_ccis(conn, a), footprint_ccis(conn, b)
            elif basis == "subpart":
                sa, sb = footprint_subparts(conn, a), footprint_subparts(conn, b)
            else:
                sa, sb = footprint_controls(conn, a), footprint_controls(conn, b)
            if sa and sb:
                metrics = _jaccard(sa, sb)
                result_basis = basis
                break
        provenance = "spine"
        needs_conf = any(
            r[0] for r in conn.execute(
                "SELECT MAX(needs_confirmation) FROM framework_projection WHERE framework IN (?,?)", (a, b)))
        if result_basis == "control":
            caveats.append("sub-part / CCI granularity unavailable for this pair; control-level basis used")
        if conf <= 0.65:
            caveats.append(f"hub-mediated mapping (confidence {conf}); parameter and sub-part precision are approximate")
    else:
        # ER fallback (inferred co-occurrence) — labeled secondary signal
        sa, sb = _er_id_set(conn, a), _er_id_set(conn, b)
        if sa and sb:
            metrics = _jaccard(sa, sb)
            result_basis = "inferred_er"
            provenance = "inferred_er_cooccurrence"
            conf = 0.5
            needs_conf = True
            caveats.append("computed from evidence-request co-occurrence, not the CCI spine")
        else:
            conf = 0.0

    if metrics is None:
        return {
            "tool": "overlap-query",
            "framework_a": a, "framework_b": b,
            "overlap_pct": 0.0, "basis": "none",
            "explanation": "no shared spine coordinates and no crosswalk path between these frameworks in current sources",
            "data_gap": {"a_on_spine": a_proj, "b_on_spine": b_proj},
            "human_review_required": True,
        }

    conf_final = conf if result_basis != "inferred_er" else 0.5
    out = {
        "tool": "overlap-query",
        "framework_a": a, "framework_b": b,
        "basis": result_basis,
        "provenance": provenance,
        "overlap_pct": metrics["jaccard_pct"],
        "a_covers_b_pct": metrics["a_covers_b_pct"],
        "b_covers_a_pct": metrics["b_covers_a_pct"],
        "shared_count": metrics["shared_count"],
        "framework_a_count": metrics["a_count"],
        "framework_b_count": metrics["b_count"],
        "confidence": confidence_tier(conf_final),
        "confidence_score": round(conf_final, 2),
        "needs_confirmation": bool(needs_conf),
        "caveats": caveats,
        "human_review_required": True,
    }
    if want_per_control and result_basis in ("cci", "subpart", "control"):
        out["per_control"] = per_control(conn, a, b)
    return out
