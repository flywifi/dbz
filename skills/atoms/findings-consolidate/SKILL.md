# findings-consolidate

Deterministically merge a set of validated agent envelopes into one consolidated result:
dedup findings by key, preserve conflicts as a minority report, roll up coverage honestly.

## Scope

Runs `scripts/consolidate.py` (in the orchestrator skill) over a list of envelopes that
have **already** passed `envelope-validate`. Implements the rules in
`skills/shared/consolidation.md`: agree → merge (confidence floored), disagree → record
both in `minority_report.conflicts` (never averaged), partial/blocked → coverage < 100%.
The same envelopes always produce byte-identical output (findings sorted by key).

## Input Schema

```json
{
  "run_id": "string — identifier for this orchestration run",
  "envelopes": "array — validated envelopes conforming to orchestration-envelope.schema.json",
  "stop_condition": "string? — the frontier stop condition that ended the run"
}
```

## Output Schema

```json
{
  "run_id": "string",
  "coverage": "object — {state, agents_total, agents_complete, agents_partial, agents_blocked, sources_read, stop_condition}",
  "findings": "array — [{key, status: merged|conflict, value, provenance[], confidence}] sorted by key",
  "residual_frontier": "array — union of open leads at stop time",
  "minority_report": "object | null — rolled-up conflicts, failed_to_merge, residual_uncertainty",
  "human_review_required": true
}
```

## Do NOT use for

- Consolidating envelopes that have not passed `envelope-validate` (garbage in)
- Resolving conflicts — this atom *preserves* them for a human; it never picks a winner
- Averaging or blending disagreeing values (explicitly forbidden)
- Reporting `coverage.state: complete` when any agent was partial/blocked

## References

- `skills/shared/consolidation.md` — the merge spec this atom obeys
- `skills/shared/minority-report.md` — conflict-preservation rules
- `skills/multi-agent-orchestrator/scripts/consolidate.py` — the deterministic merger
