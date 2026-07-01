# MAINTAINER — gap-analysis

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`gap-analysis` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Never fabricates gap classifications or remediation notes not grounded in `unified_mappings` data.
- `human_review_required: true` in every output.
- `partially_covered` controls must not be reported as `fully_covered` — the distinction matters for audit scoping.
- Source is always NIST 800-53 Rev 5; target framework comes from `unified_mappings`. Never reverse this.
- Gap percentages must be computed from the DB, not estimated.
- Always report `coverage_summary` even when the gaps list is empty.

## Known failure modes
- **Overclaiming coverage**: treating `mapped_to` and `transitive_via_hitrust` as "fully covered" — they are partial. Only `Equal` and `Subset` OLIR STRM types count as fully covered.
- **Scope creep**: being asked to map individual controls (use `compliance-crosswalk`) or compute Jaccard overlap (use `overlap-query`).
- **Missing `fedramp_level` filter**: without the filter, the gap list includes all 325 controls, which overwhelms most use cases. Always confirm scope.
- **Stale DB**: if `grc.db` is not rebuilt after catalog changes, gap numbers may be wrong. Always emit `db_built_at` from `db_metadata` so humans can detect this.

## Fragile fallbacks that must not become defaults
- When `grc.db` is absent, the atom must fail loudly with a build instruction — never fabricate gaps from general framework knowledge.
- `families` filter defaults to all families when omitted — never silently scope to a subset.

## Regression cases to preserve
1. Returns `human_review_required: true` in every response.
2. Returns `coverage_summary.coverage_pct` as a number (not a string) rounded to one decimal.
3. Does not classify `transitive_via_hitrust` mappings as `fully_covered`.
4. Returns `db_built_at` field so the consumer can verify freshness.
5. Returns an honest `not_covered` list, never truncated without a `truncated: true` flag.

## Approval-gated changes
- Changing gap classification thresholds (what counts as fully vs. partially covered).
- Changing how `fedramp_level` filter is applied (currently: filter `controls` table by baseline).
- Adding new target frameworks that require new crosswalk JOIN logic.
- Modifying the output schema (coverage_summary, gaps[], partial_coverage[] shape).

## Minority-report policy
When gap percentage differs by >5 pp depending on which relationship types are counted as
"covered," emit `minority_report.conflicts` with both counting methods before returning.
See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Confirm grc.db SCHEMA_DDL version matches expected `unified_mappings` columns.
- [ ] Confirm `db_metadata.engine_version` is read and passed through to output.
- [ ] Re-run smoke test: `python3 skills/atoms/gap-analysis/scripts/gap_analysis.py "CMMC 2.0 / NIST 800-171" --fedramp moderate --family AC IA SC --format summary`
- [ ] Confirm `human_review_required: true` still present in all output paths.
- [ ] Check that `fully_covered` count does not include `mapped_to` or `transitive_via_hitrust` rows.
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
