# MAINTAINER — kev-lookup

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`kev-lookup` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Never fabricate KEV entries — `in_kev: false` is correct if the CVE is not in the DB.
- CVE ID format must be validated: 'CVE-' prefix + year + '-' + number sequence.
- NIST family codes returned must be from the controlled vocabulary (19 NIST families).
- References `skills/shared/minority-report.md` policy.

## Known failure modes
- **Fabricated KEV status**: saying `in_kev: true` for a CVE not in the DB. Must be `false`.
- **Stale KEV data**: KEV is a daily-updated feed. If `db_built_at` is >7 days old, note it
  in the response so callers know to rebuild before relying on KEV absence.

## Fragile fallbacks that must not become defaults
- Partial CVE ID match (e.g., 'CVE-2021' matching all 2021 CVEs): never do broad pattern
  matching. Exact CVE ID only.

## Regression cases to preserve
1. CVE-2021-44228 (Log4Shell) → `in_kev: true`, nist_families includes 'SI' and 'RA' (pass-01)
2. Invalid CVE format → error (fail-01)
3. Valid CVE not in KEV → `in_kev: false`, not an error (edge-01)

## Approval-gated changes
- Changing the NIST family mapping logic for CVE types.
- Changing the CVE ID validation regex.

## Minority-report policy
Single-record DB lookup; minority-report not applicable.
If CVE data conflicts between KEV and NVD, note discrepancy in metadata only.
See `skills/shared/minority-report.md`.

## Update checklist
- [ ] SKILL.md "Do NOT use for…" clause intact
- [ ] `python3 tools/sync_check.py` passes
- [ ] evals/evals.json has ≥3 cases
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
