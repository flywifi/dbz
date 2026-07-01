# wave-judge — Maintainer Notes

## Non-Negotiables

- The composite is deterministic (`skills/multi-agent-orchestrator/scripts/judge.py`): same dimension scores → same
  recommendation. Weights (`coverage .35, consistency .25, provenance .20, saturation .20`)
  and thresholds (`stop ≥ 0.80`, `coverage floor 0.70`) are fixed in the script, not
  re-decided per call.
- **Coverage floor gates stop**: a high composite with coverage < 0.70 still returns
  `continue`. Thin coverage can never be papered over by the other dimensions.
- The judge is a **complementary** stop signal. It never overrides a non-empty frontier —
  if leads remain, the run continues regardless of the composite.
- A missing/invalid dimension scores 0.0 (toward `continue`); never fabricate a pass.
- `human_review_required` is always `true`.

## Known Failure Modes

- All dimensions high but frontier non-empty: recommendation may be `stop`, but the manager
  keeps going because the frontier is not dry — the two signals are AND-ed for stopping.
- Judge over-scores coverage: caught later by frontier saturation (residual leads remain).
  The two signals are deliberately redundant so a bad score on one does not end the run.
- Scores outside 0–1: clamped to [0,1]; non-numeric → treated as missing (0.0).

## Regression Cases

See `evals/evals.json`:
- pass-01: strong wave (all high) → stop
- fail-01: thin coverage (0.5) with high others → continue (coverage floor)
- edge-01: missing dimensions → continue, missing_dimensions listed
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
