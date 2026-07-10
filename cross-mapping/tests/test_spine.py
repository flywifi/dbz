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

# normalize_iso_id: ISO 27001/2:2022 canonical form across the three source dialects
check(SN.normalize_iso_id("A.05.01") == ("A.5.1", "annex_a"), "iso ER zero-padded Annex A")
check(SN.normalize_iso_id("A.5.15") == ("A.5.15", "annex_a"), "iso OLIR Annex A passthrough")
check(SN.normalize_iso_id("8.17") == ("A.8.17", "annex_a"), "iso bare above ISMS ceiling -> Annex A")
check(SN.normalize_iso_id("5.1a") == ("5.1 a", "isms_clause"), "iso HITRUST compressed sub-part")
check(SN.normalize_iso_id("10.2a1") == ("10.2 a.1", "isms_clause"), "iso HITRUST 10.2a1")
check(SN.normalize_iso_id("6.1.1e2") == ("6.1.1 e.2", "isms_clause"), "iso 3-seg + sub-part")
check(SN.normalize_iso_id("04.01") == ("4.1", "isms_clause"), "iso ER zero-padded ISMS clause")
check(SN.normalize_iso_id("06.01.01") == ("6.1.1", "isms_clause"), "iso ER 3-seg zero-padded")
check(SN.normalize_iso_id("5.1") == ("5.1", "ambiguous"), "iso bare 5.1 stays ambiguous (never guess)")
check(SN.normalize_iso_id("5.99") == (None, "unknown"), "iso beyond both ranges -> unknown")
check(SN.normalize_iso_id("garbage") == (None, "unknown"), "iso garbage -> unknown")

# TSC + PCI canonicalizers (consensus keys)
check(SN.normalize_tsc_id("AICPA 2017 CC6.1") == "CC6.1", "tsc AICPA-prefixed")
check(SN.normalize_tsc_id("cc 06.01") == "CC6.1", "tsc padded/lower")
check(SN.normalize_tsc_id("PI1.4") == "PI1.4", "tsc PI series")
check(SN.normalize_tsc_id("REQ-17") is None, "tsc rejects firm-local ids (never guess)")
check(SN.normalize_pci_id("Req 1.2.3") == "1.2.3", "pci Req prefix")
check(SN.normalize_pci_id("01.02") == "1.2", "pci zero-padded")
check(SN.normalize_pci_id("13.1") is None, "pci out-of-range top level")
check(SN.normalize_pci_id("A.8.20") is None, "pci rejects ISO ids")
# PCI DSS v4 Appendix ids (A1 multi-tenant / A2 POS TLS / A3 DESV) are real (Phase 19)
check(SN.normalize_pci_id("A3.1.1") == "A3.1.1", "pci appendix A3")
check(SN.normalize_pci_id("a1.2.3") == "A1.2.3", "pci appendix case-normalized")
check(SN.normalize_pci_id("A4.1") is None, "pci appendix only A1-A3")
check(SN.normalize_pci_id("A3") is None, "pci appendix needs a segment")
# HIPAA citation canonicalizer (Phase 19): one namespace across hub + 800-66 direct
check(SN.normalize_hipaa_citation("§ 164.308(a)(1)") == "164.308(a)(1)", "hipaa strips § prefix")
check(SN.normalize_hipaa_citation("45 CFR 164.312(e)(2)(ii)") == "164.312(e)(2)(ii)", "hipaa strips 45 CFR prefix")
check(SN.normalize_hipaa_citation("164.308(a)(1)(ii)(A)") == "164.308(a)(1)(ii)(A)", "hipaa preserves level case")
check(SN.normalize_hipaa_citation("164.308") == "164.308", "hipaa bare section ok")
check(SN.normalize_hipaa_citation("165.308") is None, "hipaa rejects non-164 parts")
check(SN.normalize_hipaa_citation("REQ-34-HIPAA") is None, "hipaa rejects firm-local ids (never guess)")

# repeated '-N' objective suffixes all strip (synthetic — no such id in current data)
_synth = {"parts": [{"id": "xx-1_obj", "name": "assessment-objective", "parts": [
    {"id": "xx-1_obj.a-1-2", "name": "assessment-objective", "prose": ""}]}]}
