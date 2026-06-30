# MAINTAINER — changelog-query

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`changelog-query` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- `change_type` values must be from the controlled vocabulary: 'major_revision', 'minor_update',
  'retired', 'new_entry'. Never return an unconstrained string.
- All filters are AND-combined, never OR.
- Empty result set returns `{"entries": [], "count": 0}` — not an error.
- `human_confirmed` field must always be present in output (may be false for machine-detected entries).
- References `skills/shared/minority-report.md` policy.

## Known failure modes
- **change_type vocabulary drift**: if new change types are added to framework_changelog.json
  without updating this atom's controlled vocabulary, callers get unexpected values.
- **Missing human_confirmed**: old changelog entries may lack this field; default to `false`.

## Regression cases to preserve
1. Query with no filters → returns all entries; count ≥ 0 (pass-01)
2. Filter by known framework_id → returns only entries for that framework (pass-02)
3. Invalid change_type value → error with controlled vocabulary in message (fail-01)

## Approval-gated changes
- Extending the `change_type` vocabulary — all callers must handle the new value.
- Changing how `since` date filtering works.

## Minority-report policy
When machine-detected version (framework-update-check) conflicts with human-confirmed
changelog entry, surface both as `minority_report.conflicts`.
See `skills/shared/minority-report.md`.

## Update checklist
- [ ] SKILL.md "Do NOT use for…" clause intact
- [ ] `python3 tools/sync_check.py` passes
- [ ] evals/evals.json has ≥3 cases
