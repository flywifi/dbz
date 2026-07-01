# instruction-audit — Maintainer Notes

## Non-Negotiables

- **Read-only.** This atom never edits or rewrites instruction files — it reports
  contradictions for a human to resolve.
- **Adversarial-consensus, not single-pass.** Every flagged contradiction must survive
  `finding-verify` skeptics (independent, prompted to refute) before it is reported.
  Single-model confidence is not sufficient — it over-reports.
- **Block decomposition is deterministic** (`instruction_blocks.py`): the same files always
  yield the same blocks and the same pairs, so the LLM judgment is applied to a stable frame.
- **Provenance is a specific `file:section`** for every reported contradiction — an
  unciteable contradiction is not reported.
- `human_review_required` is always `true`.

## Known Failure Modes

- Over-reporting stylistic tension as contradiction → the adversarial pass filters these;
  keep the skeptic prompt biased toward "refute unless it is a real logical conflict."
- A skill with sparse structure (few headings) yields few pairs → decomposition still runs;
  report low confidence rather than inventing contradictions.
- Cross-file rule (SKILL.md vs atoms.json schema) needs the atom registered — if absent,
  note the gap, do not fabricate a match.

## Regression Cases

See `evals/evals.json`:
- pass-01: a skill whose "Do NOT use for" contradicts its Scope → one confirmed contradiction
- fail-01: a consistent skill → zero contradictions (no false positive)
- edge-01: decomposition of a real skill yields the expected block classes (deterministic)
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