_srecs = {r["part_id"]: r["subpath"] for r in SN.parse_oscal_parts(_synth)}
check(_srecs.get("xx-1_obj.a-1-2") == "a", "objective id a-1-2 collapses to a (repeat suffix strip)")

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
    check(_bases == {"r5_native", "r4_identity", "appj_absorption", "legacy_r3_identity"},
          f"cci xml bases (got {_bases})")
    # Phase 22: the FULL CCI dictionary lands (every cci_item, mapped or not); only a
    # small residue is definition-only (no r5 successor), never dropped silently.
    check(xml_stats["dictionary_rows"] == xml_stats["cci_items"],
          f"every cci_item lands in disa_ccis ({xml_stats['dictionary_rows']} == {xml_stats['cci_items']})")
    check(xml_stats["cci_items"] >= 5000, f"cci dictionary >=5000 items (got {xml_stats['cci_items']})")
    check(all(d["definition"] for d in xml_disa), "every disa_ccis row carries a definition")
    check(xml_stats["definition_only"] < 100,
          f"definition-only residue is small (got {xml_stats['definition_only']})")
    # legacy_r3_identity + appj_absorption are control-level only (never a guessed sub-part)
    check(all(b["r5_subpart"] is None for b in xml_bridge
              if b["basis"] in ("appj_absorption", "legacy_r3_identity")),
          "appj_absorption + legacy_r3_identity rows are control-level only")
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
    r = SO.compute(_c, "SOC 2", "ISO 27001/2 (2022)", want_per_control=True, consensus_tier=False)
    check(r.get("basis") in ("cci", "subpart"), f"SOC2×ISO uses a spine basis (got {r.get('basis')})")
    check(40.0 <= (r.get("overlap_pct") or 0) <= 70.0, f"SOC2×ISO overlap in band (got {r.get('overlap_pct')})")
    check(r.get("needs_confirmation") is True, "SOC2×ISO (hub-mediated) needs_confirmation")
    check(r.get("confidence") == "low", f"SOC2×ISO confidence gated by weaker hub side (got {r.get('confidence')})")
    # Consensus provenance tier (Phase 18): confidence-only lift, flag-gated.
    r_on = SO.compute(_c, "SOC 2", "ISO 27001/2 (2022)", consensus_tier=True)
    _structural = ("basis", "overlap_pct", "a_covers_b_pct", "b_covers_a_pct",
                   "shared_count", "framework_a_count", "framework_b_count", "consensus_support")
    check(all(r.get(k) == r_on.get(k) for k in _structural),
          "consensus tier changes no structural metric (confidence-only)")
    _sup = r.get("consensus_support") or {}
    check(_sup.get("strong_edges", 0) > 0 and _sup.get("text_confirmed", 0) > 0,
          f"SOC2×ISO carries consensus support in both states (got {_sup})")
    check(r_on.get("confidence") == "medium" and r_on.get("confidence_score") == 0.85
          and r_on.get("provenance") == "consensus"
          and r_on.get("relationship_basis") == "multi_source_consensus"
          and r_on.get("needs_confirmation") is True,
          f"tier on: 0.85/medium, provenance consensus, still needs_confirmation "
          f"(got {r_on.get('confidence_score')}/{r_on.get('provenance')})")
    check("relationship_basis" not in r, "tier off: no relationship_basis stamped")
    # default path follows the consensus_provenance flag
    import feature_flags as FF  # type: ignore
    _flag_on = FF.FeatureFlags.load().effective("consensus_provenance")
    r_def = SO.compute(_c, "SOC 2", "ISO 27001/2 (2022)")
    check(r_def.get("confidence_score") == (r_on if _flag_on else r).get("confidence_score"),
          f"default path follows the consensus_provenance flag (flag={'on' if _flag_on else 'off'})")
    # owner-direct pairs are never downgraded by the tier
    r_cmmc = SO.compute(_c, "CMMC 2.0", "NIST SP 800-171 r2", consensus_tier=True)
    check(r_cmmc.get("confidence_score") == 0.95 and r_cmmc.get("provenance") == "spine",
          f"owner-direct 0.95 pair untouched by consensus tier (got {r_cmmc.get('confidence_score')})")
    # the local label map must stay the exact inverse of the detector's
    import consensus_detector as CD  # type: ignore
    check(SO._CONSENSUS_LABEL == {v: k for k, v in CD._PROJ_LABEL.items()},
          "spine_overlap._CONSENSUS_LABEL is the inverse of consensus_detector._PROJ_LABEL")
    _partials = [p for p in r.get("per_control", []) if p["classification"] == "partial"]
    check(_partials and _partials[0]["shared_subparts"] and _partials[0]["a_unmet_subparts"],
          "per-control partial lists both met and unmet sub-parts")
    # self-overlap = 100
    rs = SO.compute(_c, "SOC 2", "SOC 2")
    check(rs.get("overlap_pct") == 100.0, f"self-overlap is 100% (got {rs.get('overlap_pct')})")
    # unknown name -> input error
    ru = SO.compute(_c, "SOC 2", "totally-unknown-xyz")
    check(ru.get("overlap_pct") is None and "error" in ru, "unknown framework -> input error")
    # unbridged -> basis none, real zero, never raises (SOC 1 has no public
    # control layer, so no spine path and no shared ER ids with GDPR)
    rn = SO.compute(_c, "SOC 1", "GDPR")
    check(rn.get("basis") in ("none", "inferred_er") and (rn.get("overlap_pct") or 0.0) == 0.0,
          f"unbridged pair -> real zero, no error (got {rn.get('basis')}/{rn.get('overlap_pct')})")
    # PCI is on the spine since Phase 19 (bundled tier from the master crosswalk)
    rp = SO.compute(_c, "PCI DSS v4.0", "ISO 27001/2 (2022)", consensus_tier=False)
    check(rp.get("basis") in ("cci", "subpart") and (rp.get("overlap_pct") or 0) > 0,
          f"PCI×ISO uses a spine basis since Phase 19 (got {rp.get('basis')}/{rp.get('overlap_pct')})")
    check(rp.get("confidence_score") == 0.6 and rp.get("needs_confirmation") is True,
          f"PCI side gated at bundled 0.60 needs_confirmation (got {rp.get('confidence_score')})")
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
    # ISO canonical ids: no zero-padded ids anywhere; ER and projection sets join
    _iso = "ISO 27001/2 (2022)"
    n_pad = _c2.execute(
        "SELECT COUNT(*) FROM framework_projection WHERE framework=? AND native_id GLOB '*0[0-9].*'",
        (_iso,)).fetchone()[0]
    n_pad += _c2.execute(
        "SELECT COUNT(*) FROM er_mappings WHERE framework=? AND native_id GLOB '*0[0-9].*'",
        (_iso,)).fetchone()[0]
    check(n_pad == 0, f"no zero-padded ISO native ids remain (got {n_pad})")
    _shared = _c2.execute("""
        SELECT COUNT(*) FROM (
            SELECT DISTINCT native_id FROM framework_projection WHERE framework=?
            INTERSECT
            SELECT DISTINCT native_id FROM er_mappings WHERE framework=?)""",
        (_iso, _iso)).fetchone()[0]
    check(_shared > 0, f"ER and projection ISO canonical ids intersect (got {_shared}, was 0)")
    # Data feeds (Phase 14) — assert only when the source artifact is on disk,
    # so offline rebuilds without the fetched feeds still pass.
    if (ROOT / "canonical-sources" / "known_exploited_vulnerabilities.json").stat().st_size > 1000:
        n_kev = _c2.execute("SELECT COUNT(*) FROM cisa_kev").fetchone()[0]
        check(n_kev > 1000, f"cisa_kev populated from fetched KEV catalog (got {n_kev})")
    if (ROOT / "canonical-sources" / "mitre-attack-techniques.json").exists():
        n_atk = _c2.execute("SELECT COUNT(*) FROM attack_techniques").fetchone()[0]
        check(n_atk > 600, f"attack_techniques populated from ATT&CK v19 STIX (got {n_atk})")
    if (ROOT / "canonical-sources" / "cfr" / "45-cfr-164.json").exists():
        n_cfr = _c2.execute("SELECT COUNT(*) FROM cfr_requirements").fetchone()[0]
        check(n_cfr > 0, f"cfr_requirements populated from eCFR part 164 (got {n_cfr})")
    if (ROOT / "canonical-sources" / "edgar-8k-cyber.json").exists():
        n_edg = _c2.execute("SELECT COUNT(*) FROM edgar_cyber_incidents").fetchone()[0]
        check(n_edg > 0, f"edgar_cyber_incidents populated from stored 8-K data (got {n_edg})")
    # Consensus edges (Phase 16): the user's example class — SOC2(TSC)<->ISO pairs
    # carried by >=3 independent voters, with computed extent + shared spine atoms.
    n_cons = _c2.execute("SELECT COUNT(*) FROM consensus_edges WHERE tier='strong'").fetchone()[0]
    check(n_cons > 100, f"consensus: >100 strong pairs (got {n_cons})")
    n_ti = _c2.execute("""SELECT COUNT(*) FROM consensus_edges WHERE tier='strong'
        AND ((fw_a='SOC 2 (TSC)' AND fw_b='ISO 27001/2 (2022)')
          OR (fw_b='SOC 2 (TSC)' AND fw_a='ISO 27001/2 (2022)'))""").fetchone()[0]
    check(n_ti > 0, f"consensus: strong SOC2(TSC)<->ISO pairs exist (got {n_ti})")
    n_char = _c2.execute("""SELECT COUNT(*) FROM consensus_edges WHERE tier='strong'
        AND extent IS NOT NULL AND uncertainty_id IS NOT NULL""").fetchone()[0]
    check(n_char == n_cons, f"every strong pair characterized + id'd ({n_char}/{n_cons})")
    # privacy: no proprietary ids anywhere in consensus output columns
    n_leak = _c2.execute("""SELECT COUNT(*) FROM consensus_edges
        WHERE native_a GLOB '*REQ-[0-9]*' OR native_b GLOB '*REQ-[0-9]*'
           OR native_a GLOB '*ER-[0-9]*' OR native_b GLOB '*ER-[0-9]*'
           OR evidence GLOB '*REQ-[0-9]*' OR evidence GLOB '*ER-[0-9]*'""").fetchone()[0]
    check(n_leak == 0, f"consensus carries no proprietary identifiers (got {n_leak})")
    # overlap_matrix persists consensus corroboration counts (schema 3.6),
    # computed flag-independently so the build digest is deterministic.
    _om_cols = {row[1] for row in _c2.execute("PRAGMA table_info(overlap_matrix)")}
    check({"consensus_strong_edges", "consensus_text_confirmed"} <= _om_cols,
          "overlap_matrix carries consensus corroboration columns")
    _om = _c2.execute("""SELECT consensus_strong_edges, consensus_text_confirmed, confidence
        FROM overlap_matrix WHERE framework_a='ISO 27001/2 (2022)' AND framework_b='SOC 2'""").fetchone()
    check(_om is not None and _om[0] > 0 and _om[1] > 0 and _om[2] == 0.65,
          f"matrix SOC2×ISO row: consensus counts populated, confidence stays flag-off 0.65 (got {_om})")
    # ── Phase 19: master mapping surface ────────────────────────────────────────
    _fws = {r[0] for r in _c2.execute("SELECT DISTINCT framework FROM framework_projection")}
    check({"PCI DSS v4.0", "NIST CSF 2.0", "NIST SP 800-171 r3", "NIST SP 800-172 r3",
           "SCF 2026.1", "CSA CCM v4"} <= _fws
          and len(_fws) == 14, f"projection has the 14 frameworks (12 Phase 19 + SCF/CCM Phase 20, got {len(_fws)})")
    # ── Phase 20: SCF + CCM owner-stated projections ────────────────────────────
    _scf = _c2.execute("""SELECT COUNT(*), COUNT(DISTINCT native_id), MAX(confidence)
        FROM framework_projection WHERE framework='SCF 2026.1'""").fetchone()
    check(_scf[0] >= 1000 and _scf[1] >= 700 and _scf[2] == 0.80,
          f"SCF projection: >=1000 edges over >=700 controls at 0.80 (got {_scf})")
    _bad_scf = [r[0] for r in _c2.execute(
        "SELECT DISTINCT native_id FROM framework_projection WHERE framework='SCF 2026.1'")
        if not re.match(r"^[A-Z]{2,4}-\d{2}(\.\d{1,2})?$", r[0])]
    check(not _bad_scf, f"all SCF natives canonical (bad: {_bad_scf[:3]})")
    _ccm = _c2.execute("""SELECT COUNT(*), COUNT(DISTINCT native_id), MAX(confidence),
        MAX(needs_confirmation) FROM framework_projection WHERE framework='CSA CCM v4'""").fetchone()
    check(_ccm[0] >= 1600 and _ccm[1] >= 190 and _ccm[2] == 0.85 and _ccm[3] == 0,
          f"CCM projection: >=1600 source-stated edges over >=190 controls at 0.85/needs_conf=0 (got {_ccm})")
    _ccm_rels = {r[0] for r in _c2.execute(
        "SELECT DISTINCT relationship FROM framework_projection WHERE framework='CSA CCM v4'")}
    check(_ccm_rels <= {"equal", "superset"}, f"CCM relationships are CSA-stated equal/superset ({_ccm_rels})")
    # HIPAA now reaches the spine directly (800-66, NIST-stated 0.85); hub kept beneath
    _hc = _c2.execute("""SELECT MAX(confidence) FROM framework_projection
        WHERE framework='HIPAA Security'""").fetchone()[0]
    check(_hc == 0.85, f"HIPAA best path is the 800-66 direct projection at 0.85 (got {_hc})")
    _hprov = {r[0] for r in _c2.execute("""SELECT DISTINCT provenance FROM framework_projection
        WHERE framework='HIPAA Security'""")}
    check(_hprov == {"direct_800_66", "hitrust_hub"}, f"HIPAA carries both direct + hub paths ({_hprov})")
    n_para = _c2.execute("""SELECT COUNT(*) FROM framework_projection
        WHERE framework='HIPAA Security' AND native_id LIKE '§%'""").fetchone()[0]
    check(n_para == 0, f"hub HIPAA natives canonicalized (no '§ ' prefix remains, got {n_para})")
    # master_mappings populated with the tier vocabulary, no proprietary ids anywhere
    _tiers = {r[0] for r in _c2.execute("SELECT DISTINCT tier FROM master_mappings")}
    check(_tiers == {"owner_direct", "nist_stated", "owner_stated", "hub", "bundled",
                     "consensus", "production_aggregate"},
          f"master tier vocabulary exact — 7 tiers incl. owner_stated ({_tiers})")
    n_mleak = _c2.execute("""SELECT COUNT(*) FROM master_mappings
        WHERE native_a GLOB '*REQ-[0-9]*' OR native_b GLOB '*REQ-[0-9]*'
           OR native_a GLOB '*ER-[0-9]*'  OR native_b GLOB '*ER-[0-9]*'
           OR corroboration GLOB '*REQ-[0-9]*' OR corroboration GLOB '*ER-[0-9]*'
           OR source_ref GLOB '*REQ-[0-9]*' OR source_ref GLOB '*ER-[0-9]*'""").fetchone()[0]
    check(n_mleak == 0, f"master_mappings carries no proprietary identifiers (got {n_mleak})")
    # SOC 1 never appears at id level (no public control layer)
    n_soc1 = _c2.execute("""SELECT COUNT(*) FROM master_mappings
        WHERE fw_a='SOC 1' OR fw_b='SOC 1'""").fetchone()[0]
    check(n_soc1 == 0, f"SOC 1 has no id-level master rows (got {n_soc1})")
    # arbitration: a hub-won pair that consensus corroborates keeps the dissent
    n_corr = _c2.execute("""SELECT COUNT(*) FROM master_mappings
        WHERE corroboration IS NOT NULL""").fetchone()[0]
    check(n_corr > 1000, f"master keeps minority-report corroboration on >1000 pairs (got {n_corr})")
    # matrix covers the canonical union: C(16,2)=120 incl. SOC 1 + HITRUST CSF rows
    n_mx = _c2.execute("SELECT COUNT(*) FROM overlap_matrix").fetchone()[0]
    check(n_mx == 120, f"overlap_matrix covers all 120 canonical framework pairs (got {n_mx})")
    # SCF and CCM pairs compute on a spine basis
    for _pa, _pb in (("SCF 2026.1", "SOC 2"), ("CSA CCM v4", "ISO 27001/2 (2022)")):
        _row = _c2.execute("""SELECT basis, jaccard_pct FROM overlap_matrix
            WHERE (framework_a=? AND framework_b=?) OR (framework_a=? AND framework_b=?)""",
            (_pa, _pb, _pb, _pa)).fetchone()
        check(_row is not None and _row[0] in ("cci", "subpart") and (_row[1] or 0) > 0,
              f"{_pa} × {_pb} on a spine basis (got {_row})")
    _s1 = _c2.execute("""SELECT basis FROM overlap_matrix
        WHERE framework_a='SOC 1' OR framework_b='SOC 1' LIMIT 1""").fetchone()
    check(_s1 is not None and _s1[0] in ("inferred_er", "none"),
          f"SOC 1 matrix rows stay inferred_er/none (got {_s1})")
    # ── Phase 21: STIG application layer (technology tier, on-demand) ───────────
    _has_stig = _c2.execute("SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name='stig_catalog'").fetchone()
    if _has_stig:
        _sc = _c2.execute("SELECT COUNT(*), COALESCE(SUM(rule_count),0) FROM stig_catalog").fetchone()
        check(_sc[0] >= 380 and _sc[1] >= 19000,
              f"STIG catalog harvested (>=380 benchmarks, >=19000 rules; got {_sc})")
        # every stored CCI token is well-formed (never guessed)
        _badcci = _c2.execute(
            "SELECT COUNT(*) FROM stig_cci_usage WHERE cci_id NOT GLOB 'CCI-[0-9][0-9][0-9][0-9][0-9][0-9]'"
        ).fetchone()[0]
        check(_badcci == 0, f"all STIG CCI tokens match CCI-NNNNNN (bad: {_badcci})")
        # STIG-cited CCIs resolve in cci_bridge at a high rate (measured 97.6%)
        _u, _r = _c2.execute("SELECT COUNT(*), COALESCE(SUM(in_bridge),0) FROM stig_cci_usage").fetchone()
        check(_u > 0 and _r / _u >= 0.90,
              f"STIG CCIs resolve in cci_bridge >=90% (got {_r}/{_u})")
        # tech tier never leaks into the matrix / projection / master surface
        _stig_ids = {x[0] for x in _c2.execute("SELECT stig_id FROM stig_catalog")}
        _mx_fws = {x[0] for x in _c2.execute("SELECT DISTINCT framework_a FROM overlap_matrix")}
        _mx_fws |= {x[0] for x in _c2.execute("SELECT DISTINCT framework_b FROM overlap_matrix")}
        _pj_fws = {x[0] for x in _c2.execute("SELECT DISTINCT framework FROM framework_projection")}
        check(not (_stig_ids & (_mx_fws | _pj_fws)) and not any(
              str(f).startswith("stig:") for f in _mx_fws | _pj_fws),
              "STIG ids never enter overlap_matrix / framework_projection")
        # on-demand `stig:` resolver round-trips and projects a real footprint
        _sid = _c2.execute("SELECT stig_id FROM stig_catalog WHERE stig_id LIKE '%RHEL_9%' "
                           "OR stig_id LIKE '%Windows%' ORDER BY rule_count DESC LIMIT 1").fetchone()
        if _sid:
            _kind, _val = SO.resolve_stig(_c2, f"stig:{_sid[0]}")
            check(_kind == "ok" and _val == _sid[0], f"stig: resolver round-trip ({_sid[0]})")
            _fp = SO.stig_footprint_ccis(_c2, _sid[0])
            check(len(_fp) > 0, f"STIG {_sid[0]} projects a non-empty CCI footprint ({len(_fp)})")
            _ov = SO.compute(_c2, f"stig:{_sid[0]}", "FedRAMP r5")
            check(_ov.get("provenance") == "stig_cci" and _ov.get("basis") in ("cci", "subpart"),
                  f"STIG×framework overlap uses the stig_cci tech tier (got {_ov.get('provenance')})")
    # ── Phase 25: OLIR-hub composed edges (query-surface tier, contained) ───────
    _has_hub = _c2.execute("SELECT name FROM sqlite_master WHERE type='table' "
                           "AND name='olir_hub_edges'").fetchone()
    if _has_hub:
        _hc = _c2.execute("SELECT COUNT(*) FROM olir_hub_edges").fetchone()[0]
        check(_hc >= 1400, f"olir_hub_edges composed (>=1400 edges; got {_hc})")
        _hfws = {x[0] for x in _c2.execute("SELECT DISTINCT framework FROM olir_hub_edges")}
        check(_hfws == {"CIS Controls 8.1", "OWASP LLM Top 10 v2.0", "NIST SSDF v1.1"},
              f"olir_hub_edges cover the 3 net-new hub frameworks ({_hfws})")
        # every composed edge cites two DISTINCT non-empty OLIR references (no fabrication)
        _badref = _c2.execute(
            "SELECT COUNT(*) FROM olir_hub_edges WHERE source_ref_a='' OR source_ref_b='' "
            "OR source_ref_a=source_ref_b OR basis<>'olir_hub_composed'").fetchone()[0]
        check(_badref == 0, f"every olir_hub edge cites two distinct refs + olir_hub_composed basis (bad: {_badref})")
        # every reached control resolves to a real 800-53 control/enhancement
        _catset = {r[0] for r in _c2.execute("SELECT nist_id FROM controls")}
        _catset |= {r[0] for r in _c2.execute("SELECT id FROM enhancements")}
        _badctrl = sum(1 for (c,) in _c2.execute("SELECT DISTINCT r5_control FROM olir_hub_edges")
                       if c not in _catset)
        check(_badctrl == 0, f"every olir_hub r5_control resolves in the 800-53 catalog (bad: {_badctrl})")
        # containment: hub frameworks never leak into projection / matrix / master
        _pj_fws2 = {x[0] for x in _c2.execute("SELECT DISTINCT framework FROM framework_projection")}
        _mx_fws2 = {x[0] for x in _c2.execute("SELECT DISTINCT framework_a FROM overlap_matrix")}
        _mx_fws2 |= {x[0] for x in _c2.execute("SELECT DISTINCT framework_b FROM overlap_matrix")}
        check(not (_hfws & (_pj_fws2 | _mx_fws2)),
              "olir_hub frameworks never enter framework_projection / overlap_matrix")

    # ── Phase 26: FedRAMP Consolidated Rules 2026 (contained confirmation layer) ─
    _has_fr = _c2.execute("SELECT name FROM sqlite_master WHERE type='table' "
                          "AND name='fedramp_ksi'").fetchone()
    if _has_fr:
        _nk, _nf = _c2.execute(
            "SELECT COUNT(*), COUNT(DISTINCT family) FROM fedramp_ksi").fetchone()
        check(_nk == 46 and _nf == 10, f"fedramp KSI: 46 indicators / 10 families (got {_nk}/{_nf})")
        _ne = _c2.execute("SELECT COUNT(*) FROM fedramp_ksi_controls").fetchone()[0]
        check(_ne >= 370, f"fedramp KSI->800-53 edges >=370 (got {_ne})")
        _catset2 = {r[0] for r in _c2.execute("SELECT nist_id FROM controls")}
        _catset2 |= {r[0] for r in _c2.execute("SELECT id FROM enhancements")}
        _badc = sum(1 for (x,) in _c2.execute(
            "SELECT DISTINCT r5_control FROM fedramp_ksi_controls") if x not in _catset2)
        check(_badc == 0, f"every fedramp KSI r5_control resolves in the catalog (bad: {_badc})")
        # rules: pipeline vocabulary is exactly the transition dimension
        _pipes = {r[0] for r in _c2.execute("SELECT DISTINCT pipeline FROM fedramp_rules")}
        check(_pipes == {"all", "20x", "rev5"}, f"fedramp rule pipelines exact ({_pipes})")
        _nr = _c2.execute("SELECT COUNT(*) FROM fedramp_rules").fetchone()[0]
        check(_nr >= 240, f"fedramp rules >=240 leaf rules (got {_nr})")
        _no, _ng = _c2.execute("SELECT (SELECT COUNT(*) FROM fedramp_odp_pins), "
                               "(SELECT COUNT(*) FROM fedramp_ctl_guidance)").fetchone()
        check(_no == 16 and _ng == 65, f"fedramp CTL captured completely: 16 ODP pins + 65 guidance rows (got {_no}/{_ng})")
        # carry-over vs the FedRAMP r5 Moderate baseline — measured 95.2%, pinned >=90%
        _tot = _c2.execute("SELECT COUNT(DISTINCT r5_control) FROM fedramp_ksi_controls").fetchone()[0]
        _inm = _c2.execute("""
            SELECT COUNT(DISTINCT e.r5_control) FROM fedramp_ksi_controls e
            WHERE EXISTS (SELECT 1 FROM controls c WHERE c.nist_id=e.r5_control AND c.baseline_moderate=1)
               OR EXISTS (SELECT 1 FROM enhancements h WHERE h.id=e.r5_control AND h.baseline_moderate=1)
        """).fetchone()[0]
        check(_tot > 0 and _inm / _tot >= 0.90,
              f"KSI carry-over: >=90% of KSI-cited controls sit in the Moderate baseline (got {_inm}/{_tot})")
        # containment: the KSI layer never leaks; FedRAMP r5 KEEPS its matrix seat
        _mx3 = {x[0] for x in _c2.execute("SELECT DISTINCT framework_a FROM overlap_matrix")}
        _mx3 |= {x[0] for x in _c2.execute("SELECT DISTINCT framework_b FROM overlap_matrix")}
        check("FedRAMP r5" in _mx3, "FedRAMP r5 keeps its first-class matrix seat")
        _pj3 = {x[0] for x in _c2.execute("SELECT DISTINCT framework FROM framework_projection")}
        check(not any(str(fw).startswith("KSI") or "20x" in str(fw) for fw in _mx3 | _pj3),
              "KSI/20x layer never enters overlap_matrix / framework_projection")

    # label registry loaded; the in-module dicts must match it exactly
    import master_surface as MSF  # type: ignore
    _reg = {r[0]: r[2] for r in _c2.execute(
        "SELECT alias, surface, canonical FROM framework_labels")}
    check(len(_reg) > 50, f"framework_labels loaded (got {len(_reg)})")
    for _cons_label, _canon_label in MSF._CONSENSUS_TO_CANON.items():
        check(_reg.get(_cons_label, _cons_label) == _canon_label,
              f"registry agrees with master_surface for {_cons_label!r}")
    # master_surface arbitration unit behavior (synthetic)
    _mc = MSF._Claims()
    _mc.add("A", "a1", "B", "b1", provenance="hitrust_hub", relationship="intersect",
            relationship_basis="co_membership", confidence=0.65, hop_count=2,
            needs_confirmation=1, source_ref="s1")
    _mc.add("A", "a1", "B", "b1", provenance="cmmc171", relationship="equal",
            relationship_basis="source_stated", confidence=0.95, hop_count=1,
            needs_confirmation=0, source_ref="s2")
    _mrow = _mc.rows()[0]
    check(_mrow["tier"] == "owner_direct" and _mrow["relationship"] == "equal"
          and json.loads(_mrow["corroboration"])[0]["provenance"] == "hitrust_hub"
          and json.loads(_mrow["corroboration"])[0]["relationship"] == "intersect",
          "master arbitration: strongest tier wins, dissent preserved verbatim")
    try:
        _mc.add("A", "REQ-34", "B", "b1", provenance="hitrust_hub", relationship="intersect",
                relationship_basis="co_membership", confidence=0.65, hop_count=2,
                needs_confirmation=1, source_ref="s3")
        check(False, "proprietary id must raise at master assembly")
    except ValueError:
        check(True, "proprietary id refused at master assembly (raises)")
    # Licensed ISO text (Phase 17): with the Annex A verification copy on disk,
    # Annex-side strong pairs flip to texts_on_file_licensed; only ISMS-clause
    # ids (partial excerpts on file) may remain pending.
    if (ROOT / "canonical-sources" / "source_data" / "iso_combined_master_enhanced.xlsm").exists():
        import consensus_detector as CD  # type: ignore
        annex = CD.annex_text_ids()
        check(len(annex) == 93 and "5.10" in annex and "8.34" in annex,
              f"annex_text_ids recovers all 93 ISO 27001:2022 Annex A controls (got {len(annex)})")
        n_lic = _c2.execute("""SELECT COUNT(*) FROM consensus_edges WHERE tier='strong'
            AND text_confirmation='texts_on_file_licensed'""").fetchone()[0]
        check(n_lic > 0, f"consensus: ISO Annex-side strong pairs text-confirmed against licensed copy (got {n_lic})")
        n_bad = 0
        for (nid,) in _c2.execute("""SELECT CASE WHEN fw_a='ISO 27001/2 (2022)' THEN native_a ELSE native_b END
            FROM consensus_edges WHERE tier='strong' AND text_confirmation='pending_licensed_artifact'
            AND 'ISO 27001/2 (2022)' IN (fw_a, fw_b)"""):
            base = (nid[2:] if nid.startswith("A.") else nid).split(" ")[0]
            if base in annex:
                n_bad += 1
        check(n_bad == 0, f"no Annex-covered strong pair left pending (got {n_bad})")
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

