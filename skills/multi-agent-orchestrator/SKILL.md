# multi-agent-orchestrator

The manager's playbook for running many sub-agents on one task with discipline: decompose
→ fan out → validate every return → consolidate → recurse into what was missed → stop
when saturated. Turns the ad-hoc "spawn a few agents and eyeball their answers" pattern
into a repeatable, drift-resistant capability.

## The one rule that makes this work

**The manager reads envelopes, never raw transcripts.** Every sub-agent returns one
identically-shaped envelope (`skills/shared/orchestration-envelope.schema.json`). Because
the shape is fixed and schema-forced, consolidation is mechanical and the manager's
context never fills with raw agent output.

## Scope

Use when a task is bigger than one agent should hold: reading across many files/sources,
extracting a taxonomy, auditing a large surface, or applying one pattern across many
targets. Picks an orchestration **mode** by task class (see `references/routing.md`),
sets stop conditions (`skills/shared/frontier-model.md`), and consolidates deterministically
(`skills/shared/consolidation.md`).

## Default to one agent

**Fan-out is off by default.** `task-decompose` keeps a task solo (one agent, one scope)
unless a concrete escalation trigger holds — many independent sources, ≥2 independent
sub-areas, cross-checking needed, context overflow, or an unknown breadth-first frontier.
Multi-agent runs cost ~15× the tokens of a single pass, so the fan-out has to earn itself.
When a task stays solo, the machinery below collapses to a single agent returning one
envelope; the discipline (schema-forced return, human_review_required) still applies.

## The loop (what the manager does each run)

1. **Decompose + gate** — `task-decompose` first decides solo vs fan-out. If solo, run one
   agent and skip to step 4. If fan-out: mode + N non-overlapping scopes + stop conditions.
2. **Fan out a wave** — spawn one agent per scope, each **forced to return the envelope
   schema**. Default engine: the Claude Code Workflow tool (`pipeline()` for per-item
   recursion, `parallel()` only when a barrier is genuinely needed).
3. **Validate** — run `envelope-validate` on every return. A malformed envelope is a hard
   stop for that scope (re-run it); it never enters consolidation half-formed.
4. **Consolidate** — `findings-consolidate` merges the wave (dedup by key, conflicts
   preserved, confidence floored, coverage honest). It emits `pending_verification` — the
   high-materiality keys (conflicts, low/uncertain confidence) that must be skeptic-checked.
5. **Adversarially verify** — for each `pending_verification` key, run `finding-verify`:
   independent skeptics prompted to *refute*, tallied deterministically. Refuted findings
   leave the trusted set and land in `minority_report.failed_to_merge`; unverifiable ones
   stay flagged. High-stakes findings are never promoted on a single pass.
6. **Judge** — `wave-judge` scores the wave (coverage/consistency/provenance/saturation) and
   recommends stop or continue: a quality stop signal that complements frontier saturation.
7. **Recurse** — `frontier-expand` dedups each envelope's `residual_frontier` against the
   run's `seen` set and returns the next wave — or signals saturation.
8. **Stop** — when the frontier is dry (K dry waves) **and** the judge says quality is
   sufficient, or when depth/size capped or budget exhausted. Record whatever was left in
   the consolidated residual section — never keep spawning "to be safe."

## Engine selection

- **Default: Workflow tool.** The manager hand-writes a Workflow script per run that reads
  the contracts, fans out with `schema: orchestration-envelope.schema.json`, recurses via
  `pipeline()` + loop-until-dry, and calls `scripts/consolidate.py` on the collected
  envelopes.
- **Hybrid (declarative `workflow.json` compiled to a Workflow run)** activates only when
  the `orchestration_hybrid_mode` feature flag is effective and a trigger condition holds
  (named/recurring workflow, deterministic replay needed, or agent count over threshold).
  See `references/routing.md` and `canonical-sources/feature_flags.json`.

## Modes (routed by task class, never guessed)

| Mode | For | Isolation |
|---|---|---|
| `read-fanout` | quick + deep-technical lookups (read-only) | shared FS, read-only |
| `mutate` | canonical/seed edits, migrations | one git worktree per agent (`isolation: "worktree"`); `depth_cap 1` |
| `external` | web / MCP / upstream fetches | feature-flag gated; rate-limited + provenance |

## Do NOT use for

- A task one agent can finish — orchestration overhead isn't free.
- Running `mutate` mode for a read-only task to "save a step" — mode follows task class.
- Reading sub-agent transcripts to check them — read the envelope; that is the contract.
- Resolving conflicts automatically — consolidation *preserves* them for human review.

## Atoms this skill orchestrates

`task-decompose` (solo/fan-out gate) · `envelope-validate` (anti-drift gate) ·
`findings-consolidate` (deterministic merge) · `finding-verify` (adversarial skeptics) ·
`wave-judge` (rubric stop signal) · `frontier-expand` (recursion).

## References

- `skills/shared/orchestration-envelope.schema.json` — the fixed agent return
- `skills/shared/frontier-model.md` — solo default, recursion + the two AND-ed stop signals
- `skills/shared/consolidation.md` — deterministic merge + adversarial-verify stage
- `skills/shared/minority-report.md` — disagreement preservation (non-negotiable)
- `references/routing.md` — task class → mode + hybrid trigger conditions
- `scripts/validate_envelope.py`, `scripts/consolidate.py`, `scripts/verify.py`,
  `scripts/judge.py` — the deterministic backers (agents judge, scripts compute)
- `workflow.json` — declarative spec (hybrid source of truth)
