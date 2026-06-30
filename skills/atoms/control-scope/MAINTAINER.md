# MAINTAINER — control-scope

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`control-scope` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Never fabricate control IDs — all results from grc.db only.
- Unknown framework_id must return an error, not an empty list (empty = valid framework with 0 controls).
- References `skills/shared/minority-report.md` policy.

## Known failure modes
- **Silent empty on bad ID**: returning `{"controls": [], "count": 0}` when the framework_id
  is simply unknown (vs. a valid framework that happens to have 0 controls in the DB).
  Must distinguish with an error message.

## Regression cases to preserve
1. 'fedramp-moderate' → count ≥ 300 controls (pass-01)
2. Unknown framework_id → error, not empty list (fail-01)
3. Framework with controls in both NIST and ER sides → minority_report if counts diverge (edge-01)

## Approval-gated changes
- Changing which DB tables are queried (controls vs er_controls).
- Changing the output schema — callers in workflow.json depend on `controls[].id`.

## Minority-report policy
When NIST and ER control counts for the same framework diverge by more than 5%, emit
`minority_report.conflicts` with both counts. See `skills/shared/minority-report.md`.

## Update checklist
- [ ] SKILL.md "Do NOT use for…" clause intact
- [ ] `python3 tools/sync_check.py` passes
- [ ] evals/evals.json has ≥3 cases