# ── Phase 25: crawl-seed link-graph determinism + well-formedness ───────────────
if (ROOT / "canonical-sources" / "crawl_seeds.json").exists():
    sys.path.insert(0, str(ROOT / "tools"))
    import crawl_seed as CS  # type: ignore
    _reg = CS.load_registry()
    _a = CS.expand_seeds(_reg)
    _b = CS.expand_seeds(_reg)
    check(_a == _b and len(_a) > 0, f"crawl-seed expansion deterministic + non-empty ({len(_a)} candidates)")
    check(len({s["id"] for s in _reg["seeds"]}) == len(_reg["seeds"]), "crawl-seed ids unique")
    check(all(s.get("authority") and s.get("root") and s.get("resolver") for s in _reg["seeds"]),
          "every crawl-seed carries authority/root/resolver")

# ── report ─────────────────────────────────────────────────────────────────────
if FAILS:
    print("SPINE SELF-TEST: FAIL")
    for f in FAILS:
        print(f"  ✗ {f}")
    sys.exit(1)
# ── Anticipated-updates horizon monitor (Phase 24) ───────────────────────────
import importlib as _il
_hm = _il.import_module("horizon_monitor")
_recs = _hm.load_records()
check(len(_recs) >= 20, f"horizon registry loads ({len(_recs)} records)")
from datetime import date as _d
_dated = {"id": "t-dated", "expected_window": {"earliest": "2020-01-01", "latest": "2020-01-31", "basis": "x"},
          "escalate_after_days": 30, "status": "watching", "confidence": "high"}
