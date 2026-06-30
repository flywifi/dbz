---
name: cfr-lookup
description: >
  Retrieve structured CFR (Code of Federal Regulations) sections from the GRC database.
  Returns section text and the NIST 800-53 control families mapped to each section.
  Use for HIPAA (45 CFR 164), GLBA (16 CFR 314), 21 CFR 11, 10 CFR 73.54, and other
  ingested CFR parts. Do NOT use for live eCFR API lookups (data is from last DB build).
  Do NOT use for Federal Register rulemaking text (not a CFR section).
atom: true
version: "1.0"
---

# cfr-lookup

Structured lookup against the `cfr_requirements` table in grc.db.
Wraps `dbz_query.py cfr`.

## Input schema
```json
{
  "part": "string — CFR part in '45-CFR-164' format (title-CFR-part)",
  "section": "string? — optional section number (e.g. '164.308' for HIPAA Administrative Safeguards)"
}
```

## Output schema
```json
{
  "part": "string",
  "sections": [
    {
      "section_id": "string — e.g. '164.308'",
      "title": "string",
      "text": "string — section text",
      "nist_families": "array — NIST 800-53 family codes (e.g. ['IA', 'AC', 'SC'])"
    }
  ],
  "count": "integer"
}
```

## Do NOT use for
- Live eCFR API queries — use ecfr_loader.py directly for fresh pulls
- Federal Register rulemaking text — not stored in cfr_requirements table
- Statutory text (Title 18 criminal statutes) — different data model

## Conflicting sources — minority-report policy
When a CFR section maps to different NIST families in two different ingestion runs
(e.g., ecfr_loader.py keyword heuristic vs. manually-coded mapping), emit
`minority_report.conflicts` with both mappings. See `skills/shared/minority-report.md`.
