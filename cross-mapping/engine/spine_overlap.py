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
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import framework_alias  # the single alias authority
from framework_alias import AmbiguousFrameworkError  # noqa: F401 (re-exported for callers)

_ALIAS_REGISTRY: Optional[dict] = None


def _alias_registry(conn) -> dict:
    global _ALIAS_REGISTRY
    if _ALIAS_REGISTRY is None:
        _ALIAS_REGISTRY = framework_alias.load_registry(conn)
    return _ALIAS_REGISTRY

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


# ── STIG technology tier (Phase 21, on-demand) ──────────────────────────────
# STIG benchmarks are a per-product implementation tier resolved live — they are
# NOT in framework_projection and never enter the precomputed matrix or the
# master surface. A `stig:<title>` pseudo-framework projects onto the 800-53
# spine via its rules' DISA CCIs through cci_bridge.

STIG_PREFIX = "stig:"
# CCI -> sub-part edges are DISA-native; the STIG side never limits confidence
# below the framework side it is compared against.
STIG_CONF = 0.95


def resolve_stig(conn, name: str):
    """('ok', stig_id) | ('ambiguous', [ids]) | ('none', None) for a stig:-prefixed
    name; ('notstig', None) when the name carries no stig: prefix."""
    if not name or not name.strip().lower().startswith(STIG_PREFIX):
        return ("notstig", None)
    q = name.strip()[len(STIG_PREFIX):].strip()
    try:
        rows = conn.execute("SELECT stig_id, title FROM stig_catalog").fetchall()
    except sqlite3.OperationalError:
        return ("none", None)
    if not q:
        return ("none", None)
    ql = q.lower()
    for sid, _t in rows:                       # exact id (case-insensitive)
        if sid.lower() == ql:
            return ("ok", sid)
    for sid, t in rows:                        # exact title
        if (t or "").lower() == ql:
            return ("ok", sid)
    subs = sorted({sid for sid, t in rows
                   if ql in sid.lower() or ql in (t or "").lower()})
    if len(subs) == 1:
        return ("ok", subs[0])
    if len(subs) > 1:
        return ("ambiguous", subs)
    return ("none", None)


def _stig_ccis(conn, stig_id: str) -> Set[str]:
    """Distinct CCI tokens the STIG's rules cite (ccis stored as sorted JSON)."""
    import json as _json
    out: Set[str] = set()
    for (blob,) in conn.execute("SELECT ccis FROM stig_rules WHERE stig_id=?", (stig_id,)):
        try:
            out.update(_json.loads(blob) or [])
        except (ValueError, TypeError):
            continue
    return out


def stig_footprint_ccis(conn, stig_id: str) -> Set[str]:
    """CCI atoms comparable to a framework's footprint_ccis: the STIG's cited CCIs
    that are anchored on the spine (present in cci_bridge). Unanchored CCIs cannot
    overlap any spine framework and are reported separately by the gap detector."""
    ccis = _stig_ccis(conn, stig_id)
    if not ccis:
        return set()
    qs = ",".join("?" * len(ccis))
    anchored = {r[0] for r in conn.execute(
        f"SELECT DISTINCT cci_id FROM cci_bridge WHERE cci_id IN ({qs})", tuple(sorted(ccis)))}
    return anchored


def stig_footprint_subparts(conn, stig_id: str) -> Set[str]:
    """r5 sub-parts (and control-level tokens, expanded) the STIG reaches through
    its CCIs — the same key space footprint_subparts uses for real frameworks."""
    ccis = _stig_ccis(conn, stig_id)
    if not ccis:
        return set()
    qs = ",".join("?" * len(ccis))
    out: Set[str] = set()
    for r5c, sp in conn.execute(
            f"SELECT DISTINCT r5_control, r5_subpart FROM cci_bridge WHERE cci_id IN ({qs})",
            tuple(sorted(ccis))):
        if sp:
            out.add(sp)
        else:
            out.add(r5c)
            for (s,) in conn.execute(
                    "SELECT subpart_id FROM nist_subparts WHERE r5_control=? AND path<>''", (r5c,)):
                out.add(s)
    return out


