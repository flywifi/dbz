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

# parse_objective: 171A/53A assessment objective normalizer
check(SN.parse_objective("AC-02d.01") == [("AC-2", "d.1", None)], "obj AC-02d.01 -> d.1")
check(SN.parse_objective("CM-06b") == [("CM-6", "b", None)], "obj CM-06b -> b")
check(SN.parse_objective("AC-07a.") == [("AC-7", "a", None)], "obj AC-07a. trailing dot stripped")
check(SN.parse_objective("AC-06(01)(a)[01]") == [("AC-6(1)", "a.1", None)], "obj enh paren/bracket")
check(SN.parse_objective("SI-04(04)(b)[02]") == [("SI-4(4)", "b.2", None)], "obj SI-04(04)(b)[02]")
check(SN.parse_objective("IA-03_ODP[01]") == [("IA-3", None, "ia-03_odp.01")], "obj ODP indexed")
check(SN.parse_objective("AC-05_ODP") == [("AC-5", None, "ac-05_odp")], "obj ODP bare")
check(SN.parse_objective("AC-06(01)_ODP[01]") == [("AC-6(1)", None, "ac-06.01_odp.01")], "obj ODP enh")
check(SN.parse_objective("Withdrawn") == [], "obj Withdrawn -> empty")
check(SN.parse_objective("AC-03") == [("AC-3", None, None)], "obj bare control")
check(SN.parse_objective("") == [], "obj empty -> empty")

# oscal_control_id + parse_oscal_parts (raw OSCAL catalog walker, Phase 11)
check(SN.oscal_control_id("ac-2") == "AC-2", "oscal id ac-2 -> AC-2")
check(SN.oscal_control_id("ac-2.1") == "AC-2(1)", "oscal id ac-2.1 -> AC-2(1)")
check(SN.oscal_control_id("garbage") is None, "oscal id garbage -> None")
_OSCAL_CACHE = ROOT / "cross-mapping" / "output" / "oscal_v5.2.0_cache.json"
if _OSCAL_CACHE.exists():
    _doc = json.loads(_OSCAL_CACHE.read_text())
    _ac2 = _doc["catalog"]["groups"][0]["controls"][1]
    assert _ac2["id"] == "ac-2"
    _recs = SN.parse_oscal_parts(_ac2)
    _smt = {r["subpath"]: r for r in _recs if r["kind"] == "statement"}
    check("ac-02_odp.01" in _smt.get("c", {}).get("odp_refs", []), "AC-2 c carries ac-02_odp.01")
    check("ac-02_odp.02" in _smt.get("d.3", {}).get("odp_refs", []), "AC-2 d.3 carries ac-02_odp.02")
    _obj = {r["part_id"]: r["subpath"] for r in _recs if r["kind"] == "objective"}
    check(_obj.get("ac-2_obj.d.3-1") == "d.3", "objective leaf ac-2_obj.d.3-1 collapses to d.3")
    check(_obj.get("ac-2_obj") == "", "objective root is control-level")

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

# ── 2b. OSCAL structural + CCI XML loaders (Phase 11) ─────────────────────────
if _CACHE_OK := (ROOT / "cross-mapping" / "output" / "oscal_v5.2.0_cache.json").exists():
    oscal_links, objective_rows, oscal_stats = SL.load_oscal_structural(catalog_ids)
    check(oscal_stats["odp_links"] >= 1000, f"oscal: >=1000 odp links (got {oscal_stats['odp_links']})")
    check(oscal_stats["objectives"] >= 3000, f"oscal: >=3000 objectives (got {oscal_stats['objectives']})")
    _l = [x for x in oscal_links if x["odp_id"] == "ac-02_odp.02" and x["control_id"] == "AC-2"]
    check(_l and _l[0]["r5_subpart"] == "AC-2 d.3", "oscal links ac-02_odp.02 -> AC-2 d.3")
    check(any(o["control_id"].startswith("PT-") for o in objective_rows), "objectives cover PT family")
    check(any(o["control_id"].startswith("SR-") for o in objective_rows), "objectives cover SR family")
    # no fabricated sub-parts: every linked sub-part names its own control
    check(all((x["r5_subpart"] or "").startswith(x["control_id"]) for x in oscal_links if x["r5_subpart"]),
          "oscal odp links never cross controls")

