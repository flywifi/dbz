# finding-verify — Maintainer Notes

## Non-Negotiables

- Skeptics are **independent** and prompted to **refute** — not to confirm. A confirmation-
  biased prompt defeats the purpose.
- The tally is deterministic (`skills/multi-agent-orchestrator/scripts/verify.py`): same votes → same verdict.
- **Ties go to refuted** (burden of proof on the finding); **majority-unable → unverified**
  (unverifiable is not refutation).
- A **refuted** finding leaves `findings[]` and is recorded in
  `minority_report.failed_to_merge`. It is never silently dropped and never fabricated back
  in on a later pass without new skeptic evidence.
- `human_review_required` is always `true`.

## Known Failure Modes

- Zero votes supplied: verdict `unverified` (cannot confirm nothing) — never default to
  confirmed.
- Verifying a finding not in `pending_verification`: allowed but wasteful; the orchestrator
  should restrict skeptics to that set (token cost).
- Skeptics all "unable" due to a rate limit / offline source: `unverified`, and the finding
  stays flagged — mirrors Claude Code /deep-research treating unverifiable ≠ refuted.

## Regression Cases

See `evals/evals.json`:
- pass-01: confirming majority → confirmed
- fail-01: refuting majority → refuted
- edge-01: majority unable → unverified (unreachable source, not a refutation)
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