_future = {"id": "t-future", "expected_window": {"earliest": "2099-01-01", "latest": "2099-01-31", "basis": "x"},
           "escalate_after_days": 30, "status": "watching", "confidence": "high"}
_undated = {"id": "t-undated", "expected_window": "no_fixed_date", "status": "watching",
            "confidence": "med", "poll_frequency": "monthly", "last_checked": None}
_mat = {"id": "t-mat", "expected_window": "no_fixed_date", "status": "materialized", "confidence": "low"}
_today = _d(2026, 7, 7)
check(_hm.classify(_dated, _today) == "overdue", "horizon: past-window record → overdue")
check(_hm.classify(_future, _today) == "watching", "horizon: future-window record → watching")
check(_hm.classify(_undated, _today) == "due_review", "horizon: undated med-confidence → due_review")
check(_hm.classify(_mat, _today) == "materialized", "horizon: materialized status preserved")
# the CCM v4.1 flagship must be present and never silently lost
check(any(r["id"] == "au-csa-ccm" for r in _recs), "horizon: CCM v4.1 mappings flagship present")

print("SPINE SELF-TEST: PASS")
print(f"  cci_bridge: {cci_stats}")
print(f"  control_odps: {odp_stats}")
print(f"  nist_subparts: {len(subparts)} rows")
sys.exit(0)
