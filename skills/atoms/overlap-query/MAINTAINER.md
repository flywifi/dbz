# MAINTAINER — overlap-query

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`overlap-query` so a future maintainer keeps the intended scope. The atom computes
**spine-anchored** overlap (CCI / 800-53 sub-part), not the retired ER-set metric.

## Non-negotiable invariants
- The primary metric is spine-based: shared testable atoms or shared 800-53 sub-parts between the
  two frameworks' `framework_projection` footprints. The finest ("cci") basis is the **union of
  DISA CCIs and 800-53A assessment objectives** (`cci_bridge` ∪ `assessment_objectives` — disjoint
  id spaces, same sub-part anchoring); objectives extend the denominator into PT / SR / PM where
  DISA issued no CCIs. Jaccard + both directional coverages are always reported
  (`a_covers_b_pct` and `b_covers_a_pct` differ and both matter).
- **Never error on a cross-framework comparison.** Degrade through the ladder cci → subpart →
  control → inferred_er → `basis:"none"`. Only an unknown framework *name* returns
  `overlap_pct: null` with `known_frameworks`.
- **No fabrication.** Every contributing edge traces to a real `source_file`+`source_row`. A missing
  bridge is `unknown` / `undetermined`, never a guessed `full`.
- Provenance precedence for the primary figure: `direct_olir / cmmc171 (0.95) > consensus (0.85,
  flag-gated) > hitrust_hub (0.65) > inferred_er > transitive`. Confidence is the WEAKER side's best
  path (min of the two frameworks), mapped to the tier vocabulary (`>=0.9 high · 0.7–0.9 medium ·
  0.5–0.7 low · <0.5 uncertain`).
- Hub-mediated and inferred figures carry `needs_confirmation: true` and a caveat.
- The `consensus` tier (Phase 18) is confidence-only and gated by the `consensus_provenance`
  feature flag: it lifts hub-gated pairs to 0.85 when at least one strong, text-confirmed
  consensus pair with a real shared spine footprint corroborates the framework pair
  (`consensus_support.text_confirmed >= 1`). It NEVER changes a structural metric, never
  downgrades an owner-direct 0.95 pair, never applies to `inferred_er`, and the result keeps
  `needs_confirmation: true`. The flag may be enabled only while the consensus gate in
  `cross-mapping/tests/validate_spine.py` passes.
- `human_review_required: true` in every output path.
- ODP (parameter) divergence downgrades a per-control match to `partial`; where only one baseline
  pins a value the status is `undetermined`, never silently treated as aligned.

## Known failure modes
- **Over-claiming CCI precision** for commercial pairs (SOC 2 / ISO / HIPAA / GDPR): their spine
  path is the HITRUST hub (control-level, confidence 0.65), so CCI-exactness there is transitive —
  surface the caveat, do not present it as authoritative.
- **ER-only frameworks** (e.g. SOC 1, PCI DSS) have no spine path; they fall to `inferred_er`
  (co-occurrence of shared evidence-request ids) — a labeled secondary signal, never the primary.
- **Confidence inflation** if the pair confidence is taken as the best edge anywhere instead of the
  weaker side's best path.

## Fragile fallbacks that must not become defaults
- `inferred_er` is a fallback only — never the primary basis when a spine path exists.
- `basis:"none"` returns `overlap_pct: 0.0` (a real number), never an exception.

## Regression cases to preserve
1. SOC 2 × ISO 27001 returns a spine basis (cci or subpart) with per-control partials that list exact
   met and unmet sub-parts.
2. An unbridged pair returns `basis:"none"`, `overlap_pct:0.0`, exit 0 — never an error.
3. An unknown framework name returns `overlap_pct: null` + `known_frameworks` (input error, exit 1).
4. Both directional coverages are reported and differ.
5. Hub-mediated pairs carry `needs_confirmation: true` and a caveat.

## Approval-gated changes
- Changing the footprint definitions (`footprint_ccis` / `footprint_subparts` / `footprint_controls`)
  or the ladder order in `spine_overlap.py`.
- Changing the provenance→confidence constants or the tier thresholds.
- Adding a new projected framework or bridge source.

## Minority-report policy
When two provenance tiers (direct vs. hub vs. inferred_er) yield materially different overlap for the
same pair, or a hub-mediated figure carries `needs_confirmation`, emit `minority_report.conflicts`
with the competing citations (each side's `source_file`+`row`) and the winning tier before returning
the primary metric. Direct beats hub beats inferred_er. The flag-gated `consensus` tier relabels
confidence on the SAME structural figure as the hub path (identical metrics), so it never creates a
new conflict class for this policy. See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] SKILL.md description still specific + scoped, with the "Do NOT use for…" clause intact.
- [ ] `python3 tools/sync_check.py` passes.
- [ ] `python3 cross-mapping/tests/test_spine.py` passes.
- [ ] evals/evals.json has at least 3 cases; a case was added for any new behavior.
- [ ] Never-error contract intact: unbridged pair returns basis:"none" exit 0.
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
