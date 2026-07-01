# MAINTAINER — audit-artifact-normalizer

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`audit-artifact-normalizer` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Inventory before reasoning — always produce a file manifest before any extraction or inference.
- Access mode must be determined by `references/access-modes.md` and recorded in `normalized/access-mode.json`.
- Never invent extracted content when only a routing plan is available — placeholder, not hallucination.
- Source provenance must be preserved for every file, expansion, duplicate, and warning.
- Prefer the highest-quality path that does not require new credentials.
- `human_review_required: true` in every output that contains inferred relationships.

## Known failure modes
- **Provenance loss**: normalizing two files with the same name from different directories into one record without tracking the source paths. Each file needs a unique `source_path`.
- **Premature extraction**: jumping to content extraction before completing the manifest. Always manifest-first.
- **Access mode drift**: defaulting to a credential-requiring path without checking whether a local-only path would work. Always run access-mode check first.
- **Expanding archives silently**: unzipping files without noting the expansion in the manifest — downstream tools won't know the artifact count changed.

## Fragile fallbacks that must not become defaults
- When Docling-style integrations are unavailable, fall back to native PDF/text extraction — never fail silently with empty output.
- `access-mode.json` must always be written, even for local-only runs (`access_mode: "local_artifact"`).

## Regression cases to preserve
1. Returns a complete file manifest before any extraction step.
2. Logs every duplicate filename with both paths — never silently deduplicates.
3. Records the selected `access_mode` in output.
4. Does not expand archives without flagging the expansion in the manifest.
5. Returns `human_review_required: true` whenever inferred relationships are present.

## Approval-gated changes
- Adding new access modes to `references/access-modes.md`.
- Changing the manifest schema (fields, required entries).
- Changing how duplicates are detected or flagged.

## Minority-report policy
When two source files provide conflicting metadata for the same artifact (e.g., differing dates,
framework labels), emit `minority_report.conflicts` rather than silently picking one.
See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Confirm `references/access-modes.md` access-mode hierarchy is current.
- [ ] Verify manifest schema matches downstream skills' expected input format.
- [ ] Test with a mixed archive (PDF + XLSX + screenshots) to confirm provenance tracking.
- [ ] Confirm `human_review_required: true` present in all inferred-relationship output paths.
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
