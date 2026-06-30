# MAINTAINER — cfr-lookup

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`cfr-lookup` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- CFR part format must be validated: 'NN-CFR-NNN' pattern (title-CFR-part).
- Never fabricate section text — all text from cfr_requirements table only.
- NIST family codes are keyword-heuristic derivations from eCFR loader; label as such.
- References `skills/shared/minority-report.md` policy.

## Known failure modes
- **Stale CFR text**: eCFR updates daily; DB may be weeks behind. Note `db_built_at` in response.
- **Heuristic family mapping**: NIST families come from keyword matching, not authoritative
  human crosswalk. Callers must not treat them as authoritative — they are starting points.

## Regression cases to preserve
1. 45-CFR-164 section 164.308 → returns Administrative Safeguards text, families include 'IA' and 'AC' (pass-01)
2. Invalid part format → error (fail-01)
3. Valid part not in DB → empty sections list, not error (edge-01)

## Approval-gated changes
- Changing the CFR part format validation.
- Adding NIST family mapping confidence levels (would change output schema).

## Minority-report policy
When keyword-heuristic NIST family differs from a manually coded mapping for the same section,
emit `minority_report.conflicts`. See `skills/shared/minority-report.md`.

## Update checklist
- [ ] SKILL.md "Do NOT use for…" clause intact
- [ ] `python3 tools/sync_check.py` passes
- [ ] evals/evals.json has ≥3 cases
