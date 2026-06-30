# edgar-breach-search

Search SEC EDGAR 8-K Item 1.05 cybersecurity incident disclosures and map disclosed incident types to NIST 800-53 control families.

## Scope

Queries the EDGAR cyber incident dataset in grc.db (table: `edgar_cyber_incidents`) and returns structured breach records matching the requested filter. Maps each incident type (ransomware, breach, unauthorized_access, disruption) to relevant NIST IR/AC/SI control families.

## Input Schema

```json
{
  "incident_type": "string (optional) — ransomware | breach | unauthorized_access | disruption",
  "company": "string (optional) — partial company name match",
  "since": "string (optional) — ISO date YYYY-MM-DD; filter by disclosure date",
  "limit": "integer (optional, default 20) — max results"
}
```

## Output Schema

```json
{
  "incidents": [
    {
      "accession_no": "string",
      "company_name": "string",
      "cik": "string",
      "incident_date": "string",
      "disclosure_date": "string",
      "incident_type": "string",
      "nist_families": ["IR", "SC"],
      "filing_url": "string"
    }
  ],
  "count": "integer",
  "db_built_at": "string",
  "human_review_required": true
}
```

## Do NOT use for

- Determining materiality of a breach under SEC rules (that requires legal judgment)
- Real-time monitoring of new 8-K filings (use edgar_loader.py for fresh pulls)
- Attributing incidents to specific threat actors

## References

- `edgar_loader.py` — populates edgar_cyber_incidents table
- `build_db.py` — builds grc.db with all source data
- `dbz_query.py edgar` subcommand — underlying query implementation
- `minority-report.md` — non-negotiable fabrication rules
