# Overlap spine — CCI / sub-part-anchored cross-framework overlap

## What it does
Given any two compliance frameworks, the engine reports how much audit work they share —
as a percentage, with directional coverage, and with a per-control breakdown that names
exactly which requirements overlap and which do not. It always returns a number and always
shows its work.

## The spine
Every framework's native controls are projected onto a common NIST 800-53 r5 coordinate:

```
r5_control  (AC-2)
  └─ r5_subpart (AC-2 d.1)      statement / assessment-objective granularity  [primary]
       └─ cci        (CCI-000015)     finest testable atom, where DISA issued one
       └─ objective  (ac-2_obj.d.3-1) 800-53A assessment objective — same granularity,
                                      covers the families DISA never did (PT, SR, PM)
            + odp (ac-02_odp.01) organization-defined parameter linked to the exact
                                 sub-part whose statement text references it
```

Overlap is the shared footprint on this spine. Because the pivot is the sub-part (and the CCI
where present), overlap is measured at the level auditors actually work — not "control A vs
control B", but which specific requirement inside a control is shared.

## How each framework reaches the spine
- **NIST 800-53 ↔ ISO 27001:2022** — the official NIST OLIR crosswalk (`direct_olir`). The
  relationship (equal / subset / superset / intersect) is derived from mapping cardinality,
  since this OLIR release leaves the relationship column empty. ISO ids are canonicalized by
  `normalize_iso_id` (Annex A `A.5.1`, ISMS clauses `10.2 a.1`, ambiguous ids kept bare) so
  OLIR / HITRUST-hub / ER citations of the same 2022 control join across sources.
- **CMMC 2.0 ↔ NIST SP 800-171 r2 ↔ 800-53 r5** — the CMMC/800-171A/800-53A crosswalk
  (`cmmc171`). Source-stated STRM relationships (Equal / Subset of / Superset of / Intersects
  with) from the "Mapping -171 to -53" column. Sub-part resolution via the 800-53A assessment-
  objective column (`AC-02d.01` → `AC-2 d.1`). ODP references (`IA-03_ODP[01]`) are linked to
  canonical OSCAL param ids. FedRAMP Moderate pinned values are extracted from the same file
  (partial gap fill). Confidence 0.95, hop 1, needs_confirmation=0.
- **SOC 2, ISO, HIPAA, GDPR, CMMC, FedRAMP, CIS, 800-171** — the HITRUST v11.4 authoritative-
  sources cross-reference (`hitrust_hub`), whose NIST cells resolve to sub-parts. SOC 2 is
  anchored on the AICPA Trust Services Criteria (2017) — the specific testable criteria a SOC 2
  audit evaluates against. For CMMC 2.0 and 800-171, the engine picks the stronger `cmmc171`
  edge (0.95) over the weaker hub edge (0.65) via `_framework_best_conf`.
- **CCIs** — the current DISA CCI List XML (2025-01-23, public download) maps each CCI to a
  NIST 800-53 sub-part using **native Revision 5 references** (3,836 CCIs). CCIs that only
  carry r4 refs are bridged by identity where the id survives into r5, or — for the withdrawn
  Appendix J privacy controls — via the absorption map NIST states in its own r4→r5 comparison
  workbook (`basis` stamped on every bridge row: `r5_native` / `r4_identity` /
  `appj_absorption`). 4,550 CCIs across 1,095 controls; the only controls without CCIs are the
  r5-withdrawn stubs.
- **800-53A assessment objectives** — the raw OSCAL catalog's `assessment-objective` parts
  (3,715 rows) provide sub-part-level testable anchors for every active control, including the
  PT / SR / PM families where DISA issued no CCIs. The finest overlap basis is the union of
  CCIs and objectives (disjoint id spaces).
- **ODPs** — every organization-defined parameter is linked to the statement sub-part whose
  OSCAL prose references it (`{{ insert: param, … }}`), with `link_basis` provenance:
  `oscal_part_insert` (sub-part-precise), `control_scope` (the statement has no lettered
  parts — the honest granularity for most enhancements), never fabricated.
