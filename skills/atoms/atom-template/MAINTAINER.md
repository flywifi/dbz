# MAINTAINER — __ATOM_NAME__

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`__ATOM_NAME__` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
Shared (every dbz atom):
- Never fabricate control IDs, framework citations, CVE data, or crosswalk relationships.
- `human_review_required: true` on any compliance-facing or regulatory output.
- Source precedence: explicit DB data > crosswalk > source_manifest > blank.
- All DB reads go through grc.db; never bypass via raw JSON in canonical-sources/.
- References `skills/shared/minority-report.md` policy for conflicting source data.

Atom-specific:
- <bullets unique to this atom>

## Known failure modes
- <most common / highest-impact failure modes for this specific operation>

## Fragile fallbacks that must not become defaults
- <behaviors that are acceptable as a fallback but must not silently become the normal path>

## Regression cases to preserve
<numbered list; each maps to an evals/evals.json case>
1. <case>

## Approval-gated changes
- Changing the input or output schema — downstream workflow.json callers depend on it.
- Changing the DB query that powers this atom.
- Adding new output fields — add a corresponding eval case first.
- Modifying error message format — callers may parse it.

## Minority-report policy
When two data sources disagree (e.g., source_manifest version vs. feed_registry version),
emit `minority_report.conflicts` with both sources rather than silently choosing one.
See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every change)
- [ ] SKILL.md description still specific + scoped, with "Do NOT use for…" clause intact
- [ ] `python3 tools/sync_check.py` passes
- [ ] evals/evals.json has at least 3 cases; a case was added for any new behavior
- [ ] minority-report behavior unchanged unless explicitly approved
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
