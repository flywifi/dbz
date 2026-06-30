---
name: gap-analysis
description: >
  Identify gaps in control coverage when a customer/prospect migrates from or adds a compliance framework.
  Uses the grc.db SQLite database (unified_mappings table) to determine which NIST 800-53 controls have
  no equivalent in the target framework. Returns a prioritized gap list with remediation context.
  NEVER fabricate control IDs or gap classifications — leave unknown fields blank.
  Do NOT use for single-control mapping (use compliance-crosswalk). Do NOT use for overlap % (use overlap-query).
---

# gap-analysis

Analyzes two compliance frameworks and identifies:
1. Controls in `target_framework` that are not covered by NIST 800-53 (source)
2. Controls partially covered (Superset/Intersecting relationships only)
3. Fully covered controls (Equal/Subset)

Useful for:
- **Audit readiness**: "What additional work is needed to achieve ISO 27001 if we have SOC 2?"
- **Sales**: "What's the incremental lift to add CMMC Level 2 to your FedRAMP program?"
- **Customer success**: "Your HITRUST certification covers X% of NIST 800-53 — here's what's missing"

## Input

```json
{
  "target_framework": "CMMC 2.0 / NIST 800-171",
  "fedramp_level": "moderate",
  "families": ["AC", "IA", "SC"],
  "db_path": "cross-mapping/output/grc.db"
}
```

## Output

```json
{
  "tool": "gap-analysis",
  "source_framework": "NIST 800-53 Rev 5",
  "target_framework": "CMMC 2.0 / NIST 800-171",
  "scope_applied": {"fedramp_level": "moderate", "families": ["AC", "IA", "SC"]},
  "coverage_summary": {
    "total_source_controls": 110,
    "with_target_mapping": 45,
    "coverage_pct": 40.9,
    "fully_covered": 38,
    "partially_covered": 7,
    "not_covered": 65
  },
  "gaps": [
    {
      "source_control_id": "AC-4",
      "source_title": "Information Flow Enforcement",
      "family": "AC",
      "gap_type": "not_covered",
      "target_equivalents": [],
      "relationship_type": null
    }
  ],
  "partial_coverage": [...],
  "human_review_required": true
}
```

## Do NOT use this atom for
- Single-control mapping (use compliance-crosswalk)
- Computing Jaccard overlap % (use overlap-query)
- Fabricating remediation notes not grounded in the crosswalk data
- Claiming coverage where only Intersecting (not Equal/Subset) relationships exist

## Pipeline note
Reads `unified_mappings` from `grc.db` (built by `cross-mapping/engine/build_db.py`).

Gap classification:
  - `fully_covered`    : relationship_type in ("Equal", "Subset") — precise OLIR STRM equivalence
  - `partially_covered`: relationship_type in ("Superset", "Intersecting", "mapped_to", "transitive_via_hitrust")
  - `not_covered`      : no mapping record for target framework

Note: Current catalog data uses `mapped_to` (direct reference) and `transitive_via_hitrust`
(HITRUST hub-bridged inference) rather than OLIR STRM types; both count as partial coverage.
OLIR STRM types will appear if/when catalog loaders are updated to encode precise overlap.

Script: `skills/atoms/gap-analysis/scripts/gap_analysis.py`

```bash
python3 skills/atoms/gap-analysis/scripts/gap_analysis.py \
    "CMMC 2.0 / NIST 800-171" --fedramp moderate --family AC IA SC --format summary
```

Prerequisite: `grc.db` must exist. Build it with:
```bash
python3 cross-mapping/engine/build_db.py
```

`human_review_required: true` — gap classifications require compliance specialist validation.
