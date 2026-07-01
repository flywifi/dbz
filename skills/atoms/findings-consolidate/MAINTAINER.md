# findings-consolidate — Maintainer Notes

## Non-Negotiables

- **Deterministic**: findings and conflicts are sorted by `key`; the same envelope set
  always yields byte-identical output. A verification test depends on this.
- **Never average** disagreeing values — record every variant and emit a
  `minority_report.conflicts` entry with `affected_keys`.
- **Confidence is floored**, never rounded up: a merged finding takes the lowest
  confidence among its sources.
- **Coverage is honest**: `state: complete` only when every agent is `complete` AND the
  residual frontier is empty. Any partial/blocked → `partial`.
- **Never fabricate** a key no agent found; a gap must trace to a real blocked scope or
  open frontier entry.
- `human_review_required` is always `true`.

## Known Failure Modes

- Empty envelope list: return coverage with `agents_total: 0`, empty findings, and a
  `residual_uncertainty` note that nothing was consolidated — not an error, but not a
  silent "complete" either.
- Mixed run_ids among envelopes: fail loudly — consolidating across runs is a bug.
- A finding whose `provenance` is blank should never arrive (envelope schema forbids it);
  if seen, treat the envelope as invalid upstream, do not merge it.

## Regression Cases

See `evals/evals.json`:
- pass-01: two agents agree on a key → single merged finding, coverage complete
- fail-01: two agents disagree on a key → conflict recorded, never averaged
- edge-01: one blocked agent → coverage.state partial, gap tied to the blocked scope
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