def stig_footprint_controls(conn, stig_id: str) -> Set[str]:
    ccis = _stig_ccis(conn, stig_id)
    if not ccis:
        return set()
    qs = ",".join("?" * len(ccis))
    return {r[0] for r in conn.execute(
        f"SELECT DISTINCT r5_control FROM cci_bridge WHERE cci_id IN ({qs})", tuple(sorted(ccis)))}


def resolve_framework(conn, name: str) -> Optional[str]:
    """Canonical framework label, or None if unresolvable."""
    if not name:
        return None
    proj = _projection_frameworks(conn)
    er = _er_frameworks(conn)
    known = proj + [f for f in er if f not in proj]
    # The shared registry decides (framework_alias): same authority as `master` and
    # `reverse`/`forward`, so one word can no longer mean different frameworks on
    # different subcommands. Declared-ambiguous terms raise instead of guessing.
    hits = framework_alias.resolve(name, known, _alias_registry(conn), surface="projection")
    if hits:
        return hits[0]
    n = name.strip()
    if n.lower() in _ALIASES and _ALIASES[n.lower()] in known:
        return _ALIASES[n.lower()]
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


# Bases whose edges represent SOURCE-STATED shared work. Everything else
# (co_membership, production_cooccurrence, co_citation, derived_cardinality) is
# topical co-reference: real association, but no source claims that doing one
# contributes to satisfying the other. See framework_vocab -> edge_semantics.
_SHARED_WORK_BASES = ("source_stated", "multi_source_consensus")

# Provenances whose PUBLISHER is an authority for the mapping (owner_direct /
# nist_stated / owner_stated tiers). NIST's OLIR exports land with
# relationship_basis=derived_cardinality because they supply no relationship TYPE,
# so filtering on basis alone would wrongly exclude NIST's own mappings.
_SHARED_WORK_PROVENANCES = (
    "cmmc171", "direct_olir", "direct_800_66", "direct_csf2",
    "direct_cprt_171r3", "direct_cprt_172r3", "olir_csf2_pair",
    "ccm_oscal", "scf_direct")


def footprint_controls_strict(conn, fw: str) -> Set[str]:
    """Spine footprint restricted to source-stated shared-work edges (phase-37).

    Phase-36 finding F-11: the shipped overlap percentage is computed from a
    projection that is ~95% co_membership, then reported as "shared audit work".
    This is the strict counterpart — it counts only what a source actually states.
    It is EXPECTED to be zero for frameworks whose projection is entirely
    hub-composed (SOC 2, CIS); a zero here means "no source states shared work for
    this pair", which is a fact worth reporting, not a failure."""
    qb = ",".join("?" * len(_SHARED_WORK_BASES))
    qp = ",".join("?" * len(_SHARED_WORK_PROVENANCES))
    return {r[0] for r in conn.execute(
        f"SELECT DISTINCT r5_control FROM framework_projection "
        f"WHERE framework=? AND {_NOT_REFUTED} "
        f"AND (relationship_basis IN ({qb}) OR provenance IN ({qp}))",
        (fw, *_SHARED_WORK_BASES, *_SHARED_WORK_PROVENANCES))}


def strict_shared_work(conn, a: str, b: str) -> dict:
    """Source-stated shared-work metrics for a pair, alongside the co-reference
    figure. Control-level basis only — the strict subset is too sparse for
    sub-part/CCI granularity to be meaningful."""
    sa, sb = footprint_controls_strict(conn, a), footprint_controls_strict(conn, b)
    m = _jaccard(sa, sb)
    return {
        "shared_work_pct": m["jaccard_pct"],
        "shared_work_shared_count": m["shared_count"],
        "shared_work_a_count": m["a_count"],
        "shared_work_b_count": m["b_count"],
        "shared_work_basis": "control (source-stated edges only)",
    }


