---
name: overlap-query
description: >
  Compute the percentage of shared audit work between two compliance frameworks using the ER crosswalk data.
  Returns Jaccard index, coverage percentages, and the shared/unique control sets.
  Use this atom for the sales/CS "shared audit work %" deliverable.
  Do NOT use for single-control mapping (use compliance-crosswalk). Do NOT use for gap lists (use gap-analysis).
  Do NOT fabricate overlap numbers — compute only from the ER crosswalk CSV data.
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
  "crosswalk_path": "cross-mapping/core-audit/mappings/SOC 2 T2.csv",
  "metric": "er_overlap"
}
```

## Output

```json
{
  "tool": "overlap-query",
  "framework_a": "SOC 2",
  "framework_b": "ISO 27001/2 (2022)",
  "crosswalk_source": "SOC 2 T2.csv",
  "metrics": {
    "framework_a_er_count": 84,
    "framework_b_er_count": 81,
    "shared_er_count": 74,
    "jaccard_overlap_pct": 78.7,
    "a_covers_b_pct": 91.4,
    "b_covers_a_pct": 88.1
  },
  "shared_er_ids": ["ER-1", "ER-2", "ER-3"],
  "a_only_er_ids": ["ER-5", "ER-12"],
  "b_only_er_ids": ["ER-8"],
  "interpretation": "SOC 2 certification covers 91.4% of ISO 27001 requirements at the ER level. Incremental work to add ISO 27001: ~8.6% of ER set (7 ERs).",
  "human_review_required": true
}
```

## Do NOT use this atom for
- Cross-CSV comparison (ERs across different CSV files are not comparable — IDs differ)
- Single-control lookups (use compliance-crosswalk)
- NIST 800-53-to-framework overlap (that's catalog-based, use gap-analysis)
- Fabricating overlap numbers not computed from ER data

## Pipeline note
Always uses within-crosswalk comparison (same CSV for both frameworks).
Oracle CSVs (`SOC 2 T2 & ISO 27001.csv` etc.) serve as validation oracles.
Calls `cross-mapping/engine/er_overlap.py:compute_er_overlap()`.
`human_review_required: true` — ER-level overlap is advisory; actual audit scope depends on organization context.
