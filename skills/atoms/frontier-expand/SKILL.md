# frontier-expand

Given the residual frontiers from a completed wave plus the set of already-covered
scopes, produce the next wave's scopes — or signal that the search is saturated.

## Scope

Implements the dedup-and-recurse step of `skills/shared/frontier-model.md`. Collects
every `residual_frontier[]` lead from a wave's envelopes, drops any whose scope signature
is already in `seen`, and returns the deduplicated next wave. Signals saturation when
nothing new remains. This atom decides *what to run next*; it does not run agents.

## Input Schema

```json
{
  "envelopes": "array — this wave's validated envelopes (frontier leads are read from them)",
  "seen": "array — scope signatures already dispatched in prior waves",
  "wave": "integer — current wave number (for depth_cap check)",
  "stop_conditions": "object — {k_dry, depth_cap, size_cap} from the run",
  "agents_so_far": "integer — total agents dispatched (for size_cap check)"
}
```

## Output Schema

```json
{
  "next_scopes": "array — [{scope, reason, parent_task_id}] deduped leads for the next wave (empty if none)",
  "saturated": "boolean — true when no new leads remain",
  "stop_condition": "string | null — saturated | depth_cap_reached | size_cap_reached, or null to continue",
  "seen_out": "array — updated scope-signature set including this wave's scopes",
  "human_review_required": true
}
```

## Do NOT use for

- Deduping against consolidated *findings* — dedup only against `seen` scope signatures.
  Deduping against findings would let a rejected lead reappear each wave and the run would
  never converge (see frontier-model.md).
- Auto-expanding a `mutate`-mode wave — mutation leads are surfaced to the manager for an
  explicit decision, never auto-spawned (depth_cap 1).
- Deciding the final answer (use `findings-consolidate`).

## References

- `skills/shared/frontier-model.md` — the recursion + stop-condition spec
- `skills/shared/minority-report.md` — never fabricate a lead to keep a run going
