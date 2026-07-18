# Conflict protocol

What happens when sources disagree. Formalizes existing behavior; each rule cites its source.

## Arbitration (source: `cross-mapping/engine/master_surface.py`, `docs/consensus-detection.md`)

- A disputed pair is won by the highest provenance tier present
  (`owner_direct > nist_stated > owner_stated > hub > bundled > consensus > production_aggregate`).
- The winner does not erase the losers: every non-winning surface is preserved on the edge in
  `corroboration`, so the disagreement remains inspectable.

## Consensus votes (source: `docs/consensus-detection.md`)

- Independent authorities agreeing on a pair form consensus: **strong** = ≥3 distinct voters,
  moderate = 2, single = 1 (stored, never promoted).
- Consensus carries a deterministic `uncertainty_id` and `needs_confirmation=1` — agreement
  raises confidence, it does not create authority (acceptance-authority model).

## Minority reports (source: `skills/shared/minority-report.md`, `skills/shared/consolidation.md`)

- When disagreement changes which mapping is reported, a minority report is **not optional**:
  the losing interpretation lands in `minority_report.conflicts` with the decision log
  explaining why the winner won.
- In multi-agent consolidation, a finding that fails verification leaves the trusted set and is
  recorded in `minority_report.failed_to_merge` — never silently deleted.

## Unresolvable conflicts (source: `CLAUDE.md` non-negotiables)

When precedence cannot decide (equal-tier contradiction, no oracle), the field stays blank or
flagged with its `uncertainty_id` in `canonical-sources/uncertainty_ledger.jsonl`. Guessing is
never a resolution.
