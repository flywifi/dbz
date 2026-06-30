---
name: claim-and-output-validator
description: validate risky claims, proof boundaries, and structured outputs before material is sent, reused, or promoted into durable workflows. use when chatgpt needs to review customer-facing copy, account briefs, questionnaires, or json outputs for unsupported claims, unsafe framing, missing caveats, malformed structure, or repeatable failure patterns with or without external evaluation credentials.
---

# Claim and Output Validator

## Mission

Act as a high-signal final review layer. Default to deterministic local checks, then escalate only when a stronger external eval path is actually available.

## Access modes

Read `references/access-modes.md` first.

## Core rules

- Prefer narrow, defensible language over broad impressive claims.
- Block unsupported superiority, guarantees, and blurred audit-versus-automation language.
- For structured outputs, fail closed when required keys are missing.
- Explain failures plainly and record the selected access mode in `validation/access-mode.json`.

## Workflow

1. Run `scripts/plan_access_mode.py`.
2. Pick the profile: `external_send`, `internal_brief`, `questionnaire`, or `structured_output`.
3. Run deterministic checks with `scripts/run_local_checks.py` and `scripts/validate_json_keys.py`.
4. Classify the result: `safe`, `narrow_before_use`, or `blocked`.
5. Emit repair guidance and blocked-claim details.
6. When a failure pattern is durable, use `scripts/promote_failures.py` to create reusable regression cases.

## Output contract

- `validation/access-mode.json`
- `validation/report.json`
- `validation/rewrite.md`
- `validation/blocked-claims.json`
- `validation/validation-summary.md`

## Pairings

- `thoropass-message-qa`
- `briefing-generator-companion`
- `skill-regression-and-red-team`

## Bundled resources

- `scripts/plan_access_mode.py`
- `scripts/run_local_checks.py`
- `scripts/validate_json_keys.py`
- `scripts/promote_failures.py`
- `references/access-modes.md`
- `references/profiles.md`
- `references/rule-catalog.md`
- `references/repair-guidance.md`
