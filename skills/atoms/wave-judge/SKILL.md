# wave-judge

Score a completed wave on a 0.0–1.0 rubric and recommend **stop** or **continue** — a
quality-based stop signal that complements frontier saturation. The agent supplies a score
per dimension with evidence; `skills/multi-agent-orchestrator/scripts/judge.py` computes the weighted composite and the
recommendation (the judgment is the LLM's, the arithmetic is the script's).

## Scope

After a wave consolidates, the manager asks one judge agent to score four dimensions of the
consolidated result. `judge.py` combines them deterministically and returns a stop/continue
recommendation. The manager stops when the frontier is dry **or** the judge says quality is
sufficient; it continues when either says there is more to do. Modeled on Anthropic's
finding that a single LLM-as-judge call with rubric scores is the most consistent quality
signal.

## Input Schema

```json
{
  "coverage": "number 0.0–1.0 — how much of the intended scope the wave reached",
  "consistency": "number 0.0–1.0 — freedom from unresolved conflicts in merged findings",
  "provenance": "number 0.0–1.0 — how well findings are sourced (no blank/weak provenance)",
  "saturation": "number 0.0–1.0 — confidence the residual frontier is genuinely exhausted",
  "evidence": "string? — the judge's rationale for the scores (for the human reviewer)"
}
```

## Output Schema

```json
{
  "composite": "number 0.0–1.0 — weighted score (coverage .35, consistency .25, provenance .20, saturation .20)",
  "recommendation": "string — stop | continue",
  "weakest_dimension": "string — the lowest-scoring dimension (where to focus a next wave)",
  "dimension_scores": "object — clamped per-dimension scores",
  "human_review_required": true
}
```

## Rule

`stop` only when composite ≥ 0.80 **and** coverage ≥ 0.70 — a strong composite cannot
paper over thin coverage. A missing dimension scores 0.0 (pushes toward `continue`); the
judge never fabricates a pass.

## Do NOT use for

- Verifying individual findings (use `finding-verify`)
- Overriding a non-empty frontier — if leads remain, the run continues regardless of a high
  composite; the judge is a *complementary* stop signal, not a shortcut past unfinished work
- Deciding the mode / decomposition (use `task-decompose`)

## References

- `skills/multi-agent-orchestrator/scripts/judge.py` — deterministic composite + recommendation
- `skills/shared/frontier-model.md` — how the stop signals combine
- `skills/shared/minority-report.md` — never fabricate a passing score
