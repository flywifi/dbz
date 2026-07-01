# Consolidation Rules — deterministic merge of agent envelopes (canonical)

How the manager turns a pile of envelopes into one consolidated result. The rule that
makes this trustworthy: **the LLM judges with evidence, a script does the arithmetic.**
Consolidation is mechanical and reproducible — the same set of envelopes always merges
to the same output. `scripts/consolidate.py` in the orchestrator skill implements this;
this file is the spec it obeys.

## Inputs

A list of envelopes conforming to `orchestration-envelope.schema.json`, all from one run.
Every envelope must already have passed `envelope-validate` — a malformed envelope is a
hard stop, never silently merged.

## Merge algorithm

1. **Collect findings** across all envelopes, grouped by `key`.
2. **Per key:**
   - **One finding, or all agree** → emit once. Merge provenance (union of sources).
     Consolidated confidence = the **lowest** confidence among the merged findings
     (a chain is only as strong as its weakest link — never round up).
   - **Two or more disagree on `value`** → do **not** average, blend, or pick silently.
     Emit the key once with `status: "conflict"` and record every variant, then push a
     matching entry into the consolidated `minority_report.conflicts` with the
     `affected_keys` and both sources. The human/manager resolves later.
3. **Roll up coverage** (arithmetic, not judgment):
   - `agents_total`, `agents_complete`, `agents_partial`, `agents_blocked`.
   - `coverage_state`: `complete` only if every agent is `complete` **and** the frontier
     is empty; otherwise `partial` with the blocked/partial scopes listed.
   - `sources_read` = union of every envelope's `provenance.sources_read`.
   - `residual_frontier` = union of all un-covered leads still open at stop time.
4. **Roll up minority reports**: concatenate each envelope's `minority_report` buckets
   (`conflicts`, `failed_to_merge`, `residual_uncertainty`) plus the cross-agent
   conflicts found in step 2. `decision_log` records why the run stopped and which stop
   condition fired.
5. **Flag high-materiality findings for verification**: emit `pending_verification` — the
   sorted set of keys that are either a `conflict` or merged at `low`/`uncertain`
   confidence. These are NOT auto-trusted; the manager routes them to adversarial
   verification (below) before they count.
6. **Emit** one consolidated object with `pending_verification` and
   `human_review_required: true`.

## Adversarial verification (after consolidation, before trust)

Consolidation decides *what merged*; it does not decide *what is true*. Every key in
`pending_verification` is checked by the `finding-verify` atom: N independent skeptic agents
prompted to **refute** it, tallied deterministically in `scripts/verify.py`.

- **confirmed** (strict confirming majority) → finding kept, annotated.
- **refuted** (refuting majority, or a tie — burden of proof is on the finding) → finding
  **leaves `findings[]`** and is recorded in `minority_report.failed_to_merge`. Never
  silently dropped, never fabricated back in without new skeptic evidence.
- **unverified** (skeptics could not check — unreachable source, rate limit) → finding kept
  but flagged in `residual_uncertainty`. Unverifiable is never treated as refuted.

Only high-materiality keys are verified — not every finding — because multi-agent
verification is itself expensive (~15× token reality). `apply_verdicts()` folds the results
back deterministically.

## Hard rules (inherited from minority-report.md)

- **Never fabricate.** A key that no agent found is absent, or listed as a gap tied to a
  real `blocked`/`residual_frontier` entry — never invented to look complete.
- **Never average conflicting values.** Record both; escalate via minority_report.
- **Never round confidence up.** Merged confidence is the floor of its inputs.
- **Never report `coverage_state: complete` when any agent was partial/blocked** or the
  frontier is non-empty. Honest partial beats false complete.
- **Determinism:** ordering of findings and conflicts is sorted by `key` so byte-for-byte
  output is stable across runs (a verification test relies on this).

## Output shape

```
{
  "run_id": "...",
  "coverage": {
    "state": "complete | partial",
    "agents_total": N, "agents_complete": N, "agents_partial": N, "agents_blocked": N,
    "sources_read": [...],
    "stop_condition": "saturated | depth_cap_reached | size_cap_reached | budget_exhausted"
  },
  "findings": [ { "key": "...", "status": "merged | conflict", "value": ..., "provenance": [...], "confidence": "..." } ],
  "residual_frontier": [ { "scope": "...", "reason": "..." } ],
  "pending_verification": [ "key1", "key2" ],
  "minority_report": { "decision_log": {...}, "conflicts": [...], "failed_to_merge": [...], "residual_uncertainty": [...] } | null,
  "human_review_required": true
}
```

## Why a script, not a prompt

If the manager consolidated by reasoning over envelopes in-context, two things drift:
the merge could vary run-to-run, and a large pile of envelopes would blow the context
window. A deterministic script fixes both — the manager reads only the small consolidated
object, and the merge is reproducible and auditable.
