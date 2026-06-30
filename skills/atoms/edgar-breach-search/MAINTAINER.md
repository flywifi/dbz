# edgar-breach-search — Maintainer Notes

## Non-Negotiables

- Never fabricate incident records, company names, accession numbers, or NIST family mappings
- If `edgar_cyber_incidents` table is empty (loader not yet run), return `count: 0` with `_note: "edgar_loader.py has not been run"`
- `human_review_required` must always be `true` — disclosures require legal/compliance review

## Known Failure Modes

- Empty table: edgar_loader.py requires network access to SEC EDGAR; run it before querying
- Partial incident_type match: the DB stores normalized types; "ransomware" must match exactly
- Date filter: `since` filters on `disclosure_date` (SEC filing date), not `incident_date` (when breach occurred)

## Regression Cases

See `evals/evals.json`:
- pass-01: ransomware filter returns results with IR/SC families
- fail-01: unknown incident_type returns empty with informative message, not fabricated data
- edge-01: empty table returns count=0, not error
