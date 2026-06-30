# overlap-oracle-validator

Compute the Jaccard overlap coefficient between two compliance frameworks and validate it against known oracle values from combination crosswalk CSVs.

## Scope

Calls `er_overlap.py` with a framework pair and returns:
- Jaccard coefficient (intersection / union of control IDs)
- Coverage percentages (A covers B %, B covers A %)
- Optional oracle delta: difference from the known-good value in the combination CSV oracle

Use to verify overlap calculations haven't regressed after schema or crosswalk changes, or to answer "how much audit work does SOC 2 cover relative to ISO 27001?"

## Input Schema

```json
{
  "framework_a": "string — e.g. SOC2, ISO27001, HIPAA",
  "framework_b": "string — e.g. ISO27001, HITRUST, GDPR",
  "check_oracle": "boolean (optional, default false) — validate against combination CSV oracle"
}
```

## Output Schema

```json
{
  "framework_a": "string",
  "framework_b": "string",
  "jaccard": "number (0.0–1.0)",
  "a_covers_b_pct": "number (0.0–100.0)",
  "b_covers_a_pct": "number (0.0–100.0)",
  "oracle_delta": "number or null — deviation from oracle CSV value",
  "oracle_status": "string — pass | fail | skipped",
  "human_review_required": true
}
```

## Do NOT use for

- Determining which framework is "better" for compliance (that is a risk/business decision)
- Frameworks not present in the ER crosswalk CSVs (the mapping must exist in core-audit/mappings/)
- Substituting for a gap analysis (use gap-analysis atom for control-level detail)

## References

- `er_overlap.py` — Jaccard calculation engine
- `cross-mapping/core-audit/mappings/*.csv` — ER crosswalk source data
- Combination CSVs (e.g. `SOC 2 T2 & ISO 27001.csv`) — overlap oracles
- `minority-report.md` — non-negotiable fabrication rules