def footprint_ccis(conn, fw: str) -> Set[str]:
    """Finest-granularity testable atoms a framework reaches: DISA CCIs plus 800-53A
    assessment-objective ids, both anchored at the sub-part (or control) level.  The
    two id spaces are disjoint (CCI-NNNNNN vs OSCAL part ids like 'pt-1_obj.a'), so
    the union is a well-defined atom footprint; objectives extend coverage into the
    families where DISA issued no CCIs (PT, SR, much of PM)."""
    out: Set[str] = set()
    atom_tables = (
        ("cci_bridge", "cci_id", "r5_control"),
        ("assessment_objectives", "objective_id", "control_id"),
    )
    for table, id_col, ctrl_col in atom_tables:
        for (atom,) in conn.execute(f"""
                SELECT DISTINCT t.{id_col} FROM framework_projection fp
                JOIN {table} t ON t.r5_subpart = fp.r5_subpart
                WHERE fp.framework=? AND fp.r5_subpart IS NOT NULL AND fp.{_NOT_REFUTED}""", (fw,)):
            out.add(atom)
        for (atom,) in conn.execute(f"""
                SELECT DISTINCT t.{id_col} FROM framework_projection fp
                JOIN {table} t ON t.{ctrl_col} = fp.r5_control
                WHERE fp.framework=? AND fp.r5_subpart IS NULL AND fp.{_NOT_REFUTED}""", (fw,)):
            out.add(atom)
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


# ── multi-source consensus corroboration (Phase 18, flag-gated tier) ────────────

# Projection label -> consensus_edges label. Mirror of the inverse of
# consensus_detector._PROJ_LABEL, kept local so this module stays stdlib+sqlite
# only (the detector needs pandas); test_spine asserts the two maps stay mutual
# inverses so they cannot drift apart silently.
_CONSENSUS_LABEL = {
    "SOC 2": "SOC 2 (TSC)",
    "ISO 27001/2 (2022)": "ISO 27001/2 (2022)",
    "HIPAA Security": "HIPAA Security",
    "GDPR": "GDPR",
    "CIS CSC v8.0": "CIS v8",
    "NIST SP 800-171 r2": "NIST SP 800-171",
    "CMMC 2.0": "CMMC 2.0",
}

# Confidence the consensus tier assigns: above the hub's 0.65 (several independent
# voters agreeing beats one hub pivot) and below owner-direct 0.95 (consensus is
# derived evidence, never an owner's own statement).
CONSENSUS_CONFIDENCE = 0.85

_CONSENSUS_FLAG = "consensus_provenance"


def consensus_support(conn, a: str, b: str) -> dict:
    """Aggregate strong-consensus corroboration for a framework pair.

    `strong_edges` counts all strong-tier consensus pairs between the two
    frameworks; `text_confirmed` counts the subset eligible to corroborate the
    confidence tier: both requirement texts on file (texts_on_file or
    texts_on_file_licensed) and a real shared spine footprint (extent is not
    atoms_disjoint / no_spine_footprint) — pending or footprint-less pairs
    never lift confidence, so coverage is never overstated."""
    fa, fb = _CONSENSUS_LABEL.get(a), _CONSENSUS_LABEL.get(b)
    if not fa or not fb or a == b:
        return {"strong_edges": 0, "text_confirmed": 0}
    try:
        rows = conn.execute("""
            SELECT text_confirmation, extent, COUNT(*) FROM consensus_edges
            WHERE tier='strong' AND ((fw_a=? AND fw_b=?) OR (fw_a=? AND fw_b=?))
            GROUP BY text_confirmation, extent""", (fa, fb, fb, fa)).fetchall()
    except sqlite3.OperationalError:  # db predates consensus_edges
        return {"strong_edges": 0, "text_confirmed": 0}
    strong = sum(n for _t, _e, n in rows)
    eligible = sum(n for t, e, n in rows
                   if t in ("texts_on_file", "texts_on_file_licensed")
                   and e not in ("atoms_disjoint", "no_spine_footprint"))
    return {"strong_edges": strong, "text_confirmed": eligible}


def _consensus_flag_effective() -> bool:
    """Query-time read of the consensus_provenance feature flag (off = default)."""
    try:
        from feature_flags import FeatureFlags  # same directory; lazy
        return FeatureFlags.load().effective(_CONSENSUS_FLAG)
    except Exception:
        return False


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

