#!/usr/bin/env python3
"""
validate_spine.py — cross-validation of the overlap spine against oracles.

Higher-level than test_spine.py (which unit-tests the loaders/algorithm): this checks
the built grc.db against independent ground truth —
  1. Oracle reconciliation: the spine must find overlap where the ER oracle CSVs do.
  2. No fabricated citations: every HIPAA 45 CFR §164 section the spine emits must be a
     real HIPAA Security Rule section (validated against the official register).
  3. Provenance completeness: every projection edge traces to a source file.
  4. Ledger integrity: the committed uncertainty ledger has no blocking findings.
  5. Catalog completeness vs the NIST CPRT 5.2.0 export (independent oracle).
  6. Consensus provenance gate: the flag-gated multi_source_consensus overlap tier
     must be confidence-only (no structural drift, SOC2×ISO band held), production-
     enriched (strong >= 1.2x moderate corroboration), and ISO-oracle-covered (>=50%).
  7. Sub-part inventory completeness (control-level expansion symmetry).

Exit 0 = all reconciliations hold; 1 = a discrepancy (bridge_gap / fabrication / rot).
Requires a built grc.db (python3 cross-mapping/engine/build_db.py).
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "cross-mapping" / "output" / "grc.db"
REGISTER = ROOT / "overlap-data" / "official_hipaa_citations_register.csv"
sys.path.insert(0, str(ROOT / "tools"))

FAILS: list[str] = []
NOTES: list[str] = []


def fail(msg: str) -> None:
    FAILS.append(msg)


def note(msg: str) -> None:
    NOTES.append(msg)


def _check_cprt_oracle(conn) -> None:
    """
    Reconcile the DB's controls+enhancements against the NIST CPRT Release 5.2.0
    export (an independent NIST-generated inventory).  Any identifier present in
    CPRT but absent from the DB means the catalog is incomplete; extras in the DB
    that CPRT lacks are noted (withdrawn stubs are expected there).
    """
    sys.path.insert(0, str(ROOT / "cross-mapping" / "nist-catalog" / "ingestion"))
    sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
    try:
        from config import source_path, sheet_name, header_row, col  # type: ignore
        from spine_normalize import normalize_control_id  # type: ignore
        import pandas as pd  # type: ignore
        src = "cprt-sp800-53-5.2.0"
        path = source_path(src)
    except Exception as e:
        note(f"CPRT oracle skipped ({e})")
        return
    if not path.exists():
        note("CPRT oracle skipped (5.2.0 export not on disk)")
        return
    df = pd.read_excel(path, sheet_name=sheet_name(src), header=header_row(src))
    id_col = col(src, "nist_id")
    cprt_ids = set()
    for raw in df[id_col].dropna().astype(str):
        cid = normalize_control_id(raw.strip())
        if cid:
            cprt_ids.add(cid)
    db_ids = {r[0] for r in conn.execute("SELECT nist_id FROM controls")}
    db_ids |= {r[0] for r in conn.execute("SELECT id FROM enhancements")}
    missing = sorted(cprt_ids - db_ids)
    if missing:
        fail(f"catalog missing {len(missing)} CPRT 5.2.0 identifiers (e.g. {missing[:5]})")
    else:
        note(f"CPRT 5.2.0 oracle: all {len(cprt_ids)} identifiers present in the catalog")


def main() -> int:
    if not DB.exists():
        print("validate_spine: grc.db not built — run python3 cross-mapping/engine/build_db.py")
        return 1
    conn = sqlite3.connect(str(DB))
    sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
    import spine_overlap as SO  # type: ignore

    # 1. Oracle reconciliation — the spine must find overlap the ER oracle also finds.
    for a, b in [("SOC 2", "ISO 27001/2 (2022)"), ("SOC 2", "HIPAA Security")]:
        spine = SO.compute(conn, a, b)
        er_a = {r[0] for r in conn.execute("SELECT DISTINCT er_id FROM er_mappings WHERE framework=?", (a,))}
        er_b = {r[0] for r in conn.execute("SELECT DISTINCT er_id FROM er_mappings WHERE framework=?", (b,))}
        er_shared = len(er_a & er_b)
        sp = spine.get("overlap_pct") or 0.0
        if er_shared > 0 and sp <= 0.0:
            fail(f"bridge_gap: ER oracle finds {a}×{b} overlap ({er_shared} shared ERs) but the spine found 0")
        else:
            note(f"{a} × {b}: spine {sp}% (basis {spine.get('basis')}), ER oracle shares {er_shared} ERs")

    # 2. No fabricated 45 CFR §164 sections in the HIPAA projection.
    valid_sections = {"164.306", "164.308", "164.310", "164.312", "164.314", "164.316",
                      "164.104", "164.105", "164.318"}
    if REGISTER.exists():
        with open(REGISTER, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                m = re.search(r"164\.\d+", row.get("45_CFR_Citation", "") or "")
                if m:
                    valid_sections.add(m.group(0))
    hipaa_natives = [r[0] for r in conn.execute(
        "SELECT DISTINCT native_id FROM framework_projection WHERE framework='HIPAA Security'")]
    bad = []
    for nid in hipaa_natives:
        m = re.search(r"164\.\d+", nid)
        if m and m.group(0) not in valid_sections:
            bad.append(nid)
    if bad:
        fail(f"fabricated / unknown 45 CFR sections in HIPAA projection: {sorted(set(bad))[:5]}")
    else:
        note(f"45 CFR: {len(hipaa_natives)} HIPAA citations, all within valid Security Rule sections")

    # 3. Provenance completeness — every edge traces to a source file.
    orphan = conn.execute(
        "SELECT COUNT(*) FROM framework_projection WHERE source_file IS NULL OR source_file=''").fetchone()[0]
    if orphan:
        fail(f"{orphan} projection edges have no source_file (untraceable)")
    else:
        note("provenance: every projection edge carries a source_file")

    # 4. Ledger integrity.
    import health_audit as HA  # type: ignore
    blocking = [f for f in HA.check_uncertainty_ledger() if f["severity"] == "blocking"]
    if blocking:
        fail(f"uncertainty ledger has {len(blocking)} blocking finding(s)")
    else:
        note("ledger: committed uncertainty_ledger.jsonl clean")

    # 5. Catalog completeness vs the NIST CPRT 5.2.0 export (independent oracle).
    _check_cprt_oracle(conn)

    # 6. Consensus provenance gate — the flag-gated multi_source_consensus overlap
    # tier (spine_overlap, confidence 0.85) may be enabled only while these hold.
    # Thresholds are pinned from measured values at gate-authoring time (2026-07-03),
    # each with a margin below the observation — never invented.
    #   (a) Band preservation: the tier is confidence-only — every structural metric
    #       must be identical with the tier forced on vs off, and the SOC2×ISO
    #       overlap stays in the accepted 40–70% band.
    #   (b) ER-oracle correlation (enrichment): strong-tier consensus pairs must be
    #       production-corroborated at >=1.2x the moderate-tier rate (observed 2.3x:
    #       3.8% vs 1.6%), with >=10 corroborated strong pairs (observed 32).
    #       Measured globally: production evidence keys firm-local SOC 2 ids (never
    #       TSC), so per-pair TSC enrichment is structurally zero and meaningless.
    #   (c) ISO-side oracle coverage: the ISO ids on eligible strong consensus pairs
    #       (texts on file, real shared footprint) must cover >=50% of the ISO ids
    #       the ER production oracle co-cites with SOC 2 (observed 55.9%), and >=1
    #       eligible TSC<->ISO pair must exist (observed 8).
    _ELIGIBLE = ("tier='strong' AND text_confirmation IN ('texts_on_file','texts_on_file_licensed')"
                 " AND extent NOT IN ('atoms_disjoint','no_spine_footprint')")
    for a, b in [("SOC 2", "ISO 27001/2 (2022)"), ("SOC 2", "HIPAA Security")]:
        r_off = SO.compute(conn, a, b, consensus_tier=False)
        r_on = SO.compute(conn, a, b, consensus_tier=True)
        structural = ("basis", "overlap_pct", "a_covers_b_pct", "b_covers_a_pct",
                      "shared_count", "framework_a_count", "framework_b_count",
                      "consensus_support")
        drift = [k for k in structural if r_off.get(k) != r_on.get(k)]
        if drift:
            fail(f"consensus tier changes structural metrics for {a}×{b}: {drift}")
        sup = (r_on.get("consensus_support") or {}).get("text_confirmed", 0)
        if sup > 0 and not (r_on.get("confidence_score") == 0.85
                            and r_on.get("provenance") == "consensus"
                            and r_on.get("relationship_basis") == "multi_source_consensus"
                            and r_on.get("needs_confirmation") is True):
            fail(f"consensus tier mis-stamped for {a}×{b} "
                 f"(conf={r_on.get('confidence_score')}, prov={r_on.get('provenance')})")
        if b.startswith("ISO") and not (40.0 <= (r_on.get("overlap_pct") or 0) <= 70.0):
            fail(f"SOC2×ISO overlap out of 40–70 band with consensus tier on ({r_on.get('overlap_pct')})")
        note(f"consensus gate {a} × {b}: {sup} eligible corroborating pairs, "
             f"conf {r_off.get('confidence_score')}→{r_on.get('confidence_score')}, structural identical")
    rates = {t: (p or 0, n) for t, p, n in conn.execute(
        "SELECT tier, SUM(production_support>0), COUNT(*) FROM consensus_edges "
        "WHERE tier IN ('strong','moderate') GROUP BY tier")}
    s_prod, s_n = rates.get("strong", (0, 0))
    m_prod, m_n = rates.get("moderate", (0, 0))
    s_rate = s_prod / s_n if s_n else 0.0
    m_rate = m_prod / m_n if m_n else 0.0
    if s_prod < 10 or (m_rate > 0 and s_rate < 1.2 * m_rate):
        fail(f"consensus enrichment gate: strong {s_prod}/{s_n} ({s_rate:.1%}) vs "
             f"moderate {m_prod}/{m_n} ({m_rate:.1%}) — lift below 1.2x or <10 corroborated")
    else:
        note(f"consensus enrichment: strong {s_rate:.1%} vs moderate {m_rate:.1%} "
             f"(lift {s_rate / m_rate:.2f}x, {s_prod} corroborated strong pairs)")
    oracle_iso = set()
    for (nid,) in conn.execute(
            "SELECT DISTINCT m2.native_id FROM er_mappings m1 JOIN er_mappings m2 ON m1.er_id=m2.er_id "
            "WHERE m1.framework='SOC 2' AND m2.framework='ISO 27001/2 (2022)'"):
        oracle_iso.add((nid[2:] if nid.startswith("A.") else nid).split(" ")[0])
    cons_iso, n_tsc_pairs = set(), 0
    for fa, na, fb, nb in conn.execute(
            f"SELECT fw_a, native_a, fw_b, native_b FROM consensus_edges "
            f"WHERE {_ELIGIBLE} AND 'ISO 27001/2 (2022)' IN (fw_a, fw_b)"):
        nid = na if fa == "ISO 27001/2 (2022)" else nb
        cons_iso.add((nid[2:] if nid.startswith("A.") else nid).split(" ")[0])
        if "SOC 2 (TSC)" in (fa, fb):
            n_tsc_pairs += 1
    cov = len(oracle_iso & cons_iso) / len(oracle_iso) if oracle_iso else 0.0
    if oracle_iso and (cov < 0.50 or n_tsc_pairs < 1):
        fail(f"consensus ISO oracle coverage gate: {cov:.1%} of {len(oracle_iso)} oracle-co-cited "
             f"ISO ids covered (need >=50%), {n_tsc_pairs} eligible TSC<->ISO pairs (need >=1)")
    else:
        note(f"consensus ISO oracle coverage: {cov:.1%} of {len(oracle_iso)} co-cited ids, "
             f"{n_tsc_pairs} eligible TSC<->ISO pairs")

    # 7. Sub-part inventory completeness — every sub-part any table references
    # must be enumerable via nist_subparts (control-level expansion symmetry).
    for table in ("framework_projection", "assessment_objectives"):
        missing = conn.execute(f"""
            SELECT COUNT(DISTINCT r5_subpart) FROM {table}
            WHERE r5_subpart IS NOT NULL
              AND r5_subpart NOT IN (SELECT subpart_id FROM nist_subparts)""").fetchone()[0]
        if missing:
            fail(f"subpart inventory incomplete: {missing} sub-parts in {table} missing from nist_subparts")
        else:
            note(f"subpart inventory: all {table} sub-parts enumerated in nist_subparts")

    # 8. Master mapping surface (Phase 19) — thresholds pinned from measured values
    # at gate-authoring time (2026-07-03), each with a margin below the observation.
    #   8a Integrity: every row source-traced; (tier, provenance, confidence) triples
    #      exactly within the tier map; consensus/production rows carry no confidence.
    #   8b Leak: hard-zero proprietary-id tokens across all master text columns.
    #   8c Label round-trip: every framework label on the master surface is a
    #      registered canonical; no alias resolves to two canonicals.
    #   8d HIPAA reconciliation: the NIST 800-66 direct citations and the HITRUST
    #      hub citations must substantially agree — >=50% of hub natives appear in
    #      the direct set (observed 73.2%: 52 of 71).
    #   8e CSF2 parity: the unified concept-crosswalk pair set must be covered by
    #      the OLIR r5.2.0 projection at >=95% (observed 100%: 731/731; the
    #      projection's extra pairs come from the newer r5.2.0 revision).
    #   8f PCI on-spine: every projected PCI native re-normalizes; PCI×ISO matrix
    #      overlap > 0 on a spine basis (observed 54.0% cci).
    #   8g Matrix completeness: C(n,2) rows over the 14 canonical frameworks (91),
    #      SOC 1 rows honest (inferred_er/none).
    bad_8a = conn.execute("""SELECT COUNT(*) FROM master_mappings WHERE
        (tier='owner_direct' AND (provenance<>'cmmc171' OR confidence<>0.95)) OR
        (tier='nist_stated' AND confidence<>0.85) OR
        (tier='owner_stated' AND NOT ((provenance='ccm_oscal' AND confidence=0.85)
                                   OR (provenance='scf_direct' AND confidence=0.80))) OR
        (tier='hub' AND confidence<>0.65) OR
        (tier='bundled' AND (provenance<>'master_crosswalk' OR confidence<>0.6)) OR
        (tier IN ('consensus','production_aggregate') AND confidence IS NOT NULL) OR
        source_ref IS NULL OR source_ref=''""").fetchone()[0]
    if bad_8a:
        fail(f"master integrity: {bad_8a} rows violate the tier/provenance/confidence map")
    else:
        note("master integrity: every row source-traced with a consistent tier triple")
    n_leak = conn.execute("""SELECT COUNT(*) FROM master_mappings
        WHERE native_a GLOB '*REQ-[0-9]*' OR native_b GLOB '*REQ-[0-9]*'
           OR native_a GLOB '*ER-[0-9]*'  OR native_b GLOB '*ER-[0-9]*'
           OR corroboration GLOB '*REQ-[0-9]*' OR corroboration GLOB '*ER-[0-9]*'
           OR source_ref GLOB '*REQ-[0-9]*' OR source_ref GLOB '*ER-[0-9]*'
           OR shared_anchors GLOB '*REQ-[0-9]*' OR shared_anchors GLOB '*ER-[0-9]*'""").fetchone()[0]
    if n_leak:
        fail(f"master leak: {n_leak} rows carry provider-proprietary identifiers")
    else:
        note("master leak scan: zero proprietary identifiers")
    reg = {}
    multi = 0
    for alias, _s, canon in conn.execute("SELECT alias, surface, canonical FROM framework_labels"):
        if alias in reg and reg[alias] != canon:
            multi += 1
        reg[alias] = canon
    canonicals = {r[0] for r in conn.execute(
        "SELECT canonical FROM framework_labels WHERE surface IN ('canonical','distinct','surface_observed')")}
    master_fws = {r[0] for r in conn.execute(
        "SELECT DISTINCT fw_a FROM master_mappings UNION SELECT DISTINCT fw_b FROM master_mappings")}
    unresolved = sorted(f for f in master_fws
                        if f not in canonicals and reg.get(f, f) not in canonicals)
    if multi or unresolved:
        fail(f"master labels: {multi} multi-resolving aliases; unresolved frameworks {unresolved[:5]}")
    else:
        note(f"master labels: {len(master_fws)} surface frameworks all resolve through the registry")
    direct = {r[0] for r in conn.execute("""SELECT DISTINCT native_id FROM framework_projection
        WHERE framework='HIPAA Security' AND provenance='direct_800_66'""")}
    hub = {r[0] for r in conn.execute("""SELECT DISTINCT native_id FROM framework_projection
        WHERE framework='HIPAA Security' AND provenance='hitrust_hub'""")}
    if direct and hub:
        cov = len(direct & hub) / len(hub)
        if cov < 0.50:
            fail(f"HIPAA reconciliation: only {cov:.1%} of hub citations in the 800-66 direct set (need >=50%)")
        else:
            note(f"HIPAA reconciliation: {cov:.1%} of {len(hub)} hub citations confirmed by the 800-66 direct set")
    elif hub:
        note("HIPAA reconciliation skipped (800-66 artifact not on disk)")
    proj_csf = {(r[0], r[1]) for r in conn.execute(
        "SELECT native_id, r5_control FROM framework_projection WHERE framework='NIST CSF 2.0'")}
    uni_csf = set()
    for tid, ctrl in conn.execute(
            "SELECT DISTINCT target_id, control_id FROM unified_mappings WHERE framework='NIST CSF 2.0'"):
        fam, _, num = str(tid).rpartition("-")
        uni_csf.add((f"{fam}-{int(num)}" if num.isdigit() else tid, ctrl))
    if proj_csf and uni_csf:
        cov = len(proj_csf & uni_csf) / len(uni_csf)
        if cov < 0.95:
            fail(f"CSF2 parity: OLIR projection covers only {cov:.1%} of the concept-crosswalk pairs (need >=95%)")
        else:
            note(f"CSF2 parity: projection covers {cov:.1%} of {len(uni_csf)} concept-crosswalk pairs")
    sys.path.insert(0, str(ROOT / "cross-mapping" / "nist-catalog" / "ingestion"))
    from spine_normalize import normalize_pci_id  # type: ignore
    bad_pci = [r[0] for r in conn.execute(
        "SELECT DISTINCT native_id FROM framework_projection WHERE framework='PCI DSS v4.0'")
        if normalize_pci_id(r[0]) != r[0]]
    pci_iso = conn.execute("""SELECT jaccard_pct, basis FROM overlap_matrix
        WHERE (framework_a='ISO 27001/2 (2022)' AND framework_b='PCI DSS v4.0')
           OR (framework_a='PCI DSS v4.0' AND framework_b='ISO 27001/2 (2022)')""").fetchone()
    if bad_pci or not pci_iso or pci_iso[1] not in ("cci", "subpart") or (pci_iso[0] or 0) <= 0:
        fail(f"PCI on-spine: bad natives {bad_pci[:3]} or PCI×ISO not spine-based ({pci_iso})")
    else:
        note(f"PCI on-spine: natives canonical; PCI×ISO {pci_iso[0]}% on {pci_iso[1]} basis")
    n_mx = conn.execute("SELECT COUNT(*) FROM overlap_matrix").fetchone()[0]
    soc1_bases = {r[0] for r in conn.execute(
        "SELECT DISTINCT basis FROM overlap_matrix WHERE framework_a='SOC 1' OR framework_b='SOC 1'")}
    if n_mx != 120 or not soc1_bases <= {"inferred_er", "none"}:
        fail(f"matrix completeness: {n_mx} rows (need 120) / SOC 1 bases {soc1_bases}")
    else:
        note(f"matrix completeness: 120 canonical pairs; SOC 1 stays inferred_er/none")

    # 8i. SCF + CCM owner-stated projections (Phase 20) — thresholds pinned from
    # measured values at gate-authoring time (2026-07-03), margins below observation.
    #   (a) CCM cross-artifact id check: every projected CCM native must resolve in
    #       the v4.0.13 xlsx Control ID column at >=95% (observed 100%: 195/195).
    #   (b) SCF cross-source agreement: the projected SCF ids and the master
    #       crosswalk's SCF column (independent compilations citing the same
    #       framework) must agree at >=90% of projected ids (observed 98.5%).
    #   Containment spot-checks for CCM 'equal' claims are NOT gated: both sides
    #   are control-level (no sub-part footprints), so an atoms-based check would
    #   be vacuous — recorded as an honest limit, not a green light.
    proj_ccm = {r[0] for r in conn.execute(
        "SELECT DISTINCT native_id FROM framework_projection WHERE framework='CSA CCM v4'")}
    if proj_ccm:
        try:
            from config import source_path as _sp  # type: ignore
            import pandas as _pd  # type: ignore
            _ccm_df = _pd.read_excel(
                _sp("csa-ccm-v4.0.13"), sheet_name="CCM", header=2)
            _idc = next(c2 for c2 in _ccm_df.columns if str(c2).strip() == "Control ID")
            xlsx_ids = {str(v).strip() for v in _ccm_df[_idc].dropna()}
            cov = len(proj_ccm & xlsx_ids) / len(proj_ccm)
            if cov < 0.95:
                fail(f"CCM id oracle: only {cov:.1%} of projected CCM natives resolve in the v4.0.13 xlsx (need >=95%)")
            else:
                note(f"CCM id oracle: {cov:.1%} of {len(proj_ccm)} projected natives resolve in the v4.0.13 xlsx")
        except Exception as e:
            note(f"CCM id oracle skipped ({e})")
    proj_scf = {r[0] for r in conn.execute(
        "SELECT DISTINCT native_id FROM framework_projection WHERE framework='SCF 2026.1'")}
    if proj_scf:
        master_path = ROOT / "canonical-sources" / "crosswalk_80053_master.json"
        if master_path.exists():
            with open(master_path, encoding="utf-8") as f:
                _mj = json.load(f)
            master_scf = {str(t).strip().upper() for cols in _mj["map"].values()
                          for t in (cols.get("SCF") or [])}
            agree = len(proj_scf & master_scf) / len(proj_scf)
            if agree < 0.90:
                fail(f"SCF cross-source agreement: only {agree:.1%} of projected SCF ids in the master crosswalk column (need >=90%)")
            else:
                note(f"SCF cross-source agreement: {agree:.1%} of {len(proj_scf)} projected ids confirmed by the master crosswalk")

    # 9. STIG application layer (Phase 21) — CCI application evidence.
    #   The STIG layer's purpose is CCI usage evidence, not a complete STIG
    #   registry. Guarded on the artifact: absent stig tables → skipped (offline).
    #   (a) STIG-cited CCIs resolve in cci_bridge at >= a pinned rate (measured
    #       97.6%; pin 90%) — high resolution proves the harvest keys the same CCI
    #       space as the bridge; the small unresolved remainder is surfaced.
    #   (b) unresolved (STIG-cited, not in cci_bridge) CCIs are counted + noted —
    #       informational gap detector (STIG releases can lead the CCI list).
    #   (c) catalog↔rules consistency: SUM(rule_count) == COUNT(stig_rules) and no
    #       per-STIG mismatch (build integrity).
    #   (d) the tech tier did not leak: STIG ids never appear in framework_projection
    #       / overlap_matrix / master_mappings.
    have_stig = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stig_catalog'").fetchone()
    n_stig = conn.execute("SELECT COUNT(*) FROM stig_catalog").fetchone()[0] if have_stig else 0
    if not have_stig or n_stig == 0:
        note("STIG layer: skipped (no stig_catalog artifact)")
    else:
        n_rules = conn.execute("SELECT COUNT(*) FROM stig_rules").fetchone()[0]
        n_used = conn.execute("SELECT COUNT(*) FROM stig_cci_usage").fetchone()[0]
        n_res = conn.execute("SELECT COUNT(*) FROM stig_cci_usage WHERE in_bridge=1").fetchone()[0]
        n_unres = n_used - n_res
        resolve_pct = (n_res / n_used * 100) if n_used else 0.0
        # (a) resolution rate
        if resolve_pct < 90.0:
            fail(f"STIG CCI resolution: only {resolve_pct:.1f}% of STIG-cited CCIs resolve "
                 f"in cci_bridge (need >=90%)")
        else:
            note(f"STIG CCI resolution: {resolve_pct:.1f}% of {n_used} STIG-cited CCIs "
                 f"resolve in cci_bridge ({n_stig} benchmarks, {n_rules} rules)")
        # (b) gap detector — informational, never a fail
        if n_unres:
            note(f"STIG CCI gap detector: {n_unres} STIG-cited CCIs absent from cci_bridge "
                 "(DISA list lag or r4-only — informational, never dropped)")
        # (c) catalog<->rules consistency
        sum_rc = conn.execute("SELECT COALESCE(SUM(rule_count),0) FROM stig_catalog").fetchone()[0]
        n_mismatch = conn.execute("""
            SELECT COUNT(*) FROM stig_catalog c
            JOIN (SELECT stig_id, COUNT(*) n FROM stig_rules GROUP BY stig_id) r
              ON c.stig_id=r.stig_id WHERE c.rule_count<>r.n""").fetchone()[0]
        if sum_rc != n_rules or n_mismatch:
            fail(f"STIG catalog/rules inconsistency: SUM(rule_count)={sum_rc} vs "
                 f"COUNT(stig_rules)={n_rules}, {n_mismatch} per-STIG mismatches")
        else:
            note(f"STIG catalog/rules consistency: {n_rules} rules reconcile exactly")
        # (d) tech-tier isolation: STIG ids must never enter the master surface
        stig_ids = {r[0] for r in conn.execute("SELECT stig_id FROM stig_catalog")}
        leak = 0
        for tbl, cols in (("framework_projection", ["framework", "native_id"]),
                          ("overlap_matrix", ["framework_a", "framework_b"]),
                          ("master_mappings", ["fw_a", "fw_b"])):
            for col_ in cols:
                vals = {r[0] for r in conn.execute(f"SELECT DISTINCT {col_} FROM {tbl}")}
                leak += len(vals & stig_ids)
                leak += sum(1 for v in vals if isinstance(v, str) and v.startswith("stig:"))
        if leak:
            fail(f"STIG tech-tier leak: {leak} STIG ids found in matrix/projection/master")
        else:
            note("STIG tech-tier isolation: no STIG ids in framework_projection / "
                 "overlap_matrix / master_mappings")

    # 10. CCI dictionary completeness + mapping corroboration (Phase 22).
    #   (a) every CCI in the source XML lands in disa_ccis with a definition — no
    #       silent drops (the pre-Phase-22 loader dropped 587 definitions).
    #   (b) no fabricated bridge edge: every cci_bridge row carries a known basis and
    #       traces to the CCI source file; legacy_r3/appj rows are control-level only.
    #   (c) corroboration verdicts are exhaustive + divergences are enumerated, not hidden.
    have_cci = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name='cci_mapping_corroboration'").fetchone()
    if not have_cci:
        note("CCI enrichment: skipped (no corroboration table)")
    else:
        sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
        try:
            import spine_loader as _sl  # type: ignore
            src_items = None
            if _sl.CCI_XML_PATH.exists():
                import xml.etree.ElementTree as _ET
                _r = _ET.parse(str(_sl.CCI_XML_PATH)).getroot()
                _ns = _r.tag.split("}")[0].strip("{") if "}" in _r.tag else ""
                src_items = sum(1 for _ in _r.iter(f"{{{_ns}}}cci_item" if _ns else "cci_item"))
        except Exception as e:
            src_items = None
            note(f"CCI source count unavailable ({e})")
        n_dict = conn.execute("SELECT COUNT(*) FROM disa_ccis").fetchone()[0]
        n_nodef = conn.execute("SELECT COUNT(*) FROM disa_ccis WHERE definition IS NULL OR definition=''").fetchone()[0]
        if src_items is not None and n_dict != src_items:
            fail(f"CCI dictionary incomplete: {n_dict} loaded vs {src_items} in source XML")
        elif n_nodef:
            fail(f"CCI definitions missing: {n_nodef} disa_ccis rows have no definition")
        else:
            note(f"CCI dictionary complete: {n_dict} CCIs, every one with a definition"
                 + (f" (== source {src_items})" if src_items else ""))
        # (b) no fabricated edges
        bad_basis = conn.execute(
            "SELECT COUNT(*) FROM cci_bridge WHERE basis NOT IN "
            "('r5_native','r4_identity','appj_absorption','legacy_r3_identity','xlsx_legacy')"
        ).fetchone()[0]
        ctl_leak = conn.execute(
            "SELECT COUNT(*) FROM cci_bridge WHERE basis IN ('appj_absorption','legacy_r3_identity') "
            "AND r5_subpart IS NOT NULL").fetchone()[0]
        if bad_basis or ctl_leak:
            fail(f"CCI bridge integrity: {bad_basis} unknown-basis rows, "
                 f"{ctl_leak} control-level bases with a guessed sub-part")
        else:
            note("CCI bridge integrity: all edges carry a known basis; recovered/absorption "
                 "edges are control-level only (no guessed sub-parts)")
        # (c) corroboration exhaustive + confirmation summary
        vd = dict(conn.execute(
            "SELECT verdict, COUNT(*) FROM cci_mapping_corroboration GROUP BY verdict").fetchall())
        bad_v = conn.execute(
            "SELECT COUNT(*) FROM cci_mapping_corroboration WHERE verdict NOT IN "
            "('confirmed','disa_only','candidate')").fetchone()[0]
        if bad_v:
            fail(f"CCI corroboration: {bad_v} rows with an unknown verdict")
        else:
            note(f"CCI corroboration: {vd.get('confirmed',0)} confirmed / "
                 f"{vd.get('disa_only',0)} disa-only / {vd.get('candidate',0)} candidate-gain "
                 "(acasehs+trackr are derived republications — transcription/gap witnesses, "
                 "not independent authority)")

    # 11. Anticipated-updates horizon registry well-formedness (Phase 24).
    #   Every record must carry authority/artifact/trigger/detection, a valid status +
    #   confidence, an expected_window that is EITHER "no_fixed_date" OR a {earliest,latest}
    #   with real ISO dates (no fabricated dates), and any dependent_of must resolve.
    have_au = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                           "AND name='anticipated_updates'").fetchone()
    if not have_au:
        note("anticipated-updates: skipped (no table)")
    else:
        import json as _json
        from datetime import date as _date
        rows = conn.execute("SELECT id, authority, artifact, trigger_signal, detection, "
                            "expected_window, status, confidence, dependent_of FROM anticipated_updates").fetchall()
        ids = {r[0] for r in rows}
        bad = []
        STATUS = {"watching", "draft_observed", "materialized", "superseded"}
        CONF = {"high", "med", "low"}
        for rid, auth, art, trig, det, win, status, conf, dep in rows:
            if not (auth and art and trig):
                bad.append(f"{rid}: missing authority/artifact/trigger")
            try:
                d = _json.loads(det) if det else {}
                if not d.get("url") and not d.get("method"):
                    bad.append(f"{rid}: empty detection")
            except Exception:
                bad.append(f"{rid}: unparseable detection")
            if status not in STATUS:
                bad.append(f"{rid}: bad status {status!r}")
            if conf not in CONF:
                bad.append(f"{rid}: bad confidence {conf!r}")
            try:
                w = _json.loads(win)
            except Exception:
                w = None
            if w == "no_fixed_date":
                pass
            elif isinstance(w, dict) and w.get("earliest") and w.get("latest"):
                try:  # dates must be real ISO — never fabricated/garbage
                    _date.fromisoformat(w["earliest"]); _date.fromisoformat(w["latest"])
                except ValueError:
                    bad.append(f"{rid}: non-ISO expected_window")
            else:
                bad.append(f"{rid}: expected_window neither no_fixed_date nor {{earliest,latest}}")
            if dep and dep not in ids:
                bad.append(f"{rid}: dependent_of {dep!r} does not resolve")
        if bad:
            fail("anticipated-updates malformed: " + "; ".join(bad[:8]))
        else:
            note(f"anticipated-updates horizon: {len(rows)} records well-formed "
                 "(status/confidence/detection valid; every window is no_fixed_date or real ISO dates; "
                 "no fabricated dates; dependencies resolve)")

    # 12. OLIR-hub composed edges (Phase 25) — no fabrication + containment.
    #   Every third-party -> CSF2 -> 800-53 edge must cite TWO distinct real OLIR
    #   references, resolve to a real 800-53 control, and the hub frameworks must
    #   never leak into framework_projection / overlap_matrix (query-surface tier).
    have_hub = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                            "AND name='olir_hub_edges'").fetchone()
    if not have_hub:
        note("olir-hub composed edges: skipped (no table)")
    else:
        hub = conn.execute("SELECT framework, native_id, r5_control, basis, "
                           "source_ref_a, source_ref_b FROM olir_hub_edges").fetchall()
        cat = {r[0] for r in conn.execute("SELECT nist_id FROM controls")}
        cat |= {r[0] for r in conn.execute("SELECT id FROM enhancements")}
        pj = {r[0] for r in conn.execute("SELECT DISTINCT framework FROM framework_projection")}
        mx = {r[0] for r in conn.execute("SELECT DISTINCT framework_a FROM overlap_matrix")}
        mx |= {r[0] for r in conn.execute("SELECT DISTINCT framework_b FROM overlap_matrix")}
        hub_fws = {r[0] for r in hub}
        hbad = []
        for fw, nat, ctrl, basis, ra, rb in hub:
            if not (ra and rb) or ra == rb:
                hbad.append(f"{fw}:{nat}->{ctrl}: refs not two-distinct")
            if basis != "olir_hub_composed":
                hbad.append(f"{fw}:{nat}: basis {basis!r}")
            if ctrl not in cat:
                hbad.append(f"{fw}:{nat}: {ctrl} not in catalog")
        leak = hub_fws & (pj | mx)
        if hbad:
            fail("olir-hub edges malformed: " + "; ".join(hbad[:8]))
        elif leak:
            fail(f"olir-hub frameworks leaked into projection/matrix: {sorted(leak)}")
        else:
            note(f"olir-hub composed edges: {len(hub)} edges across {len(hub_fws)} frameworks "
                 "(every edge cites two distinct OLIR refs; controls resolve; "
                 "frameworks stay out of projection/matrix — query-surface tier)")

    # 13. FedRAMP Consolidated Rules 2026 (Phase 26) — source-tracing + containment.
    #   Every KSI edge must carry basis='fedramp_stated' (FedRAMP's own published mapping),
    #   a well-formed indicator id that exists in fedramp_ksi, and a catalog-resolving
    #   control; statuses/lifecycle in enum; ODP pins well-formed; FedRAMP r5 keeps its
    #   matrix seat while the KSI layer stays out of projection/matrix.
    have_fr = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                           "AND name='fedramp_ksi'").fetchone()
    if not have_fr:
        note("fedramp consolidated rules: skipped (no table)")
    else:
        import re as _re
        _KSI_RE = _re.compile(r"^KSI-[A-Z]{3}-[A-Z0-9]{2,4}$")
        cat13 = {r[0] for r in conn.execute("SELECT nist_id FROM controls")}
        cat13 |= {r[0] for r in conn.execute("SELECT id FROM enhancements")}
        ksis = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT indicator_id, status, lifecycle FROM fedramp_ksi")}
        fbad = []
        for iid, (st, lc) in ksis.items():
            if not _KSI_RE.match(iid):
                fbad.append(f"malformed indicator id {iid}")
            if st not in ("stable", "placeholder"):
                fbad.append(f"{iid}: status {st!r} outside enum")
            if lc != "2026_public_preview":
                fbad.append(f"{iid}: lifecycle {lc!r}")
        for iid, ctrl, basis in conn.execute(
                "SELECT indicator_id, r5_control, basis FROM fedramp_ksi_controls"):
            if iid not in ksis:
                fbad.append(f"edge {iid}->{ctrl}: orphan indicator")
            if ctrl not in cat13:
                fbad.append(f"edge {iid}->{ctrl}: control not in catalog")
            if basis != "fedramp_stated":
                fbad.append(f"edge {iid}->{ctrl}: basis {basis!r}")
        for pid, src in conn.execute("SELECT parameter_id, source FROM fedramp_odp_pins"):
            if "_odp" not in pid or src != "fedramp_ctl_2026":
                fbad.append(f"odp pin {pid}/{src} malformed")
        mx13 = {r[0] for r in conn.execute("SELECT DISTINCT framework_a FROM overlap_matrix")}
        mx13 |= {r[0] for r in conn.execute("SELECT DISTINCT framework_b FROM overlap_matrix")}
        pj13 = {r[0] for r in conn.execute("SELECT DISTINCT framework FROM framework_projection")}
        if "FedRAMP r5" not in mx13:
            fbad.append("FedRAMP r5 lost its matrix seat")
        if any(str(fw).startswith("KSI") or "20x" in str(fw) for fw in mx13 | pj13):
            fbad.append("KSI/20x layer leaked into projection/matrix")
        if fbad:
            fail("fedramp consolidated rules malformed: " + "; ".join(fbad[:8]))
        else:
            n_e = conn.execute("SELECT COUNT(*) FROM fedramp_ksi_controls").fetchone()[0]
            note(f"fedramp consolidated rules: {len(ksis)} KSIs / {n_e} fedramp_stated edges "
                 "(all controls resolve; statuses+lifecycle in enum; ODP pins well-formed; "
                 "FedRAMP r5 keeps its matrix seat; KSI layer contained)")

    # 14. Evidence-state ladder (Phase 29) — derivation consistent + vocabulary exact.
    ev_counts = dict(conn.execute(
        "SELECT evidence_state, COUNT(*) FROM master_mappings GROUP BY 1"))
    ebad = []
    valid_states = {"oracle_confirmed", "cross_validated", "columns_aligned",
                    "asserted_by_source"}
    if set(ev_counts) - valid_states:
        ebad.append(f"unknown states {sorted(set(ev_counts) - valid_states)}")
    n_null = conn.execute("SELECT COUNT(*) FROM master_mappings "
                          "WHERE evidence_state IS NULL OR evidence_state=''").fetchone()[0]
    if n_null:
        ebad.append(f"{n_null} rows without a state")
    # monotonic sanity: a directly-stated tier is never asserted_by_source
    n_mono = conn.execute(
        "SELECT COUNT(*) FROM master_mappings WHERE tier IN "
        "('owner_direct','nist_stated','owner_stated','hub') "
        "AND evidence_state='asserted_by_source'").fetchone()[0]
    if n_mono:
        ebad.append(f"{n_mono} directly-stated edges downgraded to asserted_by_source")
    # independent recomputation over a deterministic sample (first 500 rows by PK)
    n_mismatch = 0
    for (tier, votes, prod, corr, state) in conn.execute(
            "SELECT tier, votes, production_support, corroboration, evidence_state "
            "FROM master_mappings ORDER BY fw_a, native_a, fw_b, native_b LIMIT 500"):
        n_corr = len(json.loads(corr)) if corr else 0
        if (prod or 0) >= 1 or tier == "production_aggregate":
            want = "oracle_confirmed"
        elif n_corr >= 1 or (votes or 0) >= 2:
            want = "cross_validated"
        elif tier in ("owner_direct", "nist_stated", "owner_stated", "hub"):
            want = "columns_aligned"
        else:
            want = "asserted_by_source"
        if want != state:
            n_mismatch += 1
    if n_mismatch:
        ebad.append(f"{n_mismatch}/500 sampled rows disagree with the independent derivation")
    if ebad:
        fail("evidence-state ladder malformed: " + "; ".join(ebad[:6]))
    else:
        note(f"evidence-state ladder: {sum(ev_counts.values())} rows across "
             f"{len(ev_counts)} states {dict(sorted(ev_counts.items()))} "
             "(vocabulary exact; monotonic; 500-row independent recomputation matches)")

    # 15. Edge-semantic model (Phase 37, schema 3.15) — what an edge CLAIMS.
    #     Phase-36 finding F-10: weak "relates to" links were stored identically to
    #     strong "satisfies" links and then reported as shared audit work. The class is
    #     derived mechanically, so this check asserts the derivation is TOTAL (every row
    #     classified), SINGLE-VALUED (vocabulary exact), and independently reproducible.
    sbad = []
    with open(ROOT / "canonical-sources" / "framework_vocab.json", encoding="utf-8") as f:
        _vocab_sem = json.load(f).get("edge_semantics", {}).get("classes", {})
    allowed = set(_vocab_sem)
    if not allowed:
        sbad.append("framework_vocab.json declares no edge_semantics.classes")
    sem_counts = dict(conn.execute(
        "SELECT edge_semantic, COUNT(*) FROM master_mappings GROUP BY 1").fetchall())
    unknown = set(sem_counts) - allowed
    if unknown:
        sbad.append(f"undeclared edge_semantic value(s): {sorted(unknown)}")
    n_null = conn.execute(
        "SELECT COUNT(*) FROM master_mappings WHERE edge_semantic IS NULL "
        "OR TRIM(edge_semantic)=''").fetchone()[0]
    if n_null:
        sbad.append(f"{n_null} rows without an edge_semantic (derivation not total)")
    # a co_membership edge must NEVER be classified as shared work — that is the exact
    # conflation F-10 recorded
    n_conflate = conn.execute(
        "SELECT COUNT(*) FROM master_mappings WHERE relationship_basis='co_membership' "
        "AND edge_semantic IN ('equivalent','supports') "
        "AND tier NOT IN ('owner_direct','nist_stated','owner_stated')").fetchone()[0]
    if n_conflate:
        sbad.append(f"{n_conflate} co_membership edges classified as shared work (F-10 regression)")
    # independent recomputation over a deterministic sample
    n_mis = 0
    for (basis, rel, sem, tier) in conn.execute(
            "SELECT relationship_basis, relationship, edge_semantic, tier FROM master_mappings "
            "ORDER BY fw_a, native_a, fw_b, native_b LIMIT 500"):
        if tier in ("owner_direct", "nist_stated", "owner_stated") or basis == "source_stated":
            want = "equivalent" if rel == "equal" else "supports"
        elif basis == "multi_source_consensus":
            want = "supports"
        elif basis in ("co_membership", "production_cooccurrence"):
            want = "co_referenced"
        else:
            want = "informs"
        if want != sem:
            n_mis += 1
    if n_mis:
        sbad.append(f"{n_mis}/500 sampled rows disagree with the independent derivation")
    if sbad:
        fail("edge-semantic model malformed: " + "; ".join(sbad[:6]))
    else:
        shared = sum(n for s, n in sem_counts.items()
                     if _vocab_sem.get(s, {}).get("counts_as_shared_work"))
        tot_sem = sum(sem_counts.values())
        note(f"edge-semantic model: {tot_sem} rows across {len(sem_counts)} classes "
             f"{dict(sorted(sem_counts.items()))}; {shared} ({100*shared/tot_sem:.1f}%) count as "
             "shared work (vocabulary exact; total; 500-row independent recomputation matches)")

    # 16. Auditability floor (Phase 37) — phase-36 finding F-6 measured that the hub
    #     block (82,825 rows) could be checked against an authority on 52 native ids
    #     total, because the two sides wrote ids in different dialects. This pins the
    #     recovered auditability so it cannot silently regress.
    #
    #     Join rule: EXACT ids first; fall back to the coarse corroboration key only when
    #     exact sharing is weaker. Coarsening is lossy (it helps ISO/CMMC but discards
    #     real precision for 800-171 and HIPAA), so it is a fallback, never a default.
    sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
    from spine_normalize import corroboration_key  # noqa: E402
    MIN_SHARED = 20
    AUDITABLE_FLOOR = 3          # measured 2026-08-13: 4 frameworks clear; pinned below
    pairs_clearing, detail = 0, []
    for fw, prov in (("ISO 27001/2 (2022)", "direct_olir"),
                     ("CMMC 2.0", "cmmc171"),
                     ("NIST SP 800-171 r2", "cmmc171"),
                     ("HIPAA Security", "direct_800_66")):
        D = {r[0] for r in conn.execute(
            "SELECT DISTINCT native_id FROM framework_projection WHERE framework=? AND provenance=?",
            (fw, prov))}
        H = {r[0] for r in conn.execute(
            "SELECT DISTINCT native_id FROM framework_projection WHERE framework=? "
            "AND provenance='hitrust_hub'", (fw,))}
        if not D or not H:
            continue
        exact = len(D & H)
        Dc = {corroboration_key(fw, x) for x in D} - {None}
        Hc = {corroboration_key(fw, x) for x in H} - {None}
        shared = max(exact, len(Dc & Hc))
        detail.append(f"{fw}={shared}")
        if shared >= MIN_SHARED:
            pairs_clearing += 1
    if pairs_clearing < AUDITABLE_FLOOR:
        fail(f"auditability regressed: only {pairs_clearing} framework(s) clear the "
             f">={MIN_SHARED}-shared-id bar (floor {AUDITABLE_FLOOR}); phase-36 F-6 "
             f"recorded 1 — a drop means an id dialect was reintroduced [{'; '.join(detail)}]")
    else:
        note(f"auditability floor: {pairs_clearing} framework(s) clear the >={MIN_SHARED} "
             f"shared-id bar for authority-vs-hub corroboration ({'; '.join(detail)}); "
             f"phase-36 baseline was 1")

    # 17. Identifier hygiene (Phase 37) — phase-36 finding F-7: assessment-objective
    #     PROSE was stored in native_id at the top confidence tier, so 100% of page 1
    #     of the obvious 800-171 query showed sentences where control ids belong.
    #     A native_id is an identifier: short, and never a sentence.
    idbad = []
    for col in ("native_a", "native_b"):
        for (fw, nid, prov) in conn.execute(
                f"SELECT fw_a, {col}, provenance FROM master_mappings "
                f"WHERE LENGTH({col}) > 80 OR {col} LIKE '% if %' OR {col} LIKE '%;%'"):
            # HITRUST writes 'id + title' by convention (159 of 226 ids) — allowed,
            # because the identifier still leads the string.
            if str(fw).startswith("HITRUST") or re.match(r"^\d{2}\.[a-z]\s", str(nid) or ""):
                continue
            idbad.append(f"{fw}:{str(nid)[:40]}... ({prov})")
    if idbad:
        fail(f"{len(idbad)} master row(s) store prose where a control identifier belongs "
             f"(F-7 regression): {idbad[:3]}")
    else:
        note("identifier hygiene: no master row stores sentence-shaped native ids")

    # 18. Anchor retention (Phase 37) — phase-36 finding F-8: cross-framework edges
    #     recorded no shared 800-53 anchors, so a user could not ask why a pair was
    #     believed related. Spoke edges are exempt: there the control is an endpoint.
    ANCHOR_FLOOR = 1000          # measured 2026-08-13: 1,379 cross rows carry anchors
    n_anch = conn.execute(
        "SELECT COUNT(*) FROM master_mappings WHERE fw_a<>? AND fw_b<>? AND anchor_count>0",
        ("NIST 800-53", "NIST 800-53")).fetchone()[0]
    if n_anch < ANCHOR_FLOOR:
        fail(f"anchor retention regressed: {n_anch} cross edges carry shared anchors "
             f"(floor {ANCHOR_FLOOR}; phase-36 baseline was 117)")
    else:
        note(f"anchor retention: {n_anch} cross edges carry their shared 800-53 anchors "
             f"(phase-36 baseline 117)")

    # 19. Framework -> CCI confirmation layer (Phase 38, schema 3.16) — the repository's
    #     objective is convergence onto CONFIRMED CCI mappings. This asserts the verdict
    #     derivation is total, the vocabulary exact, the witness rules honoured, and that
    #     `reachable` is never dressed up as a confirmation.
    cbad = []
    with open(ROOT / "canonical-sources" / "framework_vocab.json", encoding="utf-8") as f:
        _cv = json.load(f).get("cci_confirmation", {}).get("classes", {})
    allowed_v = set(_cv)
    v_counts = dict(conn.execute(
        "SELECT verdict, COUNT(*) FROM framework_cci_confirmation GROUP BY 1").fetchall())
    if not allowed_v:
        cbad.append("framework_vocab.json declares no cci_confirmation.classes")
    unknown_v = set(v_counts) - allowed_v
    if unknown_v:
        cbad.append(f"undeclared verdict(s): {sorted(unknown_v)}")
    n_nullv = conn.execute(
        "SELECT COUNT(*) FROM framework_cci_confirmation WHERE verdict IS NULL "
        "OR TRIM(verdict)=''").fetchone()[0]
    if n_nullv:
        cbad.append(f"{n_nullv} rows without a verdict (derivation not total)")
    # a verdict of `confirmed` REQUIRES the CCI's own anchor to be confirmed
    n_badanchor = conn.execute(
        "SELECT COUNT(*) FROM framework_cci_confirmation "
        "WHERE verdict='confirmed' AND w_cci_anchor_confirmed=0").fetchone()[0]
    if n_badanchor:
        cbad.append(f"{n_badanchor} confirmed rows whose CCI anchor is not itself confirmed")
    # consensus is control-granularity: it may support a confirmation but never carry one
    n_consonly = conn.execute(
        "SELECT COUNT(*) FROM framework_cci_confirmation WHERE verdict='confirmed' "
        "AND w_framework_sources < 2 AND w_stig_exercised = 0").fetchone()[0]
    if n_consonly:
        cbad.append(f"{n_consonly} confirmed rows rest on control-granularity witnesses alone "
                    f"(consensus/baseline/olir) with no CCI-level witness "
                    f"(a second same-anchor publisher or a STIG exercising the CCI)")
    # every confirmed row must be traceable to its witnesses
    n_nowit = conn.execute(
        "SELECT COUNT(*) FROM framework_cci_confirmation WHERE verdict='confirmed' "
        "AND (witnesses IS NULL OR witnesses IN ('', '[]'))").fetchone()[0]
    if n_nowit:
        cbad.append(f"{n_nowit} confirmed rows carry no witness list (untraceable verdict)")
    # Re-pinned phase 39: the per-anchor publisher rule corrected a phase-38 overcount
    # (anchor-blind counting credited two publishers of a control to every CCI it could
    # reach). Measured after correction + FedRAMP baseline derivation + OLIR witness:
    # 23,339. Floor below it, never aspirational.
    CONFIRMED_FLOOR = 18000
    # FedRAMP is derived from the owner's baseline flags — every row must say so, and
    # no FedRAMP row may carry the old hub-graded shape.
    n_fed_bad = conn.execute(
        "SELECT COUNT(*) FROM framework_cci_confirmation "
        "WHERE framework='FedRAMP r5' AND w_baseline_authoritative=0").fetchone()[0]
    if n_fed_bad:
        cbad.append(f"{n_fed_bad} FedRAMP rows lack the baseline_authoritative witness "
                    f"(hub-graded shape reintroduced)")
    if v_counts.get("confirmed", 0) < CONFIRMED_FLOOR:
        cbad.append(f"confirmed framework->CCI mappings regressed: "
                    f"{v_counts.get('confirmed', 0):,} < floor {CONFIRMED_FLOOR:,}")
    if cbad:
        fail("framework->CCI confirmation malformed: " + "; ".join(cbad[:6]))
    else:
        tot_v = sum(v_counts.values())
        note(f"framework->CCI confirmation: {tot_v:,} pairs across {len(v_counts)} verdicts "
             f"{dict(sorted(v_counts.items()))}; every confirmed row has a confirmed CCI anchor, "
             "a CCI-level witness, and a traceable witness list")

    conn.close()

    print("SPINE VALIDATION:", "FAIL" if FAILS else "PASS")
    for n in NOTES:
        print(f"  · {n}")
    for f in FAILS:
        print(f"  ✗ {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
