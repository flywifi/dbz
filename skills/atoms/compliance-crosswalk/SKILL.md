---
name: compliance-crosswalk
description: >
  Map a control from one compliance framework to its equivalents in one or more target frameworks,
  using the unified_mappings field in the NIST 800-53 catalog or the ER crosswalk data.
  Returns typed mapping records with relationship_type, strength, direction, and provenance.
  NEVER fabricate control IDs or relationship types — return an explicit gap if no mapping exists.
  Do NOT use for computing overlap percentages (use overlap-query). Do NOT use for gap analysis
  across an entire framework (use gap-analysis).
---

# compliance-crosswalk

Maps a single source control (NIST or ER) to its equivalents in a target framework.
Reads from the enriched catalog JSON or ER crosswalk CSV. Returns typed records
with full provenance so downstream systems can audit the mapping chain.

## Input

```json
{
  "source_control_id": "AC-2",
  "source_framework": "NIST 800-53 Rev 5",
  "target_frameworks": ["ISO/IEC 27001:2022", "CMMC 2.0 / NIST 800-171", "HITRUST CSF"],
  "catalog_path": "cross-mapping/nist-catalog/output/NIST_800_53_AC.json",
  "include_enhancements": false
}
```

## Output

```json
{
  "tool": "compliance-crosswalk",
  "source_control": {
    "id": "AC-2",
    "framework": "NIST 800-53 Rev 5",
    "title": "Account Management",
    "fedramp_levels": ["low", "moderate", "high"]
  },
  "mappings": [
    {
      "framework": "ISO/IEC 27001:2022",
      "framework_version": "2022",
      "control_id": "A.5.16",
      "control_title": "",
      "relationship_type": "mapped_to",
      "strength": "",
      "direction": "NIST→ISO 27001",
      "mapping_source": "NIST OLIR STRM (sp800-53r5-to-iso-27001-mapping-2022)",
      "notes": "",
      "confidence": "high"
    }
  ],
  "gaps": [
    {
      "target_framework": "SOC 2",
      "reason": "No direct NIST→SOC 2 crosswalk in catalog; use ER crosswalk for commercial frameworks"
    }
  ],
  "human_review_required": true
}
```

`confidence` reflects the mapping's provenance: `"high"` is reserved for Confirmed-Direct
OLIR STRM mappings; transitive or heuristic mappings must be `"medium"` or `"low"`.

## Do NOT use this atom for
- Fabricating control IDs, relationship types, or strength values not in the source data
- Computing overlap % between two frameworks (use overlap-query)
- Full framework gap analysis (use gap-analysis)
- Pair enumeration between two non-NIST frameworks or audit-scope filtering (use master-crosswalk)

## Master-surface control mode (Phase 19)
For a single native id in ANY framework — not just a NIST control — the master surface
answers "what does this map to, across every source, strongest tier first":

```bash
python3 cross-mapping/engine/dbz_query.py master --framework "SOC 2" --control CC6.1
```

Rows carry tier (`owner_direct > nist_stated > hub > bundled > consensus >
production_aggregate`), provenance, confidence, and minority-report `corroboration`.
Since Phase 19, HIPAA Security and CSF 2.0 have NIST-stated direct paths (SP 800-66r2 OLIR,
CSF2->53 r5.2.0 OLIR) and PCI DSS v4.0 has a bundled-tier path — "commercial frameworks
have no direct NIST mapping" is no longer categorically true; the tier tells you which
kind of mapping you are holding.

## Pipeline note
Reads from `unified_mappings` in the enriched catalog JSON (schema_version 1.1.0+).
Relationship types follow the NIST OLIR STRM vocabulary:
  "Subset" | "Superset" | "Equal" | "Intersecting" | "mapped_to" | ""
`human_review_required: true` — relationship type and strength must be verified by a compliance specialist.

## Conflicting sources — minority-report policy
When two crosswalk sources disagree on a mapping (e.g., NIST OLIR says "Subset" but HITRUST hub
says "Equal" for the same control pair), emit `minority_report.conflicts` with both sources.
See canonical policy: `skills/shared/minority-report.md`.
