# task-decompose — Maintainer Notes

## Non-Negotiables

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
- pass-01: a read-only extraction task yields `mode: read-fanout` with ≥2 scopes
- fail-01: an underspecified task returns an error, not fabricated scopes
- edge-01: a canonical-update task yields `mode: mutate` with `depth_cap: 1`
