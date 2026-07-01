# MAINTAINER — overlap-query

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`overlap-query` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Overlap percentages are computed exclusively from ER crosswalk data in `grc.db` — never estimated or fabricated.
- `human_review_required: true` in every output.
- Jaccard index formula: `|A ∩ B| / |A ∪ B|`. Never use a weighted or directional substitute as the primary metric.
- `a_covers_b_pct` and `b_covers_a_pct` must both be reported — they differ and both matter to compliance teams.
- ERs across different CSV source files are NOT comparable — must reject cross-file comparisons with an explicit error.
- Never merges two frameworks into one ER namespace; always keeps source CSV provenance.

## Known failure modes
- **Cross-file ER comparison**: ER-101 from `SOC 2 T1.csv` is not the same as ER-101 from `ISO 27001.csv` — IDs only have meaning within their source file. Return an error, never a number.
- **Scope creep**: being asked to list specific gap controls (use `gap-analysis`) or map individual controls (use `compliance-crosswalk`).
- **Fabricating an overlap number** when frameworks are both in `grc.db` but the `er_overlap_pairs` view returns zero — the zero is correct. Never override with a heuristic estimate.
- **Stale oracle discrepancy**: if `shared_er_count` diverges by >2 from the oracle CSV row count, surface as a regression alert in `minority_report`.

## Fragile fallbacks that must not become defaults
- `include_er_lists: false` is the default — never include ER ID lists unless explicitly requested.
- "interpretation" string is advisory only — never present it as a compliance opinion or audit conclusion.

## Regression cases to preserve
1. Returns `human_review_required: true` in every response.
2. SOC 2 vs ISO 27001/2 (2022) Jaccard ≈ 78–82% (validate against oracle CSV; alert if outside this band).
3. Returns three metrics: `jaccard_overlap_pct`, `a_covers_b_pct`, `b_covers_a_pct` — never collapses to one.
4. Returns `framework_a_er_count` and `framework_b_er_count` (not zero) even when `include_er_lists: false`.
5. Rejects cross-CSV comparisons with a structured error rather than returning a number.

## Approval-gated changes
- Changing the Jaccard computation (currently: `|intersection| / |union|`).
- Adding a new framework that requires a new ER CSV source.
- Modifying the `er_overlap_pairs` view in `build_db.py`.
- Changing the oracle CSV validation thresholds.

## Minority-report policy
When overlap percentage changes materially (>5 pp) depending on which ER relationship edges
are included, emit `minority_report.conflicts` before returning the primary metric.
See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Re-run oracle check: SOC 2 × ISO 27001/2 shared_er_count against `SOC 2 T2 & ISO 27001.csv`.
- [ ] Confirm `er_overlap_pairs` view reflects current `er_mappings` table schema.
- [ ] Smoke test: `python3 skills/atoms/overlap-query/scripts/overlap_query.py --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)" --format summary`
- [ ] Confirm `human_review_required: true` still present in all output paths.
