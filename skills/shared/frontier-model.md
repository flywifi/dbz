# Frontier Model — recursive fan-out and stop conditions (canonical)

How the manager turns a big task into waves of sub-agents that recurse into what
they didn't reach, and how it knows when to stop. Adapted from the traversal stop
conditions proven in the sibling educator-tools repo, restated for agent fan-out.

The `residual_frontier[]` field on every envelope (see
`orchestration-envelope.schema.json`) is the whole mechanism: each agent reports the
leads it saw but did not cover; the manager collects those, removes anything already
covered, and spawns the next wave against what remains.

## The loop

```
seen = set()                      # scope-signatures already dispatched
frontier = decompose(task)        # wave-1 scopes (from task-decompose atom)
dry_waves = 0
wave = 0

while frontier and wave < DEPTH_CAP and total_agents < SIZE_CAP:
    wave += 1
    envelopes = fan_out(frontier)              # one agent per scope, schema-forced
    envelopes = [e for e in envelopes if envelope_validate(e)]   # drift gate
    seen |= { signature(s) for s in frontier }

    next_frontier = [
        lead for e in envelopes for lead in e.residual_frontier
        if signature(lead.scope) not in seen
    ]

    if not next_frontier:
        dry_waves += 1
        if dry_waves >= K_DRY:                  # saturated
            break
    else:
        dry_waves = 0
    frontier = dedup(next_frontier)
```

## Stop conditions (any one ends the run)

| Condition | Meaning | Default |
|---|---|---|
| **saturated** (loop-until-dry) | `K_DRY` consecutive waves produced no new frontier | `K_DRY = 1` for quick lookups, `2` for deep/technical |
| **depth_cap_reached** | recursion reached `DEPTH_CAP` waves | `2` quick, `4` deep, `1` mutate |
| **size_cap_reached** | total agents hit `SIZE_CAP` | `24` (well under the Workflow 1000-agent lifetime cap) |
| **budget_exhausted** | `budget.remaining()` below a floor (only if a token target was set) | floor `50_000` |
| **frontier_exhausted** | frontier empty and nothing new to expand | n/a — natural end |

Prefer **loop-until-dry** over a fixed depth: a fixed `DEPTH_CAP` is a backstop, not the
primary signal. K consecutive empty waves is the real "we got everything" test.

## Concurrency

Within a wave, agents run concurrently but are capped by the runtime at
`min(16, cores - 2)` simultaneous agents. A wave with more scopes than that queues the
excess — still correct, just serialized in part. Keep individual waves at or below the
cap when latency matters; split very wide waves into two.

## Dedup discipline (why the run terminates)

- `signature(scope)` = a normalized form of the scope string (lowercased, whitespace-
  collapsed). Dedup the frontier against `seen`, **not** against the consolidated
  findings — deduping against findings would let a rejected lead reappear every wave and
  the run would never converge.
- A lead already in `seen` is dropped silently; it was (or is being) covered.
- If two agents surface the same new lead in one wave, it enters the next wave once.

## Mode interaction

- **read-fanout**: full recursion as above (this is where the frontier earns its keep).
- **mutate**: `DEPTH_CAP = 1` by default — mutation waves do not self-expand into new
  edits without the manager re-deciding scope. A mutate agent may still report a
  `residual_frontier`, but those leads are surfaced to the manager for an explicit
  decision, not auto-spawned.
- **external**: recursion allowed only when the external feature flag is effective;
  otherwise the wave runs once and reports the gap.

## What the manager never does

- Never read a sub-agent's raw transcript to "check" it — read the envelope only.
- Never keep spawning past a stop condition to "be thorough" — record what was left in
  the consolidated report's residual section instead.
- Never silently drop a `blocked` scope — it rolls up as reduced coverage.
