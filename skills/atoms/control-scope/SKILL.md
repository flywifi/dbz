---
name: control-scope
description: >
  Retrieve all controls in a named framework baseline from the GRC database.
  Returns the full list of control IDs, titles, and families for a given framework_id.
  Use for FedRAMP High/Moderate/Low baselines, CMMC levels, DAAPM, and ER crosswalk scope.
  Do NOT use for keyword search within controls (use control-search).
  Do NOT use for framework crosswalk mapping (use compliance-crosswalk).
atom: true
version: "1.0"
---

# control-scope

Returns the complete set of controls for a named framework baseline.
Wraps `dbz_query.py scope`.

## Input schema
```json
{
  "framework_id": "string — framework ID from feed_registry (e.g. 'fedramp-moderate', 'cmmc-level-2', 'nist-800-53')"
}
```

## Output schema
```json
{
  "framework_id": "string",
  "controls": [
    {
      "id": "string — control ID",
      "title": "string",
      "family": "string — two-letter family code",
      "baseline": "string — baseline name this control appears in"
    }
  ],
  "count": "integer"
}
```

## Do NOT use for
- Keyword search within controls — use control-search
- Framework crosswalk mapping — use compliance-crosswalk
- Overlap percentage calculation — use overlap-query

## Conflicting sources — minority-report policy
If the framework appears in both `controls` table (NIST side) and `er_controls` table (ER side)
with different counts, emit `minority_report.conflicts` with both counts and sources.
See canonical policy: `skills/shared/minority-report.md`.
