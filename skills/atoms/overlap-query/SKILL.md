---
name: overlap-query
description: >
  Compute the percentage of shared audit work between two compliance frameworks using the ER crosswalk data.
  Uses grc.db (er_overlap_pairs view) to return Jaccard index, coverage percentages, and shared/unique ER sets.
  Use this atom for the sales/CS "shared audit work %" deliverable.
  Do NOT use for single-control mapping (use compliance-crosswalk). Do NOT use for gap lists (use gap-analysis).
  Do NOT fabricate overlap numbers — compute only from the ER crosswalk data in grc.db.
---

# overlap-query

Computes framework overlap using the ER-anchored crosswalk data (core-audit/mappings/).
Each ER (Evidence Requirement) is a universal anchor — two frameworks "overlap" when they
share the same ER set. This enables exact overlap calculation without subjective weighting.

## Input

```json
{
  "framework_a": "SOC 2",
  "framework_b": "ISO 27001/2 (2022)",
  "db_path": "cross-mapping/output/grc.db",
  "include_er_lists": false
}
```

## Output

```json
{
  "tool": "overlap-query",
  "framework_a": "SOC 2",
  "framework_b": "ISO 27001/2 (2022)",
  "metrics": {
    "framework_a_er_count": 84,
    "framework_b_er_count": 81,
    "shared_er_count": 74,
    "jaccard_overlap_pct": 78.7,
    "a_covers_b_pct": 91.4,
    "b_covers_a_pct": 88.1
  },
  "interpretation": "SOC 2 certification covers 91.4% of ISO 27001/2 (2022) requirements at the ER level. Incremental work to add ISO 27001/2 (2022): ~8.6% of ER set (7 ERs).",
  "human_review_required": true
}
```

With `include_er_lists: true`, also returns `shared_er_ids`, `a_only_er_ids`, `b_only_er_ids`.

## Do NOT use this atom for
- Cross-CSV comparison (ERs across different CSV files are not comparable — IDs differ)
- Single-control lookups (use compliance-crosswalk)
- NIST 800-53-to-framework overlap (that's catalog-based, use gap-analysis)
- Fabricating overlap numbers not computed from ER data

## Pipeline note
Reads `er_overlap_pairs` view and `er_mappings` table from `grc.db`.

Script: `skills/atoms/overlap-query/scripts/overlap_query.py`

```bash
python3 skills/atoms/overlap-query/scripts/overlap_query.py \
    --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)" --format summary

python3 skills/atoms/overlap-query/scripts/overlap_query.py \
    --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)" --er-lists --format json
```

To see available ER frameworks stored in grc.db:
```bash
python3 cross-mapping/engine/dbz_query.py overlap --framework-a "SOC 2" --framework-b "HITRUST CSF v11"
```

Prerequisite: `grc.db` must exist. Build it with:
```bash
python3 cross-mapping/engine/build_db.py
```

Oracle CSVs (`SOC 2 T2 & ISO 27001.csv` etc.) remain as validation oracles — spot-check
that `shared_er_count` from the DB matches the overlap CSV row count.

`human_review_required: true` — ER-level overlap is advisory; actual audit scope depends on organization context.
