# ecfr-monitor — Maintainer Notes

## Non-Negotiables

- Never fabricate as-of dates, section counts, or change flags — all values come from the eCFR versioner API
- `changed` must be a boolean comparison of `as_of_date > since_date` using ISO date string comparison; never guess
- `human_review_required` must always be `true` — regulatory text requires legal review
- If the eCFR API is unreachable, return `{error: "eCFR API unavailable"}` not a fabricated result

## Known Failure Modes

- Network failure: eCFR API at `ecfr.gov/api/versioner/v1` requires outbound HTTPS; fails in air-gapped environments
- Unknown CFR part: eCFR returns 404 for parts that don't exist; surface as `{error: "CFR part not found"}`
- Subpart scope: `section_count` reflects the full part unless subpart is specified; count may be large for parts with many sections

## Regression Cases

See `evals/evals.json`:
- pass-01: 45 CFR 164 returns valid as-of date and non-zero section count
- fail-01: nonexistent CFR part returns error, not fabricated section data
- edge-01: since_date in the future always returns changed=false
