---
name: gap-analysis
description: >
  Identify gaps in control coverage when a customer/prospect migrates from or adds a compliance framework.
  Uses the NIST 800-53 unified_mappings or ER crosswalk to determine which controls in the target framework
  have no equivalent in the source framework. Returns a prioritized gap list with remediation context.
  NEVER fabricate control IDs or gap classifications — leave unknown fields blank.
  Do NOT use for single-control mapping (use compliance-crosswalk). Do NOT use for overlap % (use overlap-query).
---

# gap-analysis

Analyzes two compliance frameworks and identifies:
1. Controls in `target_framework` that are not covered by `source_framework`
2. Controls partially covered (Superset/Intersecting relationships only)
3. Fully covered controls (Equal/Subset)

Useful for:
- **Audit readiness**: "What additional work is needed to achieve ISO 27001 if we have SOC 2?"
- **Sales**: "What's the incremental lift to add CMMC Level 2 to your FedRAMP program?"
- **Customer success**: "Your HITRUST certification covers X% of NIST 800-53 — here's what's missing"

## Input

```json
{
  "source_framework": "NIST 800-53 Rev 5",
  "target_framework": "CMMC 2.0 / NIST 800-171",
  "scope": {
    "fedramp_levels": ["moderate"],
    "families": ["AC", "IA", "SC"]
  },
  "catalog_path": "cross-mapping/nist-catalog/output/NIST_800_53_FULL_ALL_FAMILIES.json",
  "output_format": "summary"
}
```

## Output

```json
{
  "tool": "gap-analysis",
  "source_framework": "NIST 800-53 Rev 5",
  "target_framework": "CMMC 2.0 / NIST 800-171",
  "scope_applied": {"fedramp_levels": ["moderate"], "families": ["AC", "IA", "SC"]},
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
      "gap_type": "not_covered",
      "target_equivalents": [],
      "remediation_note": "No CMMC practice maps to this control; implement via AC.L2-3.1.3 (flow control of CUI)"
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
Reads `unified_mappings` from enriched catalog (schema_version 1.1.0+).
Gap classification:
  - `fully_covered`   : relationship_type in ("Equal", "Subset")
  - `partially_covered`: relationship_type in ("Superset", "Intersecting")
  - `not_covered`     : no mapping record for target framework
`human_review_required: true` — gap classifications require compliance specialist validation.
