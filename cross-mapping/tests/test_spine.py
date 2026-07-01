#!/usr/bin/env python3
"""
Deterministic self-test for the overlap spine (Phase 1+).

Independent of the auditor: asserts hand-verified expectations about the canonical
normalizers and the spine loaders against the real source data.  Run:

    python3 cross-mapping/tests/test_spine.py     # exit 0 = pass, 1 = fail

No network; stdlib + pandas/openpyxl only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "cross-mapping" / "engine"
sys.path.insert(0, str(ENGINE))

import spine_normalize as SN  # type: ignore
import spine_loader as SL     # type: ignore
import build_db as B          # type: ignore

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        FAILS.append(msg)


# ── 1. Canonical normalizer ────────────────────────────────────────────────────
check(SN.normalize_control_id("AC-01") == "AC-1", "normalize AC-01 -> AC-1")
check(SN.normalize_control_id("AC-02(01)") == "AC-2(1)", "normalize AC-02(01) -> AC-2(1)")
check(SN.normalize_control_id("AC-11 (1)") == "AC-11(1)", "normalize AC-11 (1) -> AC-11(1)")
check(SN.parse_cci_index("AC-1 a") == [("AC-1", "a")], "cci AC-1 a")
check(SN.parse_cci_index("AC-1 b 1") == [("AC-1", "b.1")], "cci AC-1 b 1 -> b.1")
check(SN.parse_cci_index("AC-2(1) b") == [("AC-2(1)", "b")], "cci enh sub-part")
check(SN.parse_cci_index("AC-1.2 (i)") == [("AC-1", None)], "cci objective form -> control-level")
check(SN.canon_subpart("AC-2", "d.1") == "AC-2 d.1", "canon_subpart join")

# ── 2. Spine loaders against the real catalog + CCI list ───────────────────────
ctrl_rows, enh_rows, param_rows, _ = B.load_catalog(B.DEFAULT_CATALOG)
catalog_ids = {r["nist_id"] for r in ctrl_rows} | {r["id"] for r in enh_rows}

bridge, disa, cci_stats = SL.load_cci_bridge(catalog_ids)
subparts = SL.load_nist_subparts(catalog_ids, bridge)
odps, odp_stats = SL.load_control_odps(param_rows)

# CCI bridge: the well-known AC-2 account-management CCIs must map to AC-2, and
# CCI-000007 must resolve to the exact sub-part AC-2 a.
ac2_ccis = {b["cci_id"] for b in bridge if b["r5_control"] == "AC-2"}
check("CCI-000007" in ac2_ccis, "CCI-000007 bridges to AC-2")
check(
    any(b["cci_id"] == "CCI-000007" and b["r5_subpart"] == "AC-2 a" for b in bridge),
    "CCI-000007 resolves to sub-part 'AC-2 a'",
)
check(cci_stats["distinct_controls"] >= 250, f"cci_bridge covers >=250 controls (got {cci_stats['distinct_controls']})")
check(cci_stats["bridge_rows"] > 3000, f"cci_bridge has >3000 rows (got {cci_stats['bridge_rows']})")

# Sub-part inventory: every catalog control is present as a whole-control row.
inv_ids = {s["subpart_id"] for s in subparts}
check("AC-2" in inv_ids, "nist_subparts contains whole-control AC-2")
check("AC-2 a" in inv_ids, "nist_subparts contains statement-part AC-2 a")

# ODP rekey: AC-2 has 10 ODPs, all canonical OSCAL ids, and every oscal-rekeyed id
# resolves to a real param insert in the OSCAL extract (no fabricated ids).
ac2_odps = [o for o in odps if o["control_id"] == "AC-2"]
check(len(ac2_odps) == 10, f"AC-2 has 10 ODPs (got {len(ac2_odps)})")
check(
    all(o["rekey_basis"] == "oscal_positional_zip" for o in ac2_odps),
    "AC-2 ODPs all rekeyed from OSCAL",
)
check(ac2_odps[0]["odp_id"] == "ac-02_odp.01", "AC-2 first ODP is ac-02_odp.01")

oscal = json.loads((ROOT / "canonical-sources" / "oscal_v5.2.0_full_extract.json").read_text())
oscal_ids = set()
for v in oscal.values():
    if isinstance(v, dict):
        oscal_ids |= set(re.findall(r"insert:\s*param,\s*([a-z0-9_.\-]+)", v.get("statement", "") or ""))
unresolved = [o["odp_id"] for o in odps if o["rekey_basis"] == "oscal_positional_zip" and o["odp_id"] not in oscal_ids]
check(not unresolved, f"all oscal-rekeyed ODP ids resolve in OSCAL ({len(unresolved)} unresolved)")

# ── 3. OLIR projection (Phase 2) ───────────────────────────────────────────────
olir_edges, olir_stats = SL.load_olir_projection(catalog_ids)
check(olir_stats["unresolved_focal"] == 0, f"OLIR: 0 unresolved focal ids (got {olir_stats['unresolved_focal']})")
check(olir_stats["edges"] > 500, f"OLIR: >500 edges (got {olir_stats['edges']})")
check(all(e["provenance"] == "direct_olir" for e in olir_edges), "OLIR edges all provenance=direct_olir")
check(all(e["relationship"] in {"equal", "subset", "superset", "intersect"} for e in olir_edges),
      "OLIR relationships derived to a valid STRM value")
check(all(e["relationship_basis"] == "derived_cardinality" for e in olir_edges),
      "OLIR relationship_basis is derived_cardinality (source states none)")
check(any(e["r5_control"] == "AC-2" and e["framework"] == SL.ISO_FRAMEWORK for e in olir_edges),
      "OLIR projects at least one ISO clause onto AC-2")

# ── 4. HITRUST hub (Phase 3) ───────────────────────────────────────────────────
hub_rows, hub_edges, hub_stats = SL.load_hitrust_hub(catalog_ids)
check(len(hub_stats["frameworks"]) >= 7, f"hub projects >=7 frameworks (got {hub_stats['frameworks']})")
check("SOC 2" in hub_stats["frameworks"], "hub projects SOC 2 (AICPA TSC)")
check(hub_stats["nist_parse_incomplete"] == 0, f"hub NIST refs all parse ({hub_stats['nist_parse_incomplete']} incomplete)")
check(all(e["provenance"] == "hitrust_hub" for e in hub_edges), "hub edges all provenance=hitrust_hub")
check(all(e["needs_confirmation"] == 1 for e in hub_edges), "hub edges flagged needs_confirmation")
check(all(e["confidence"] == 0.65 for e in hub_edges), "hub edges confidence 0.65")
check(any(e["framework"] == "SOC 2" and e["r5_control"] == "AC-2" and e["r5_subpart"] for e in hub_edges),
      "SOC 2 projects to an AC-2 sub-part via the hub")

# ── 5. ODP values + clash detection (Phase 4) ──────────────────────────────────
odpv_rows, odpv_stats = SL.load_odp_values(catalog_ids)
_by_ctrl = {}
for r in odpv_rows:
    _by_ctrl.setdefault(r["control_id"], set()).add(r["value_norm"])
check("72 hour" in _by_ctrl.get("AC-2(2)", set()), "DAAPM AC-2(2) -> 72 hour")
check("90 day" in _by_ctrl.get("AC-2(3)", set()), "DAAPM AC-2(3) -> 90 day")
check("1 year" in _by_ctrl.get("AU-11", set()), "DAAPM AU-11 -> 1 year")
check(all(r["needs_confirmation"] == 1 for r in odpv_rows), "odp_values flagged needs_confirmation")
# clash detector: divergent pair fires, agreeing pair does not, single-baseline is 0
_syn = [
    {"control_id": "AC-2(3)", "odp_id": None, "baseline": "DAAPM (DoD)", "value_norm": "90 day"},
    {"control_id": "AC-2(3)", "odp_id": None, "baseline": "FedRAMP", "value_norm": "35 day"},
    {"control_id": "AU-11", "odp_id": None, "baseline": "DAAPM (DoD)", "value_norm": "1 year"},
    {"control_id": "AU-11", "odp_id": None, "baseline": "FedRAMP", "value_norm": "1 year"},
]
_clashes = SL.detect_odp_clashes(_syn)
check(len(_clashes) == 1 and _clashes[0]["control_id"] == "AC-2(3)", "clash fires on divergent AC-2(3)")
check(SL.detect_odp_clashes(odpv_rows) == [], "single-baseline (DAAPM only) yields no clashes")

# ── 6. Overlap engine (Phase 5) — requires a built grc.db ──────────────────────
import sqlite3  # noqa: E402
_DB = ROOT / "cross-mapping" / "output" / "grc.db"
if _DB.exists():
    import spine_overlap as SO  # type: ignore
    _c = sqlite3.connect(str(_DB))
    r = SO.compute(_c, "SOC 2", "ISO 27001/2 (2022)", want_per_control=True)
    check(r.get("basis") in ("cci", "subpart"), f"SOC2×ISO uses a spine basis (got {r.get('basis')})")
    check(40.0 <= (r.get("overlap_pct") or 0) <= 70.0, f"SOC2×ISO overlap in band (got {r.get('overlap_pct')})")
    check(r.get("needs_confirmation") is True, "SOC2×ISO (hub-mediated) needs_confirmation")
    check(r.get("confidence") == "low", f"SOC2×ISO confidence gated by weaker hub side (got {r.get('confidence')})")
    _partials = [p for p in r.get("per_control", []) if p["classification"] == "partial"]
    check(_partials and _partials[0]["shared_subparts"] and _partials[0]["a_unmet_subparts"],
          "per-control partial lists both met and unmet sub-parts")
    # self-overlap = 100
    rs = SO.compute(_c, "SOC 2", "SOC 2")
    check(rs.get("overlap_pct") == 100.0, f"self-overlap is 100% (got {rs.get('overlap_pct')})")
    # unknown name -> input error
    ru = SO.compute(_c, "SOC 2", "totally-unknown-xyz")
    check(ru.get("overlap_pct") is None and "error" in ru, "unknown framework -> input error")
    # unbridged -> basis none, real zero, never raises
    rn = SO.compute(_c, "PCI DSS v4.0", "GDPR")
    check(rn.get("basis") == "none" and rn.get("overlap_pct") == 0.0, "unbridged pair -> basis:none 0.0 (no error)")
    _c.close()
else:
    print("  (skipped Phase 5 overlap checks — grc.db not built)")

# ── 7. Uncertainty ids + confirmation cascade (Phase 6) ────────────────────────
import uncertainty as UNC  # type: ignore
check(UNC.uncertainty_id("k", a=1, b=2) == UNC.uncertainty_id("k", b=2, a=1),
      "uncertainty_id is order-independent / deterministic")
_edge = {"framework": "SOC 2", "native_id": "AICPA 2017 CC6.1", "r5_subpart": "AC-2 a",
         "provenance": "hitrust_hub", "needs_confirmation": 1, "confidence": 0.65}
_uid = UNC.edge_uncertainty_id(_edge)
check(len(_uid) == 16, "edge_uncertainty_id is 16 hex")
# confirmed cascade
_edges = [dict(_edge)]
UNC.apply_confirmations_to_edges(_edges, {_uid: {"uncertainty_id": _uid, "decision": "confirmed"}})
check(_edges[0]["needs_confirmation"] == 0 and _edges[0]["confidence"] >= 0.9 and _edges[0]["status"] == "confirmed",
      "confirmed uncertainty flips needs_confirmation + lifts confidence + status=confirmed")
# refuted cascade
_edges2 = [dict(_edge)]
UNC.apply_confirmations_to_edges(_edges2, {_uid: {"uncertainty_id": _uid, "decision": "refuted"}})
check(_edges2[0]["status"] == "refuted" and _edges2[0]["confidence"] <= 0.3, "refuted uncertainty -> status refuted, conf<=0.3")
# no confirmation -> open, id stamped
_edges3 = [dict(_edge)]
UNC.apply_confirmations_to_edges(_edges3, {})
check(_edges3[0]["status"] == "open" and _edges3[0]["uncertainty_id"] == _uid, "unconfirmed edge -> status open, id stamped")
if _DB.exists():
    _c2 = sqlite3.connect(str(_DB))
    n_uid = _c2.execute("SELECT COUNT(*) FROM framework_projection WHERE uncertainty_id IS NOT NULL").fetchone()[0]
    check(n_uid > 0, "framework_projection rows carry uncertainty_id after build")
    _c2.close()

# ── report ─────────────────────────────────────────────────────────────────────
if FAILS:
    print("SPINE SELF-TEST: FAIL")
    for f in FAILS:
        print(f"  ✗ {f}")
    sys.exit(1)
print("SPINE SELF-TEST: PASS")
print(f"  cci_bridge: {cci_stats}")
print(f"  control_odps: {odp_stats}")
print(f"  nist_subparts: {len(subparts)} rows")
sys.exit(0)
