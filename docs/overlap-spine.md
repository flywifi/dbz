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
       └─ cci    (CCI-000015)   finest, where it exists
            + odp (ac-02_odp.01) organization-defined parameter attached to the sub-part
```

Overlap is the shared footprint on this spine. Because the pivot is the sub-part (and the CCI
where present), overlap is measured at the level auditors actually work — not "control A vs
control B", but which specific requirement inside a control is shared.

## How each framework reaches the spine
- **NIST 800-53 ↔ ISO 27001:2022** — the official NIST OLIR crosswalk (`direct_olir`). The
  relationship (equal / subset / superset / intersect) is derived from mapping cardinality,
  since this OLIR release leaves the relationship column empty.
- **SOC 2, ISO, HIPAA, GDPR, CMMC, FedRAMP, CIS, 800-171** — the HITRUST v11.4 authoritative-
  sources cross-reference (`hitrust_hub`), whose NIST cells resolve to sub-parts. SOC 2 is
  anchored on the AICPA Trust Services Criteria (2017) — the specific testable criteria a SOC 2
  audit evaluates against.
- **CCIs** — the DISA CCI list maps each CCI to a NIST 800-53 sub-part, so any framework that
  reaches a sub-part inherits its CCIs.
- **ODP values** — the DAAPM (DoD) baseline pins concrete parameter values (e.g. AC-2(2) → 72
  hours) extracted from its control text.

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
- CCIs cover a subset of controls, so CCI-exact overlap is strongest on the NIST-native / CMMC /
  FedRAMP axes; for commercial pairs the honest denominator is the 800-53 sub-part via the
  HITRUST hub (lower confidence).
- Parameter (ODP) comparison is only decidable where two frameworks both pin a value; FedRAMP
  parameter values are not yet loaded, and commercial frameworks do not pin NIST ODPs, so those
  comparisons are reported as undetermined.

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
