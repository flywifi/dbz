#!/usr/bin/env python3
"""consensus_sensitivity.py — how much of the consensus surface rests on each voter.

Phase 43 found `canonical-sources/crosswalk_80053_master.json` unregistered in the source
manifest while carrying a large share of the strong/moderate consensus surface — the tier the
master surface and the customer-facing overlap number are built on. The dependency had to be
rediscovered by archaeology because nothing printed it. This does.

Leave-one-out per voter: recompute each edge's tier without that voter and report how the
strong+moderate population moves (`tier = strong if votes>=3 else moderate if votes==2 else
single`, consensus_detector.py). Read-only, no thresholds, no pins — it reports a dependency,
it does not judge it. Excluding or re-weighting a voter is a deliberate decision made
elsewhere, with these numbers in hand.

Usage: python3 cross-mapping/tests/consensus_sensitivity.py
"""

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "cross-mapping" / "output" / "grc.db"


def tier(n: int) -> str:
    """Mirrors consensus_detector.py's tier rule."""
    return "strong" if n >= 3 else ("moderate" if n == 2 else "single")


def main() -> int:
    if not DB.exists():
        print("[consensus-sensitivity] grc.db not built (fresh checkout) — skipped")
        return 0
    conn = sqlite3.connect(DB)
    rows = [set(json.loads(v or "[]"))
            for (v,) in conn.execute("SELECT voters FROM consensus_edges")]
    conn.close()
    if not rows:
        print("[consensus-sensitivity] no consensus edges")
        return 0

    base = Counter(tier(len(v)) for v in rows)
    keep = base["strong"] + base["moderate"]
    print(f"consensus edges: {len(rows):,}  "
          f"strong={base['strong']:,} moderate={base['moderate']:,} single={base['single']:,}")
    print(f"strong+moderate (the population that feeds w_consensus and the master surface): "
          f"{keep:,}\n")
    print(f"{'voter':12} {'edges voted':>12} {'s+m without it':>16} {'delta':>10}")
    for w in sorted({x for v in rows for x in v}):
        c = Counter(tier(len(v - {w})) for v in rows)
        sm = c["strong"] + c["moderate"]
        n = sum(1 for v in rows if w in v)
        print(f"{w:12} {n:12,} {sm:16,} {sm - keep:+10,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