def _stig_error(kind: str, val, raw: str) -> Optional[dict]:
    """None if this side is a usable STIG; otherwise a structured error dict."""
    if kind == "ok":
        return None
    if kind == "ambiguous":
        return {"tool": "overlap-query", "overlap_pct": None,
                "error": f"ambiguous STIG name '{raw}' — {len(val)} matches",
                "candidates": val[:25], "human_review_required": True}
    if kind == "none":
        return {"tool": "overlap-query", "overlap_pct": None,
                "error": f"no STIG matches '{raw}' (use `stig --list` for titles)",
                "human_review_required": True}
    return None  # notstig — caller resolves the framework side normally


def _compute_stig(conn, a_in, b_in, a_stig, b_stig, want_per_control: bool) -> dict:
    """Overlap where at least one side is a `stig:` technology-tier pseudo-framework.
    Footprints project onto the 800-53 spine via DISA CCIs (cci_bridge). Result is
    advisory technology-tier evidence; STIGs never enter the matrix or master."""
    a_kind, a_val = a_stig
    b_kind, b_val = b_stig
    for kind, val, raw in ((a_kind, a_val, a_in), (b_kind, b_val, b_in)):
        if kind != "notstig":
            err = _stig_error(kind, val, raw)
            if err:
                return err

    def _label_and_sets(kind, val, raw):
        """(label, cci_set, subpart_set, control_set, conf) for one side."""
        if kind == "ok":
            title = conn.execute("SELECT title FROM stig_catalog WHERE stig_id=?",
                                 (val,)).fetchone()
            lbl = f"stig:{val}"
            return (lbl, stig_footprint_ccis(conn, val), stig_footprint_subparts(conn, val),
                    stig_footprint_controls(conn, val), STIG_CONF, title[0] if title else "")
        fw = resolve_framework(conn, raw)
        if not fw:
            return (None, None, None, None, None, None)
        cf, _hop = _framework_best_conf(conn, fw)
        return (fw, footprint_ccis(conn, fw), footprint_subparts(conn, fw),
                footprint_controls(conn, fw), cf, "")

    la, cci_a, sp_a, ct_a, conf_a, title_a = _label_and_sets(a_kind, a_val, a_in)
    lb, cci_b, sp_b, ct_b, conf_b, title_b = _label_and_sets(b_kind, b_val, b_in)
    if la is None or lb is None:
        missing = a_in if la is None else b_in
        return {"tool": "overlap-query", "overlap_pct": None,
                "error": f"unknown framework name: {missing}",
                "known_frameworks": _projection_frameworks(conn) + _er_frameworks(conn),
                "human_review_required": True}

    ladder = (("cci", cci_a, cci_b), ("subpart", sp_a, sp_b), ("control", ct_a, ct_b))
    result_basis, metrics = None, None
    for basis, sa, sb in ladder:
        if sa and sb:
            metrics = _jaccard(sa, sb)
            result_basis = basis
            break
    conf = min(conf_a, conf_b)
    if metrics is None:
        return {"tool": "overlap-query", "framework_a": la, "framework_b": lb,
                "overlap_pct": 0.0, "basis": "none",
                "explanation": "no shared spine coordinates: the STIG's CCIs and the "
                               "other side reach disjoint 800-53 sub-parts (or one side "
                               "has no spine footprint)",
                "provenance": "stig_cci", "human_review_required": True}
    caveats = ["technology-tier footprint projected via DISA CCIs (stig_cci); "
               "advisory implementation evidence, not an owner-stated mapping"]
    if result_basis == "control":
        caveats.append("sub-part / CCI granularity unavailable for this pair; control-level basis used")
    out = {
        "tool": "overlap-query",
        "framework_a": la, "framework_b": lb,
        "basis": result_basis,
        "provenance": "stig_cci",
        "overlap_pct": metrics["jaccard_pct"],
        "a_covers_b_pct": metrics["a_covers_b_pct"],
        "b_covers_a_pct": metrics["b_covers_a_pct"],
        "shared_count": metrics["shared_count"],
        "framework_a_count": metrics["a_count"],
        "framework_b_count": metrics["b_count"],
        "confidence": confidence_tier(conf),
        "confidence_score": round(conf, 2),
        "needs_confirmation": True,
        "relationship_basis": "stig_technology_tier",
        "caveats": caveats,
        "human_review_required": True,
    }
    return out