if SL.CCI_XML_PATH.exists():
    xml_bridge, xml_disa, xml_stats = SL.load_cci_bridge_xml(catalog_ids)
    check(xml_stats["distinct_cci"] > 4000, f"cci xml: >4000 CCIs bridged (got {xml_stats['distinct_cci']})")
    check(xml_stats["distinct_controls"] > 1000, f"cci xml: >1000 controls (got {xml_stats['distinct_controls']})")
    check(xml_stats["r5_native"] > 3000, f"cci xml: >3000 native r5 rows (got {xml_stats['r5_native']})")
    _bases = {b["basis"] for b in xml_bridge}
    check(_bases == {"r5_native", "r4_identity", "appj_absorption"}, f"cci xml bases (got {_bases})")
    # App J absorption rows are control-level only (never a guessed sub-part)
    check(all(b["r5_subpart"] is None for b in xml_bridge if b["basis"] == "appj_absorption"),
          "appj_absorption rows are control-level only")
    _pt = {b["r5_control"].split("(")[0] for b in xml_bridge if b["r5_control"].startswith("PT-")}
    check(len(_pt) >= 8, f"cci xml covers all 8 PT controls (got {sorted(_pt)})")

# ── 4b. CMMC/800-171 crosswalk (Phase 2b) ─────────────────────────────────────
cmmc_edges, fedramp_odp_rows, cmmc_stats = SL.load_cmmc171_projection(catalog_ids)
check(cmmc_stats["edges"] > 0, f"cmmc171: >0 edges (got {cmmc_stats['edges']})")
check(cmmc_stats["cmmc_edges"] > 0, "cmmc171: CMMC 2.0 edges present")
check(cmmc_stats["nist171_edges"] > 0, "cmmc171: NIST SP 800-171 r2 edges present")
check(all(e["provenance"] == "cmmc171" for e in cmmc_edges), "cmmc171 edges all provenance=cmmc171")
check(all(e["confidence"] == 0.95 for e in cmmc_edges), "cmmc171 edges confidence 0.95")
check(all(e["relationship_basis"] == "source_stated" for e in cmmc_edges), "cmmc171 edges basis=source_stated")
check(all(e["needs_confirmation"] == 0 for e in cmmc_edges), "cmmc171 edges no confirmation needed")
_cmmc_rels = {e["relationship"] for e in cmmc_edges}
check("equal" in _cmmc_rels, "cmmc171: 'equal' relationship present")
check("intersect" in _cmmc_rels or "subset" in _cmmc_rels, "cmmc171: non-equal relationship present")
check(any(e["framework"] == "CMMC 2.0" and e["r5_subpart"] for e in cmmc_edges),
      "cmmc171: CMMC 2.0 projects to sub-part level")
