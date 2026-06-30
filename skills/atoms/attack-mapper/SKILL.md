---
name: attack-mapper
description: >
  Look up a MITRE ATT&CK Enterprise technique and return the NIST 800-53 controls
  mapped to it via the NIST ATT&CK-to-800-53 mapping (NIST SP 800-53 ATT&CK v13 mapping XLSX).
  Returns the technique name, tactics, and mapped control IDs.
  Do NOT use for ATT&CK technique discovery or browsing — this is a single-ID lookup.
  Do NOT use for CAPEC or CWE mappings — different data model.
atom: true
version: "1.0"
---

# attack-mapper

Single-technique lookup against the `attack_techniques` table in grc.db.
Wraps `dbz_query.py attack`.

## Input schema
```json
{
  "technique_id": "string — MITRE ATT&CK technique ID (e.g. 'T1078', 'T1078.001')"
}
```

## Output schema
```json
{
  "technique_id": "string",
  "name": "string — technique name",
  "tactics": "array — MITRE tactic names (e.g. ['Credential Access', 'Persistence'])",
  "nist_controls": "array — NIST 800-53 control IDs mapped to this technique",
  "mapping_source": "string — 'NIST SP 800-53 ATT&CK v13 mapping' or similar"
}
```

## Do NOT use for
- Browsing all techniques in a tactic — use the STIX bundle directly
- CAPEC attack pattern lookups — different ID format and table
- CWE weakness lookups — different table
- Reverse lookup (control ID → techniques) — use dbz_query.py directly

## Conflicting sources — minority-report policy
When the NIST ATT&CK mapping XLSX and a CISA advisory cite different NIST controls for the
same technique, emit `minority_report.conflicts`. The NIST XLSX is the primary source.
See canonical policy: `skills/shared/minority-report.md`.
