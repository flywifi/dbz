---
name: control-search
description: >
  Search the GRC database for NIST 800-53 controls matching a keyword or phrase.
  Returns matching controls with IDs, titles, family codes, and control text.
  Do NOT use for retrieving all controls in a framework baseline (use control-scope).
  Do NOT use for crosswalk mapping (use compliance-crosswalk).
atom: true
version: "1.0"
---

# control-search

Single-operation keyword search against the `controls` table in grc.db.
Wraps `dbz_query.py search`.

## Input schema
```json
{
  "query": "string — keyword or phrase to search against control titles and text",
  "family": "string? — optional NIST family filter: 'AC', 'AU', 'CA', 'CM', 'CP', 'IA', 'IR', 'MA', 'MP', 'PE', 'PL', 'PM', 'PS', 'PT', 'RA', 'SA', 'SC', 'SI', 'SR'",
  "max_results": "integer? — default 20, max 100"
}
```

## Output schema
```json
{
  "controls": [
    {
      "id": "string — control ID (e.g. 'AC-2')",
      "title": "string — control title",
      "family": "string — two-letter family code",
      "text": "string — first 500 chars of control text"
    }
  ],
  "count": "integer — total matches returned"
}
```

## Do NOT use for
- Retrieving all controls in a baseline — use control-scope
- Framework crosswalk mapping — use compliance-crosswalk
- CVE/vulnerability lookups — use kev-lookup
- CFR regulatory text — use cfr-lookup

## Conflicting sources — minority-report policy
Not applicable for pure keyword search. If DB metadata suggests stale data (built_at > 30 days),
note it in the response. See canonical policy: `skills/shared/minority-report.md`.
