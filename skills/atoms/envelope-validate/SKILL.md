# envelope-validate

Validate a single returned agent envelope against `orchestration-envelope.schema.json`
**before** it is allowed into consolidation. This is the run-time anti-drift gate: a
malformed envelope is a hard stop, not a silent merge.

## Scope

Runs `scripts/validate_envelope.py` (in the orchestrator skill) over one envelope object
and reports pass/fail with the specific schema violations. The manager calls this on
every envelope from every wave; any failure blocks that envelope from consolidation and
is surfaced for a re-run, never merged in a partial state.

## Input Schema

```json
{
  "envelope": "object — a single agent return to check",
  "schema_path": "string? — default skills/shared/orchestration-envelope.schema.json"
}
```

## Output Schema

```json
{
  "valid": "boolean",
  "violations": "array — [{path, message}] JSON-path + reason for each failure; empty when valid",
  "task_id": "string — echoed from the envelope for traceability (or null if unreadable)",
  "human_review_required": true
}
```

## Do NOT use for

- Validating the *content* of findings (schema conformance ≠ correctness — that is the
  agent's and the human reviewer's job)
- Consolidating (use `findings-consolidate`)
- "Repairing" a bad envelope by filling in defaults — a malformed envelope fails; it is
  re-run, never patched into looking valid.

## References

- `skills/shared/orchestration-envelope.schema.json` — the contract being enforced
- `skills/multi-agent-orchestrator/scripts/validate_envelope.py` — the checker
- `skills/shared/minority-report.md` — validation never fabricates a pass
