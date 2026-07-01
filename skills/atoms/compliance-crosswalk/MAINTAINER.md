# MAINTAINER — compliance-crosswalk

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`compliance-crosswalk` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Returns exactly ONE operation: a mapping from one source control to one or more target controls.
- Never fabricates control IDs, relationship types, or strength values.
- Every mapping record must carry `mapping_source` (the crosswalk file or OLIR used).
- `human_review_required: true` in every output — relationship type and strength require human validation.
- Emits explicit `gaps[]` entries for target frameworks with no mapping rather than omitting them.
- Never claims a crosswalk relationship stronger than what the source data supports (never upgrades "mapped_to" to "Equal").

## Known failure modes
- **Scope creep**: being asked to compute overlap % or run gap analysis. Refuse and redirect to `overlap-query` or `gap-analysis`.
- **Fabricating ISO/SOC 2 IDs** when no ER crosswalk data exists for commercial frameworks. Return a `gap` with `reason: "No direct NIST→SOC 2 crosswalk in catalog; use ER crosswalk for commercial frameworks"`.
- **Conflating OLIR relationship types**: "Subset" and "Superset" are direction-specific — never swap them. Always include `direction` field.
- **Missing provenance on HITRUST transitive mappings**: HITRUST-bridged relationships must carry `"transitive_via_hitrust"` in `mapping_source`, never presented as direct.

## Fragile fallbacks that must not become defaults
- `confidence: "high"` is reserved for Confirmed-Direct OLIR STRM mappings. Transitive or heuristic mappings must be `confidence: "medium"` or `"low"`.
- `relationship_type: ""` (empty string) is a valid output when the source data doesn't specify — never fill with a guess.

## Regression cases to preserve
1. Returns `human_review_required: true` in every response.
2. Returns `gaps[]` for ISO 27001 when called with source_framework "NIST 800-53" and `include_enhancements: false` — not all enhancements have direct OLIR mappings.
3. Returns `mapping_source` on every mapping record — never omits it.
4. Returns `direction: "NIST→ISO 27001"` (not `"ISO 27001→NIST"`) for OLIR crosswalks anchored on NIST.
5. Does not merge one-to-many mappings into a single composite record.

## Approval-gated changes
- Changing how relationship types are sourced or normalized.
- Changing the confidence tier thresholds.
- Adding new source frameworks that require new crosswalk logic.
- Modifying the output schema (mappings[], gaps[] shape).

## Minority-report policy
When two crosswalk sources assign different relationship types to the same control pair,
emit `minority_report.conflicts` with both sources before returning. See canonical policy:
`skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Confirm SKILL.md output schema shape matches current grc.db `unified_mappings` columns.
- [ ] Verify `mapping_source` values match strings used in `build_db.py:load_crosswalks()`.
- [ ] Test against AC-2 fixture: `cross-mapping/tests/fixtures/` — confirm ISO/CMMC/HITRUST mappings unchanged.
- [ ] Confirm `human_review_required: true` still present in all output paths.
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
