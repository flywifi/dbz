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

    conn.close()

    print("SPINE VALIDATION:", "FAIL" if FAILS else "PASS")
    for n in NOTES:
        print(f"  · {n}")
    for f in FAILS:
        print(f"  ✗ {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
