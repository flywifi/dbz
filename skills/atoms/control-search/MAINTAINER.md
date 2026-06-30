# MAINTAINER — control-search

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`control-search` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Never fabricate control IDs or titles — all results must come from grc.db.
- `max_results` cap must be enforced; never return unbounded results.
- Empty results return `{"controls": [], "count": 0}` — never an error.
- Family filter must validate against the 19 NIST 800-53 family codes; reject unknown families.
- References `skills/shared/minority-report.md` policy.

## Known failure modes
- **Hallucinated controls**: if the DB connection fails, the atom must return an error, not
  fabricated results.
- **Family code confusion**: 'CM' is Configuration Management; 'CP' is Contingency Planning;
  never silently remap to a wrong family.

## Fragile fallbacks that must not become defaults
- Fuzzy matching: if exact match fails, a fuzzy fallback is acceptable but must be labeled
  `"match_type": "fuzzy"` in the result — never present fuzzy results as exact.

## Regression cases to preserve
1. Search "multifactor authentication" → at least IA-2 in results (pass-01)
2. Unknown family code 'ZZ' → error, not empty results (fail-01)
3. query with no matches → `{"controls": [], "count": 0}`, not an error (edge-01)

## Approval-gated changes
- Changing the DB table or column names queried.
- Adding fuzzy matching — requires a labeled `match_type` field in output.
- Changing `max_results` default or cap.

## Minority-report policy
Pure read-only DB operation; minority-report not applicable. Note stale DB in response metadata.
See `skills/shared/minority-report.md`.

## Update checklist
- [ ] SKILL.md "Do NOT use for…" clause intact
- [ ] `python3 tools/sync_check.py` passes
- [ ] evals/evals.json has ≥3 cases
