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

    conn.close()

    print("SPINE VALIDATION:", "FAIL" if FAILS else "PASS")
    for n in NOTES:
        print(f"  · {n}")
    for f in FAILS:
        print(f"  ✗ {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
