# envelope-validate — Maintainer Notes

## Non-Negotiables

- A failing envelope is **blocked from consolidation** — never merged in a degraded form,
  never auto-repaired with defaults.
- `human_review_required` must be `true` on the envelope; an envelope where it is missing
  or not `true` is a validation failure (the schema pins it to `const: true`).
- Validation checks structure only. It must never assert anything about whether the
  findings are *correct* — that would be fabricating a quality signal.
- Determinism: the same envelope always yields the same violations, sorted by JSON path.

## Known Failure Modes

- Non-object input: return `{valid: false, violations: [{path: "$", message: "not an object"}], task_id: null}`.
- Unknown extra fields: schema is `additionalProperties: false`, so stray keys fail —
  this is intentional (an agent adding fields is drift).
- `residual_frontier` present but malformed items: fail with the item path; do not drop
  the bad items and pass the rest.
- Schema file missing: return an error, never a fabricated `valid: true`.

## Regression Cases

See `evals/evals.json`:
- pass-01: a well-formed envelope validates with empty violations
- fail-01: an envelope missing `residual_frontier` fails with a pointed violation
- edge-01: an envelope with `human_review_required: false` fails (const true enforced)
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