check(any(e["framework"] == "NIST SP 800-171 r2" and e["r5_subpart"] for e in cmmc_edges),
      "cmmc171: NIST 171 projects to sub-part level")

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
    # cmmc171 edges in the DB
    n_cmmc = _c2.execute("SELECT COUNT(*) FROM framework_projection WHERE provenance='cmmc171'").fetchone()[0]
    check(n_cmmc > 0, f"DB has cmmc171 projection edges (got {n_cmmc})")
    n_stated = _c2.execute("SELECT COUNT(*) FROM framework_projection WHERE relationship_basis='source_stated'").fetchone()[0]
    check(n_stated > 0, f"DB has source_stated edges (got {n_stated})")
    # CMMC 2.0 should have both hub (0.65) and cmmc171 (0.95) edges
    cmmc_confs = set(r[0] for r in _c2.execute(
        "SELECT DISTINCT confidence FROM framework_projection WHERE framework='CMMC 2.0'").fetchall())
    check(0.95 in cmmc_confs, f"CMMC 2.0 has conf=0.95 edges (confs={cmmc_confs})")
    # ODP backfill (Phase 11): sub-part-precise links from the OSCAL parts walk,
    # control_scope stamps where the statement has no lettered parts (honest
    # granularity for most enhancements), never a fabricated sub-part.
    n_odp_linked = _c2.execute("SELECT COUNT(*) FROM control_odps WHERE r5_subpart IS NOT NULL").fetchone()[0]
    check(n_odp_linked >= 500, f"control_odps: >=500 sub-part-precise ODP links (got {n_odp_linked})")
    n_basis = _c2.execute("SELECT COUNT(*) FROM control_odps WHERE link_basis IS NOT NULL").fetchone()[0]
    check(n_basis >= 1000, f"control_odps: >=1000 rows carry link provenance (got {n_basis})")
    _sp = _c2.execute("SELECT r5_subpart FROM control_odps WHERE odp_id='ac-02_odp.02' AND control_id='AC-2'").fetchone()
    check(_sp is not None and _sp[0] == "AC-2 d.3", f"DB: ac-02_odp.02 -> AC-2 d.3 (got {_sp})")
    # assessment objectives: sub-part anchors incl. the families DISA never covered
    n_obj = _c2.execute("SELECT COUNT(*) FROM assessment_objectives").fetchone()[0]
    check(n_obj >= 3000, f"assessment_objectives: >=3000 rows (got {n_obj})")
    n_pt = _c2.execute("SELECT COUNT(*) FROM assessment_objectives WHERE control_id LIKE 'PT-%'").fetchone()[0]
    n_sr = _c2.execute("SELECT COUNT(*) FROM assessment_objectives WHERE control_id LIKE 'SR-%'").fetchone()[0]
    check(n_pt > 0 and n_sr > 0, f"objectives cover PT ({n_pt}) and SR ({n_sr})")
    # CCI bridge from the current DISA XML: coverage well past the old xlsx ceiling
    n_cci_ctrl = _c2.execute("SELECT COUNT(DISTINCT r5_control) FROM cci_bridge").fetchone()[0]
    check(n_cci_ctrl > 1000, f"cci_bridge: >1000 distinct r5 controls (got {n_cci_ctrl}, was 907)")
    _c2.close()

# ── 8. Durable ledger + health-audit detector (Phase 7) ────────────────────────
_TOOLS = ROOT / "tools"
sys.path.insert(0, str(_TOOLS))
import health_audit as HA  # type: ignore
_gold = ROOT / "skills" / "health-auditor" / "tests" / "golden"
_clean_ledger = _gold / "clean" / "ledger_clean.jsonl"
_bad_ledger = _gold / "broken" / "ledger_bad_citation.jsonl"
_orphan_conf = _gold / "broken" / "confirmation_orphan.jsonl"
_empty_conf = ROOT / "canonical-sources" / "confirmations.jsonl"  # only the schema line

_clean_findings = HA.check_uncertainty_ledger(_clean_ledger, _empty_conf)
check(not any(f["severity"] == "blocking" for f in _clean_findings), "clean ledger has no blocking findings")
_bad_findings = HA.check_uncertainty_ledger(_bad_ledger, _empty_conf)
check(any(f["severity"] == "blocking" and "citation does not resolve" in f["issue"] for f in _bad_findings),
      "unresolvable citation is blocking")
_orphan_findings = HA.check_uncertainty_ledger(_clean_ledger, _orphan_conf)
check(any(f["severity"] == "blocking" and "unknown uncertainty_id" in f["issue"] for f in _orphan_findings),
      "confirmation with no matching ledger entry is blocking")
# the real committed ledger must be clean if present
if (ROOT / "canonical-sources" / "uncertainty_ledger.jsonl").exists():
    real = HA.check_uncertainty_ledger()
    check(not any(f["severity"] == "blocking" for f in real), "committed uncertainty_ledger.jsonl is clean")

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