def compute(conn, a_in: str, b_in: str, want_per_control: bool = False,
            basis_pref: str = "auto", consensus_tier: Optional[bool] = None) -> dict:
    """`consensus_tier`: None (default) reads the `consensus_provenance` feature
    flag at query time; True/False force the tier on/off — build_db passes False
    so the precomputed overlap_matrix never depends on flag state (deterministic
    builds), and tests pass both values explicitly."""
    # STIG technology tier (on-demand): if either side is a stig:<title> handle
    # it here — STIGs are not in framework_projection, so the normal path can't
    # resolve them, and they must never enter the precomputed matrix / master.
    sa_kind, sa_val = resolve_stig(conn, a_in)
    sb_kind, sb_val = resolve_stig(conn, b_in)
    if sa_kind != "notstig" or sb_kind != "notstig":
        return _compute_stig(conn, a_in, b_in, (sa_kind, sa_val), (sb_kind, sb_val),
                             want_per_control)

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

    # Multi-source consensus corroboration (Phase 18). The support counts are
    # always reported; the confidence lift is gated by the consensus_provenance
    # flag. The tier is pair-level and confidence-only: it never adds spine atoms,
    # so every structural metric above is identical with the tier on or off. It
    # never downgrades a stronger claim (applies only below CONSENSUS_CONFIDENCE)
    # and never applies to the inferred_er fallback.
    support = consensus_support(conn, a, b)
    relationship_basis = None
    if consensus_tier is None:
        consensus_tier = _consensus_flag_effective()
    if (consensus_tier and result_basis in ("cci", "subpart", "control")
            and support["text_confirmed"] > 0 and conf < CONSENSUS_CONFIDENCE):
        conf = CONSENSUS_CONFIDENCE
        provenance = "consensus"
        relationship_basis = "multi_source_consensus"
        needs_conf = True  # corroborated, not confirmed — the cascade still applies
        caveats.append(
            f"confidence lifted by multi-source consensus ({support['text_confirmed']} "
            "strong text-confirmed consensus pairs corroborate this framework pair); "
            "individual pairs still require confirmation")

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
        "consensus_support": support,
        "caveats": caveats,
        "human_review_required": True,
    }
    # Two labeled numbers (phase-37, finding F-11): `overlap_pct` is TOPICAL
    # CO-REFERENCE — it counts every spine coordinate the two frameworks share,
    # ~95% of which come from one hub requirement citing both. `shared_work_pct`
    # counts only source-stated edges. Neither replaces the other and the
    # co-reference value is unchanged from previous releases.
    out.update(strict_shared_work(conn, a, b))
    # Disclose single-source dependency per side (phase-37, finding F-11): the audit
    # found SOC 2's projection is 100% hub-derived and HIPAA's 98%, while the caveat
    # line said only "hub-mediated". Measured per pair, never hardcoded.
    for side, fw in (("a", a), ("b", b)):
        tot = conn.execute("SELECT COUNT(*) FROM framework_projection WHERE framework=?",
                           (fw,)).fetchone()[0]
        hub = conn.execute("SELECT COUNT(*) FROM framework_projection WHERE framework=? "
                           "AND provenance='hitrust_hub'", (fw,)).fetchone()[0]
        pct = round(100.0 * hub / tot, 1) if tot else 0.0
        out[f"framework_{side}_hub_derived_pct"] = pct
        if pct >= 50.0:
            out["caveats"].append(
                f"{fw}: {pct}% of its spine footprint derives from one licensed artifact "
                f"(HITRUST CSF cross-reference), composed rather than stated by that framework's owner")
    if relationship_basis:
        out["relationship_basis"] = relationship_basis
    if want_per_control and result_basis in ("cci", "subpart", "control"):
        out["per_control"] = per_control(conn, a, b)
    return out
