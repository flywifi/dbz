# task-decompose — Maintainer Notes

## Non-Negotiables

- **Read-only is the default.** `write_access` is `false` and mode is `read-fanout`/
  `external` unless the task **explicitly asks to edit files**. Only then does mode become
  `mutate` with `write_access: true` (worktree-isolated, human-reviewed). Never emit
  `mutate`/`write_access: true` to "make a task easier"; an ambiguous task is read-only.
- **Solo is the default.** `fan_out` is `false` unless a concrete escalation trigger holds
  (many independent sources, ≥2 independent sub-areas, cross-checking needed, context
  overflow, or unknown breadth-first frontier). "Might be faster" is not a trigger — the
  ~15× token cost of multi-agent runs must be justified.
- When solo, `agent_count` is 1 and `scopes` has exactly one entry (the whole task).
- Mode is chosen from the routing table by task class — never widened to `mutate` or
  `external` to "make things easier". A read task gets `read-fanout`.
- Scopes in one wave must be non-overlapping; overlapping scopes corrupt the
  consolidation dedup (two agents claiming the same key look like a conflict).
- `stop_conditions` must come from `frontier-model.md` defaults for the chosen mode,
  not invented per call.
- `human_review_required` is always `true`.

## Known Failure Modes

- Task too vague to partition: return `{error: "task underspecified", needed: [...]}` —
  do not fabricate scopes.
- More natural scopes than `max_scopes`: emit the top `max_scopes` and push the remainder
  into the first wave's expected frontier (note in each scope rationale), never silently
  drop them.
- Genuinely ambiguous mode (could be read or mutate): emit both in `minority_report` and
  default to the **narrower** (read-only) mode.

## Regression Cases

See `evals/evals.json`:
- pass-01: a broad multi-source extraction yields `fan_out: true` with ≥2 scopes
- fail-01: an underspecified task returns an error, not fabricated scopes
- edge-01: a canonical-update task yields `mode: mutate` with `depth_cap: 1`
- solo-01: a small single-source lookup yields `fan_out: false`, `agent_count: 1`, one scope
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
