# task-decompose

Turn one large task into a first-wave partition plan for multi-agent fan-out: N
non-overlapping scopes, the orchestration mode to run them in, and the stop conditions.

## Scope

Given a task statement and the body of material it ranges over, produce a partition plan
the orchestrator can dispatch. Chooses the mode from the routing table
(`skills/multi-agent-orchestrator/references/routing.md`) and sets frontier stop
conditions from `frontier-model.md`. This atom plans a wave; it does not run agents.

## Input Schema

```json
{
  "task": "string — the work to decompose (e.g. 'extract every role across all NIST families')",
  "corpus_hint": "string? — optional description of the material (paths, counts) to size the partition",
  "max_scopes": "integer? — cap on first-wave scopes; default = concurrency cap (16)"
}
```

## Output Schema

```json
{
  "mode": "string — read-fanout | mutate | external (from routing table)",
  "scopes": "array — [{scope, rationale}] non-overlapping first-wave assignments",
  "stop_conditions": "object — {k_dry, depth_cap, size_cap} resolved for this mode",
  "minority_report": "object | null — populated if the mode choice is genuinely ambiguous",
  "human_review_required": true
}
```

## Do NOT use for

- Running the agents (the orchestrator/Workflow tool does that)
- Merging results (use `findings-consolidate`)
- Expanding a later wave from a frontier (use `frontier-expand`)
- Choosing `mutate` mode for anything the routing table classifies as read-only — mode is
  routed by task class, never guessed to grant write access.

## References

- `skills/multi-agent-orchestrator/references/routing.md` — task class → mode table
- `skills/shared/frontier-model.md` — stop-condition defaults per mode
- `skills/shared/minority-report.md` — record mode ambiguity here, never silently pick
