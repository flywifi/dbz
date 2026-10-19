# MAINTAINER — source-manifest-lookup

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`source-manifest-lookup` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Read-only. The manifest is a canonical registry; writes go through `tools/registry_io.py`.
- An unknown key or role is an error with exit 1 — never synthesize or guess an entry.
- Entries are returned verbatim; no field is reinterpreted or defaulted.
- `human_review_required` is always `true`.

## Known failure modes
- **Role ambiguity**: several sources can share a role; role mode returns all of them and
  the caller must choose — the atom never picks one.
- **Renamed sources**: a re-pin can change a source's `file`/`sheet` (SCF renames its sheet
  every release); callers must read those from the entry, never cache them.

## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.

## Regression cases to preserve
- `--key scf-controls` returns exactly one entry with `count: 1`.
- `--key nonexistent-xyz` returns an error, not an empty entry.