- **ODP values** — the DAAPM (DoD) baseline pins concrete parameter values (e.g. AC-2(2) → 72
  hours) extracted from its control text; FedRAMP Moderate pins 37 values via the CMMC
  crosswalk column.

## Reading a result
- `overlap_pct` — Jaccard over the shared spine footprint (CCI or sub-part basis).
- `a_covers_b_pct` / `b_covers_a_pct` — directional coverage (they differ; both matter).
- `per_control` — each of A's controls classified `full` / `partial` / `none`, with the exact
  `shared_subparts`, `a_unmet_subparts`, the corresponding controls on B's side, and the ODP
  alignment status. A sub-part match with divergent parameter values is `partial`, not `full`.
- `basis` — `cci` (finest) down through `subpart`, `control`, `inferred_er`, to `none`. The
  engine degrades gracefully instead of erroring: an unbridged pair returns `0.0` with a
  `data_gap`, and only an unknown framework *name* is an input error.
- `confidence` — gated by the weaker side's strongest path (`high` / `medium` / `low` /
  `uncertain`); hub-mediated and inferred results carry `needs_confirmation`.

Every figure traces to a real source row. Nothing is fabricated; a missing bridge is reported
as unknown, never guessed.

## Honest limits
- The finest basis (CCI ∪ 800-53A objective) now covers every active control; the only
  controls with no atoms are r5-withdrawn stubs. Commercial pairs still reach the spine
  through the HITRUST hub, so their confidence stays gated by the hub's 0.65 edge even when
  the atom denominator is complete.
- App J–recovered CCI rows (`basis=appj_absorption`) are control-level only — NIST's
  absorption statements name the receiving control, not a sub-part, and we never guess.
- Parameter (ODP) comparison is only decidable where two frameworks both pin a value; FedRAMP
  parameter values are partially loaded (37 values from the CMMC crosswalk's FedRAMP column),
  and commercial frameworks do not pin NIST ODPs, so many comparisons are still reported as
  undetermined. The *linkage* side is closed: every ODP that the OSCAL statement text
  references is tied to its sub-part (or honestly control-scoped).

## Uncertainty ledger + confirmation cascade
Every review-worthy uncertainty (overlap pair, ODP value, conflict, agent dissent) is recorded
in `canonical-sources/uncertainty_ledger.jsonl` with a deterministic `uncertainty_id` and a
resolvable source citation. A human confirmation in `canonical-sources/confirmations.jsonl`
re-derives the dependent fields at the next build — confirm once and `status`,
`needs_confirmation`, `confidence`, and any partial→full reclassification update everywhere. The
health auditor checks the ledger for referential integrity and citation resolvability on every
scan.

## Where it lives
- `cross-mapping/engine/spine_normalize.py` — canonical id / sub-part parsers.
- `cross-mapping/engine/spine_loader.py` — CCI bridge, sub-part inventory, ODP rekey, OLIR +
  HITRUST projections, ODP-value extraction.
- `cross-mapping/engine/spine_overlap.py` — footprints, per-control classification, the
  never-error ladder.
- `cross-mapping/engine/uncertainty.py` — uncertainty ids, the confirmation cascade, the ledger.
- `skills/atoms/overlap-query/` — the runtime atom.
- `cross-mapping/tests/test_spine.py`, `cross-mapping/tests/validate_spine.py` — self-test and
  oracle reconciliation.

## Proposed (not yet added): a `mapping_edges` catalog field
The projection edges live in `grc.db` today. If the projection is later exported into the
generated catalog JSON, `cross-mapping/schema/enhanced_framework_schema.json` would need a new
`mapping_edges` array on a control:

```
"mapping_edges": [
  { "framework": "ISO 27001/2 (2022)", "native_id": "A.5.15",
    "r5_subpart": "AC-2 d.1", "cci_id": "CCI-000015",
    "relationship": "intersect", "relationship_basis": "derived_cardinality",
    "provenance": "direct_olir", "confidence": 0.85, "needs_confirmation": false,
    "source": { "file": "…", "row": 42 } }
]
```

This is a deliberate schema-evolution decision and is **not** silently added — the catalog
schema is unchanged until the export is built.
