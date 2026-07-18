# MAINTAINER — compliance-report-analyzer

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`compliance-report-analyzer` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Strict extraction mode is the default — inference mode requires explicit support from source structure (exact identifiers, clearly labeled joins).
- Supported frameworks are fixed: SOC 1 T1/T2, SOC 2 T1/T2, ISO 27001, ISO 27002, HIPAA. No others without explicit user request.
- Source precedence order must be maintained (explicit text > source mappings > testing tables > user crosswalks > bundled assets).
- Never collapse duplicate mappings (one-to-many and many-to-one must be preserved exactly as found).
- Never convert one framework's control IDs to another unless the source set contains an explicit crosswalk.
- `human_review_required: true` in every output.
- No real customer data — all examples use placeholders.

## Known failure modes
- **Hallucinating control IDs**: generating plausible-looking SOC 2 criteria (CC6.X) when the source doesn't list them. Leave blank — never invent.
- **Scope expansion**: analyzing frameworks outside the supported list. Return an explicit scope error.
- **Collapsing duplicates**: merging "AC-2 → SOC 2 CC6.1, CC6.2" into "AC-2 → CC6.1" — this loses coverage information for the client.
- **Inference overflow**: starting with inference when extraction would work — always attempt extraction first.

## Fragile fallbacks that must not become defaults
- `inference_mode` must always be labeled in output (`extraction_mode: "inference"` vs `"extraction"`). Never omit the mode label.
- Bundled mapping assets in `assets/mappings/` are supporting crosswalks only — never the primary source when explicit report text exists.

## Regression cases to preserve
1. Returns `human_review_required: true` in every response.
2. Preserves exact auditor wording — never paraphrases or standardizes control text.
3. Returns `framework_in_scope: false` with a reason when an unsupported framework is requested.
4. Does not join tables on fuzzy name matches — only exact or clearly equivalent identifiers.
5. Returns `extraction_mode` label in every output record.

## Approval-gated changes
- Adding new supported frameworks (requires asset audit + extraction rule update).
- Changing the source precedence hierarchy.
- Modifying `references/output-schema.md` (the row-level output contract).
- Changing `references/extraction-rules.md` (inference mode criteria).
- Changing what counts as a "clearly labeled join."

## Minority-report policy
When two source artifacts provide conflicting control mappings for the same control ID,
emit `minority_report.conflicts` with both sources before returning the merged result.
See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Confirm `references/output-schema.md` and `references/extraction-rules.md` are in sync.
- [ ] Verify `assets/mappings/` crosswalk files match current `canonical-sources/` versions.
- [ ] Confirm supported framework list in SKILL.md matches the source precedence rules.
- [ ] Confirm `human_review_required: true` still present in all output paths.
- [ ] Check that no fabricated IDs appear in smoke-test output.
- [ ] Confirm SKILL.md still documents the advisory post-step (`tools/output_validate.py` on
      the finished deliverable) and that its check list matches the validator's current
      behavior (id reality, unsourced numbers, tier alignment, leak scan).
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
