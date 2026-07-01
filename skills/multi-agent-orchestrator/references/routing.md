# Routing — task class → orchestration mode (canonical)

`task-decompose` uses this table to pick the mode. Mode follows the **task class**; it is
never widened to grant write or network access for convenience. When a task could be read
or write, choose the narrower (read) mode and record the ambiguity in a minority report.

## Zeroth: read-only by default

**Agents do not edit anything by default.** The baseline posture for every run is
read-only: agents scrape, crawl, read, and pass raw data + suggestions up the chain; the
manager synthesizes recommendations from that. `read-fanout` and `external` are read-only
modes. A plan becomes `mutate` (write access) **only** when the task explicitly asks to
change files — and even then each agent edits inside an isolated git worktree whose changes
are surfaced for human review before merge. When it is unclear whether a task edits, treat
it as read-only and note the ambiguity in a minority report. Write access is the narrow,
explicit exception; it is never granted to "make a task easier."

## First: solo or fan-out? (default solo)

Before choosing a mode, decide whether to fan out at all. **The default is one agent.**
Escalate to multi-agent fan-out only when a concrete trigger holds:

| Escalation trigger | Example |
|---|---|
| Many independent sources/files exceed one context | "read all 20 NIST family JSONs" |
| ≥2 independent sub-areas workable without shared state | "audit auth AND crypto AND logging" |
| Answer needs cross-checking from independent angles | "verify this mapping three ways" |
| Single-agent context would overflow | a 500-file migration |
| Unknown, breadth-first frontier (recursive discovery) | "find every place X could break" |

If none holds, run solo (`fan_out: false`, `agent_count: 1`, one scope). "It might be
faster" is not a trigger — multi-agent runs cost ~15× the tokens of a single pass.

## Table

| Task class | Example | Mode | Isolation | Engine | Stop defaults |
|---|---|---|---|---|---|
| Quick lookup / research | "read the docs and extract X" | `read-fanout` | read-only, shared FS | Workflow (default) | `k_dry 1`, `depth_cap 2`, `size_cap 24` |
| Deep / technical lookup | "trace how CCI provenance flows across the loaders" | `read-fanout` | read-only, shared FS | Workflow (default) | `k_dry 2`, `depth_cap 4`, `size_cap 24` |
| Canonical / seed update | "add feeds, re-pin sources, edit catalog JSON" | `mutate` | **git worktree per agent** (`isolation: "worktree"`) | Workflow (default) + worktree | `k_dry 1`, `depth_cap 1`, `size_cap 12` |
| External / MCP reach | "fetch upstream release notes / query an MCP server" | `external` | rate-limited + provenance | **feature-flag gated** | `k_dry 1`, `depth_cap 1`, `size_cap 8` |

The user's routing intent, encoded above: **quick and deep-technical lookups → read
fan-out; anything that touches canonical or seed data → file-mutating orchestration** with
worktree isolation so parallel edits cannot collide.

## Mode rules

- **read-fanout** — full recursion via the frontier. This is where recursive search earns
  its keep: agents surface leads, the manager spawns the next wave against them.
- **mutate** — `depth_cap 1`: a mutate wave does not self-expand into new edits. Each agent
  runs in its own git worktree (`isolation: "worktree"`) so concurrent edits never collide;
  the manager merges results after the wave. Residual leads are surfaced to the manager for
  an explicit next-wave decision, never auto-spawned.
- **external** — only runs when the relevant feature flag is effective (e.g. a web/MCP flag
  in `feature_flags.json`); otherwise the wave reports the gap and stops. Every external
  finding carries its provenance (URL/source + retrieved-at).

## Hybrid engine trigger (`orchestration_hybrid_mode`)

Default engine is the Workflow tool, driven directly by the manager. The declarative
`workflow.json` spec is compiled to a Workflow run **only** when the
`orchestration_hybrid_mode` flag is effective AND at least one trigger holds:

- **named/recurring** — the run is a saved, repeatable workflow (not a one-off);
- **replay** — deterministic replay/audit of a prior run is required;
- **scale** — planned agent count exceeds the size threshold for hand-driving (≥ `size_cap`).

Below those conditions the manager drives the Workflow tool directly — simpler, fewer
moving parts. The flag is off by default (`feature_flags.json`), so the direct path is the
norm.

## Non-negotiables

- **Agents never spawn agents.** A sub-agent cannot create or dispatch other agents. Every
  recursive wave requires the manager's recommendation AND express human approval; without
  it the run halts `awaiting_human_approval` and spawns nothing. Wave 1 is the human-
  initiated task; every wave beyond it needs fresh approval.
- **Read-only by default.** `mutate`/`write_access: true` is granted only on an explicit
  edit request; ambiguous read-vs-write → pick `read-fanout` and emit a `minority-report`
  note.
- Mode is chosen from this table by class — never escalated to `mutate`/`external` to make
  a task easier.
- Every finding an agent passes up carries a **specific citable source** in `provenance`
  (file path + locator, URL, or section id) — a vague placeholder fails validation and never
  reaches consolidation, so recommendations are always source-backed.
- Stop defaults come from here + `frontier-model.md`; they are not invented per run.
