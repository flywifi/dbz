# multi-agent-orchestrator — Maintainer Notes

## Non-Negotiable Invariants

- **Solo is the default.** `task-decompose` keeps a task on one agent unless an escalation
  trigger holds. Fan-out must be justified (the ~15× token reality), never reflexive.
- **Manager reads envelopes, never raw sub-agent transcripts.** This is the load-bearing
  rule; breaking it reintroduces context overflow and drift.
- **Every sub-agent is forced to return `orchestration-envelope.schema.json`.** Schema-
  forced returns are the primary drift lever — never accept free-text agent output into
  consolidation.
- **Every envelope passes `envelope-validate` before consolidation.** No half-formed merges.
- **High-materiality findings are adversarially verified before they are trusted.** Every
  `pending_verification` key goes through `finding-verify` (skeptics prompted to refute);
  refuted findings leave the trusted set. Never promote a conflict/low-confidence finding on
  a single pass.
- **Agents never spawn agents.** A sub-agent cannot create/dispatch other agents (the
  envelope schema has no spawn field; `additionalProperties: false` blocks it). Every
  recursive wave requires the manager's recommendation AND express human approval; an
  unapproved wave halts the run `awaiting_human_approval` and spawns nothing.
- **Stopping.** Hard caps stop always; while new leads remain the run continues (the judge
  never cuts a non-empty frontier short); a dry frontier always stops with `wave-judge`
  labeling it `saturated` (satisfied) or `frontier_exhausted` (unmet). The loop never
  invents leads.
- **Mode follows task class** (`references/routing.md`); never escalate to `mutate`/`external`.
- **`mutate` mode uses one git worktree per agent and `depth_cap 1`** — no auto-recursion
  into new edits.
- **Consolidation is deterministic** (`scripts/consolidate.py`): same envelopes → byte-
  identical output. Conflicts preserved, confidence floored, coverage honest, nothing
  fabricated.
- **Default engine is the Workflow tool driven directly**; the declarative `workflow.json`
  compiles to a run only when `orchestration_hybrid_mode` is effective and a trigger holds.
- Every envelope and the consolidated result carry `human_review_required: true`.

## Known Failure Modes

- A sub-agent returns prose instead of an envelope → `envelope-validate` fails it; re-run
  that scope with a stricter schema instruction. Never hand-parse the prose.
- Overlapping scopes in one wave → false conflicts in consolidation. Fix decomposition, not
  the merger.
- Frontier deduped against findings instead of `seen` → non-convergence (a rejected lead
  respawns forever). Dedup only against `seen` scope signatures.
- Runaway waves → guaranteed to stop by `size_cap` / `depth_cap`; if hit, surface the
  un-expanded frontier in the consolidated residual section, do not raise the caps silently.
- Hybrid flag on with no trigger condition → still runs direct; the flag alone does not
  force compilation.

## Approval-Gated Changes

- The envelope schema, the consolidation merge rules, and the routing table are contracts.
  Changing any of them requires updating the paired shared file in `skills/shared/`, the
  affected atoms' SKILL.md, and `tools/sync_check.py`, then re-running the drift guard.

## Regression Cases

See `evals/evals.json`:
- pass-01: a read-fanout run over agreeing envelopes yields a complete, merged result
- fail-01: an invalid envelope is blocked from consolidation, not merged
- edge-01: a mutate-mode plan carries depth_cap 1 and worktree isolation
