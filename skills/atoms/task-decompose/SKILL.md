# task-decompose

Decide whether a task needs multiple agents at all — and if so, turn it into a first-wave
partition plan: N non-overlapping scopes, the orchestration mode, and the stop conditions.

## Default: one agent

**Fan-out is off by default.** Multi-agent runs cost ~15× the tokens of a single pass, so a
task runs solo (`fan_out: false`, `agent_count: 1`, one scope = the whole task) unless a
concrete escalation trigger holds. Only escalate to fan-out when at least one is true:

- the corpus spans **many independent sources/files** that don't fit one agent's context;
- the task has **≥2 independent sub-areas** that can be worked without shared state;
- the answer needs **cross-checking** from independent angles (adversarial verification);
- a single agent's context would **overflow** on the material;
- the frontier is **unknown/breadth-first** (recursive discovery, not a known lookup).

If none holds, stay solo. "It might be faster" is not a trigger.

## Scope

Given a task and the material it ranges over, first apply the solo-vs-fan-out gate above.
If fanning out, produce a partition plan the orchestrator can dispatch: pick the mode from
the routing table (`skills/multi-agent-orchestrator/references/routing.md`) and set stop
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
  "fan_out": "boolean — false (solo, the default) unless an escalation trigger holds",
  "agent_count": "integer — 1 when solo; N when fanning out",
  "escalation_trigger": "string | null — which trigger justified fan-out (null when solo)",
  "mode": "string — read-fanout | mutate | external (from routing table)",
  "scopes": "array — [{scope, rationale}]; exactly one entry (the whole task) when solo",
  "stop_conditions": "object — {k_dry, depth_cap, size_cap} resolved for this mode",
  "minority_report": "object | null — populated if the mode or solo/fan-out choice is genuinely ambiguous",
  "human_review_required": true
}
```

## Do NOT use for

- Fanning out a task one agent can finish — solo is the default; escalate only on a trigger
- Running the agents (the orchestrator/Workflow tool does that)
- Merging results (use `findings-consolidate`)
- Expanding a later wave from a frontier (use `frontier-expand`)
- Choosing `mutate` mode for anything the routing table classifies as read-only — mode is
  routed by task class, never guessed to grant write access.

## References

- `skills/multi-agent-orchestrator/references/routing.md` — task class → mode table
- `skills/shared/frontier-model.md` — stop-condition defaults per mode
- `skills/shared/minority-report.md` — record mode ambiguity here, never silently pick
