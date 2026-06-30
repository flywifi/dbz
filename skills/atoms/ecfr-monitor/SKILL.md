# ecfr-monitor

Check whether a specific CFR title/part has changed since the last recorded as-of date by querying the eCFR versioner API, and return the current section count.

## Scope

Calls `ecfr_loader.py` in read-only mode against the eCFR versioner API and returns:
- Current as-of date (the date eCFR considers authoritative for this part)
- Section count in the part
- Whether the as-of date has advanced since `since_date` (if provided)

Use to detect regulatory changes to CFR parts tracked in the GRC database (HIPAA 45 CFR 164, GLBA 16 CFR 314, 21 CFR 11, 10 CFR 73.54, etc.) without doing a full ingest.

## Input Schema

```json
{
  "title": "integer — CFR title number (e.g. 45)",
  "part": "integer — CFR part number (e.g. 164)",
  "subpart": "string (optional) — subpart letter (e.g. 'C')",
  "since_date": "string (optional) — ISO date YYYY-MM-DD; set changed=true if as_of_date is newer"
}
```

## Output Schema

```json
{
  "title": "integer",
  "part": "integer",
  "subpart": "string or null",
  "as_of_date": "string — YYYY-MM-DD from eCFR versioner",
  "section_count": "integer",
  "changed": "boolean — true if as_of_date > since_date",
  "human_review_required": true
}
```

## Do NOT use for

- Fetching and storing the full text of CFR sections (use `ecfr_loader.py` directly for that)
- Determining legal interpretation of regulatory language (that requires legal counsel)
- CFR parts not yet configured in `ecfr_loader.py`

## References

- `ecfr_loader.py` — eCFR versioner API client and section extractor
- `canonical-sources/cfr/` — stored CFR section JSON output
- `minority-report.md` — non-negotiable fabrication rules
