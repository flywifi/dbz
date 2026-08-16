#!/usr/bin/env python3
"""phase43_consensus_frame.py — seeded, reproducible sample of the consensus cross stratum.

Phase 36 left the consensus stratum unadjudicated (its residual risk #2) while the flagship
stored pairs sit on exactly that tier. This draws the sample phase 43 adjudicates.

Sampling rule is phase 36's, so the two audits are comparable: rank by
md5(seed|fw_a|native_a|fw_b|native_b) and take the head of each stratum. Strata here are
framework PAIRS, allocated proportionally (largest remainder, min 1) so no pair dominates.

Two joins are pre-solved and both matter:
  * voters — master_surface builds these rows from consensus_edges with _CONSENSUS_TO_CANON
    applied to labels and native ids passed through unchanged, so reversing that map and
    joining exactly recovers votes/tier/voters for 3,422 of 3,422 rows.
  * shared anchors — `shared_anchors` is NULL and `anchor_count` 0 on consensus rows, and
    consensus_edges.shared_atoms is populated only for `strong`. Reconstructing each side's
    800-53 anchors from framework_projection needs the coarse witness key: exact native_id
    reaches 22.2% of the stratum, consensus_key 52.9%, corroboration_key 64.4%. Roughly half
    the stratum therefore has NO reconstructable anchor evidence, which is recorded per edge
    (`anchor_evidence`) so the published rates can be split by it rather than blended.

Emits the frame (seed + stratum SQL + keys) and a worksheet with verdict fields left null.
Read-only. Usage: python3 cross-mapping/tests/phase43_consensus_frame.py
"""

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
from spine_normalize import corroboration_key            # noqa: E402
from master_surface import _CONSENSUS_TO_CANON as C2C    # noqa: E402

DB = ROOT / "cross-mapping" / "output" / "grc.db"
OUT = ROOT / "docs" / "audits" / "data"
SEED = 20430816
N_TOTAL = 120

STRATUM_SQL = ("SELECT fw_a, native_a, fw_b, native_b FROM master_mappings "
               "WHERE provenance='consensus' AND fw_a NOT LIKE 'NIST 800-53%' "
               "AND fw_b NOT LIKE 'NIST 800-53%'")


def rank(key: str) -> str:
    return hashlib.md5(f"{SEED}|{key}".encode()).hexdigest()


def main() -> int:
    if not DB.exists():
        print("grc.db not built", file=sys.stderr)
        return 2
    conn = sqlite3.connect(DB)
    rows = list(conn.execute(STRATUM_SQL))

    rev = {}
    for fa, na, fb, nb, votes, tier, voters in conn.execute(
            "SELECT fw_a, native_a, fw_b, native_b, votes, tier, voters FROM consensus_edges "
            "WHERE tier IN ('strong','moderate')"):
        ca, cb = C2C.get(fa, fa), C2C.get(fb, fb)
        rev[(ca, na, cb, nb)] = rev[(cb, nb, ca, na)] = (votes, tier, voters)

    proj = {}
    for fw, nat, r5 in conn.execute(
            "SELECT framework, native_id, r5_control FROM framework_projection "
            "WHERE status <> 'refuted'"):
        proj.setdefault((fw, corroboration_key(str(fw), str(nat)) or str(nat)), set()).add(r5)
    titles = dict(conn.execute("SELECT nist_id, title FROM controls"))

    pairs = Counter((a, c) for a, _, c, _ in rows)
    alloc, remainder = {}, []
    for p, n in pairs.items():
        exact = N_TOTAL * n / len(rows)
        alloc[p] = max(1, int(exact))
        remainder.append((exact - int(exact), p))
    for _, p in sorted(remainder, reverse=True):
        if sum(alloc.values()) >= N_TOTAL:
            break
        alloc[p] += 1

    frame, sheet = {}, []
    for p, want in sorted(alloc.items()):
        cand = sorted((r for r in rows if (r[0], r[2]) == p),
                      key=lambda r: rank("|".join(r)))[:want]
        frame["|".join(p)] = {"available": pairs[p], "picked": len(cand),
                              "keys": ["|".join(r) for r in cand]}
        for fa, na, fb, nb in cand:
            A = proj.get((fa, corroboration_key(fa, na) or na), set())
            B = proj.get((fb, corroboration_key(fb, nb) or nb), set())
            shared = sorted(A & B)
            votes, tier, voters = rev.get((fa, na, fb, nb), (None, None, None))
            sheet.append({
                "key": f"{fa}|{na}|{fb}|{nb}",
                "fw_a": fa, "native_a": na, "fw_b": fb, "native_b": nb,
                "votes": votes, "consensus_tier": tier, "voters": voters,
                "shared_anchors": shared,
                "shared_anchor_titles": {c: titles.get(c) for c in shared[:8]},
                "anchor_evidence": bool(shared),
                "verdict": None, "evidence": None, "reasoning": None,
            })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phase-43-consensus-frame.json").write_text(json.dumps(
        {"db": str(DB), "seed": SEED, "stratum_sql": STRATUM_SQL,
         "total_rows": len(rows), "sample": frame}, indent=1) + "\n", encoding="utf-8")
    (OUT / "phase-43-consensus-worksheet.json").write_text(
        json.dumps(sheet, indent=1) + "\n", encoding="utf-8")
    print(f"stratum {len(rows):,}; sampled {len(sheet)}; "
          f"with reconstructable anchor evidence {sum(1 for s in sheet if s['anchor_evidence'])}; "
          f"voters recovered {sum(1 for s in sheet if s['voters'])}/{len(sheet)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
