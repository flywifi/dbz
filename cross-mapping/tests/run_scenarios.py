#!/usr/bin/env python3
"""
run_scenarios.py — pinned end-to-end scenario battery.

Unit tests check parts; this battery checks that the eleven questions users
actually ask still return the expected ANSWERS through the full pipeline
(loaders -> assemble -> grc.db -> query). Any regression surfaces as "the
SOC2xISO answer changed" — the user-meaningful signal.

Pins follow the measure-then-pin discipline (docs/BENCHMARK.md regression
policy): values measured 2026-07-18 at schema 3.13, pinned as bands (not exact)
where data legitimately drifts. On an intentional data change: re-measure ->
re-pin -> changes/CHANGELOG.md entry. Never pin aspirational values; never
delete a scenario.

Needs a built grc.db. Runs in the local gate battery and the standards-watch
CI step (after its fresh build); NOT in health.yml (no build there).
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "cross-mapping" / "output" / "grc.db"
QUERY = ROOT / "cross-mapping" / "engine" / "dbz_query.py"

FAILS = []


def check(cond, label):
    print(("  ok:  " if cond else "  FAIL:") + " " + label)
    if not cond:
        FAILS.append(label)


def q(*args):
    r = subprocess.run([sys.executable, str(QUERY), *args],
                       capture_output=True, text=True, cwd=ROOT)
    return r.stdout


def main() -> int:
    if not DB.exists():
        print("run_scenarios: grc.db not built — run build_db.py first")
        return 1
    c = sqlite3.connect(DB)

    # 1. The headline overlap answer: SOC 2 x ISO on a spine basis, in band.
    d = json.loads(q("overlap", "--framework-a", "SOC 2",
                     "--framework-b", "ISO 27001/2 (2022)", "--format", "json"))
    check(d.get("basis") in ("cci", "subpart"),
          f"scenario 1: SOC2xISO uses a spine basis (got {d.get('basis')})")
    check(48.0 <= (d.get("overlap_pct") or 0) <= 60.0,
          f"scenario 1: SOC2xISO overlap in band 48-60 (measured 54.2; got {d.get('overlap_pct')})")

    # 2. SOC 2 x PCI master edge count (measured 762; band +-15%).
    n = c.execute("SELECT COUNT(*) FROM master_mappings WHERE "
                  "(fw_a='PCI DSS v4.0' AND fw_b='SOC 2') OR "
                  "(fw_a='SOC 2' AND fw_b='PCI DSS v4.0')").fetchone()[0]
    check(648 <= n <= 876, f"scenario 2: SOC2xPCI master edges in band (measured 762; got {n})")

    # 3. HIPAA 164.312 technical-safeguard reach (measured 1644; band +-15%).
    n = c.execute("SELECT COUNT(*) FROM master_mappings WHERE "
                  "(fw_a='HIPAA Security' AND native_a LIKE '164.312%') OR "
                  "(fw_b='HIPAA Security' AND native_b LIKE '164.312%')").fetchone()[0]
    check(1397 <= n <= 1891, f"scenario 3: HIPAA 164.312 master reach in band (measured 1644; got {n})")

    # 4. FedRAMP Moderate baseline scoping (177 base controls at r5.2.0 — exact;
    #    a baseline change is a real event that must be noticed).
    n = c.execute("SELECT COUNT(*) FROM controls WHERE baseline_moderate=1").fetchone()[0]
    check(n == 177, f"scenario 4: FedRAMP Moderate base-control count exact (want 177; got {n})")

    # 5. FedRAMP 2026 KSIs citing IA-2 (measured 2 — exact; KSI set is pinned data).
    n = c.execute("SELECT COUNT(DISTINCT indicator_id) FROM fedramp_ksi_controls "
                  "WHERE r5_control='IA-2'").fetchone()[0]
    check(n == 2, f"scenario 5: KSIs citing IA-2 exact (want 2; got {n})")

    # 6. CCI dictionary complete (5,137 — exact; pinned committed artifact).
    n = c.execute("SELECT COUNT(*) FROM disa_ccis").fetchone()[0]
    check(n == 5137, f"scenario 6: CCI dictionary complete (want 5137; got {n})")

    # 7. STIG evidence layer (383 benchmarks — exact; pinned harvest).
    n = c.execute("SELECT COUNT(*) FROM stig_catalog").fetchone()[0]
    check(n == 383, f"scenario 7: STIG catalog complete (want 383; got {n})")

    # 8. Horizon registry loaded (76 records — exact until records are added;
    #    re-pinned 70→76 in phase 32 when the six CMMC suspension/RFI/task-force
    #    records landed).
    recs = json.loads((ROOT / "canonical-sources" / "anticipated_updates.json")
                      .read_text(encoding="utf-8"))["records"]
    check(len(recs) == 76, f"scenario 8: horizon registry (want 76; got {len(recs)})")

    # 9. OLIR-hub composed edges (1,870 — exact; pinned composition).
    n = c.execute("SELECT COUNT(*) FROM olir_hub_edges").fetchone()[0]
    check(n == 1870, f"scenario 9: OLIR-hub composed edges (want 1870; got {n})")

    # 10. Strong consensus pairs (measured 845; band +-10% — voters can shift).
    n = c.execute("SELECT COUNT(*) FROM consensus_edges WHERE tier='strong'").fetchone()[0]
    check(760 <= n <= 930, f"scenario 10: strong consensus pairs in band (measured 845; got {n})")

    # 11. The cmmc alias reaches the master surface's r2-labeled rows (phase-34 fix
    #     for the dead-alias regression: 'cmmc' fans out to CMMC 2.0 + 800-171 r2
    #     per the May-2024 class deviation; measured 105 SOC2 pairs, band +-15%).
    d = json.loads(q("master", "--framework-a", "cmmc", "--framework-b", "SOC 2",
                     "--format", "json", "--limit", "500"))
    rows11 = d.get("rows", [])
    check(89 <= len(rows11) <= 121,
          f"scenario 11: cmmc-alias master answer nonzero and in band (measured 105; got {len(rows11)})")
    check(any("NIST SP 800-171 r2" in (r.get("fw_a"), r.get("fw_b")) for r in rows11),
          "scenario 11: answer includes r2-labeled rows (the exact shipped regression)")

    # 12. Two labeled overlap metrics (phase-37, finding F-11). The co-reference figure
    #     must keep its previous value (nothing silently re-valued), and the strict
    #     source-stated figure must be present, lower, and honest about zeros.
    d12 = json.loads(q("overlap", "--framework-a", "SOC 2",
                       "--framework-b", "ISO 27001/2 (2022)", "--format", "json"))
    check(d12.get("shared_work_pct") is not None,
          "scenario 12: overlap reports a source-stated shared_work_pct alongside co-reference")
    check(48.0 <= (d12.get("overlap_pct") or 0) <= 60.0,
          f"scenario 12: co-reference value unchanged by the split "
          f"(measured 54.2; got {d12.get('overlap_pct')})")
    check((d12.get("shared_work_pct") or 0) == 0.0,
          f"scenario 12: SOC2xISO shared work is 0 — SOC 2's projection is entirely "
          f"hub-composed, so no source states shared work (got {d12.get('shared_work_pct')})")
    # a pair where BOTH sides carry authority coverage must be non-zero (measured 46.8;
    # band +-15% — measure-then-pin, never aspirational)
    d12b = json.loads(q("overlap", "--framework-a", "ISO 27001/2 (2022)",
                        "--framework-b", "NIST CSF 2.0", "--format", "json"))
    sw = d12b.get("shared_work_pct") or 0
    check(39.8 <= sw <= 53.8,
          f"scenario 12: ISOxCSF2 shared work in band (measured 46.8; got {sw})")
    check(sw <= (d12b.get("overlap_pct") or 0),
          "scenario 12: strict shared work never exceeds co-reference")

    c.close()
    print("\nSCENARIO BATTERY:", "PASS" if not FAILS else f"FAIL ({len(FAILS)})")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
