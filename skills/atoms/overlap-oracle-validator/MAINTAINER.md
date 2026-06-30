# overlap-oracle-validator — Maintainer Notes

## Non-Negotiables

- Never fabricate Jaccard coefficients or coverage percentages — all values come from `er_overlap.py` against real crosswalk CSV data
- If a framework pair is not present in `core-audit/mappings/`, return an error — do not estimate
- `human_review_required` must always be `true`
- Oracle delta is null (not 0) when `check_oracle` is false or no oracle CSV exists for the pair

## Known Failure Modes

- Framework not in ER crosswalk: `er_overlap.py` raises ValueError; return `{error: "framework not found"}` not a fabricated result
- No combination CSV for the pair: oracle validation is skipped; `oracle_status` = `"skipped"`, not `"fail"`
- Case sensitivity: framework names are case-normalized internally; "soc2" and "SOC2" both resolve

## Regression Cases

See `evals/evals.json`:
- pass-01: SOC2 × ISO27001 returns Jaccard in expected oracle range
- fail-01: unknown framework returns error, not fabricated values
- edge-01: framework pair with no combination CSV returns oracle_status = skipped
