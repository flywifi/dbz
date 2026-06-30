---
name: kev-lookup
description: >
  Look up a CVE identifier in the CISA Known Exploited Vulnerabilities (KEV) catalog.
  Returns KEV status, date added, affected product, and the NIST 800-53 control families
  most relevant to remediating this vulnerability class.
  Do NOT use for NVD full CVE data (use the nvd subcommand directly).
  Do NOT use for ATT&CK technique mapping (use attack-mapper).
atom: true
version: "1.0"
---

# kev-lookup

Single CVE lookup against the `cisa_kev` table in grc.db.
Wraps `dbz_query.py kev`.

## Input schema
```json
{
  "cve_id": "string — CVE identifier in format 'CVE-YYYY-NNNNN'"
}
```

## Output schema
```json
{
  "cve_id": "string",
  "in_kev": "boolean — true if CVE is in the CISA KEV catalog",
  "date_added": "string? — ISO date added to KEV (null if not in KEV)",
  "vulnerability_name": "string? — CISA name for the vulnerability",
  "affected_product": "string? — vendor and product name",
  "required_action": "string? — CISA-required remediation action",
  "due_date": "string? — CISA compliance deadline",
  "nist_families": "array — NIST 800-53 control family codes relevant to this CVE type"
}
```

## Do NOT use for
- NVD full CVSS scores or CWE details — query grc.db nvd_cves directly
- ATT&CK technique mapping — use attack-mapper
- Checking whether a KEV update is available — use framework-update-check with 'cisa-kev'

## Conflicting sources — minority-report policy
Not applicable for single-record DB lookup. If the CVE appears in both KEV and NVD with
conflicting severity data, note it in response metadata but do not emit minority_report.
See canonical policy: `skills/shared/minority-report.md`.
