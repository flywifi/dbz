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
- **HIPAA Security ↔ 800-53 (direct, Phase 19)** — the NIST SP 800-66r2 OLIR informative
  reference (CPRT element graphs, 279 citation→control pairs): `direct_800_66`, confidence
  0.85, NIST-stated. The hub path is kept beneath it; both use one canonical bare-citation
  namespace (`normalize_hipaa_citation`). Three real citation granularities coexist and are
  never rewritten: section (`164.308`, consensus keys), CPRT standard (`164.312(a)`, the
  800-66 set), full citation (`164.312(a)(1)`, the hub set).
- **NIST CSF 2.0 ↔ 800-53 r5.2.0 (direct, Phase 19)** — the official OLIR crosswalk from the
  CSF 2.0 CPRT graphs (746 subcategory→control pairs, pinned to the exact catalog release on
  disk): `direct_csf2`, 0.85. The concept-crosswalk xlsx remains in `unified_mappings` as
  corroboration (the projection covers 100% of its pairs).
- **NIST SP 800-171 r3 / 800-172 r3 ↔ 800-53 (direct, Phase 19)** — NIST's own mappings from
  the official CPRT datasets (157 + 107 external references): `direct_cprt_171r3` /
  `direct_cprt_172r3`, 0.85. 171 r2 stays pinned for CMMC — both revisions coexist as
  separate frameworks.
- **PCI DSS v4.0 ↔ 800-53 (bundled, Phase 19)** — the user-provided master crosswalk's PCI
  column (1,348 requirement→control co-citations incl. Appendix A1/A2/A3 ids):
  `master_crosswalk`, confidence 0.60, needs_confirmation=1 — honest bundled tier; the
  Phase 18 consensus tier lifts eligible pairs to 0.85 at query time.
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
- `consensus_support` — how many strong cross-source consensus pairs corroborate the framework
  pair (`strong_edges`), and how many of those are eligible corroboration (`text_confirmed`:
  both requirement texts on file and a real shared spine footprint). Always reported.
- `relationship_basis: multi_source_consensus` — present only when the flag-gated consensus
  tier applied (below).

### The consensus confidence tier (flag: `consensus_provenance`)
When at least one eligible strong consensus pair corroborates a framework pair, the pair's
confidence reports **0.85** with `provenance: consensus` — above the hub's 0.65 (several
independent authorities agreeing beats one hub pivot) and below owner-direct 0.95 (consensus
is derived evidence, never an owner's own statement). Precedence and safety rules:
- **0.95 owner-direct > 0.85 consensus > 0.65 hub** — the tier only ever lifts a weaker claim
  (applies when the pair's confidence is below 0.85); an owner-direct pair is never touched.
- **Confidence-only**: structural metrics (`overlap_pct`, coverage, shared atoms, per-control
  rows) are byte-identical with the tier on or off; the tier changes labeling, not data.
- **Never applied** to the `inferred_er` fallback, to pairs whose consensus texts are still
  `pending_licensed_artifact`, or to pairs with no shared spine footprint.
- Results keep `needs_confirmation: true` — corroborated, not confirmed; the confirmation
  cascade still governs.
The flag lives in `canonical-sources/feature_flags.json` and may be enabled only while the
consensus oracle-validation checks in `cross-mapping/tests/validate_spine.py` pass (band
preservation, production-evidence enrichment, ISO-side oracle coverage). The precomputed
`overlap_matrix` is always built with the tier off (plus persisted corroboration counts), so
build digests never depend on flag state.

Every figure traces to a real source row. Nothing is fabricated; a missing bridge is reported
as unknown, never guessed.

## Honest limits
- The finest basis (CCI ∪ 800-53A objective) now covers every active control; the only
  controls with no atoms are r5-withdrawn stubs. SOC 2 / GDPR / CIS pairs still reach the
  spine through the HITRUST hub (0.65); HIPAA and CSF 2.0 now carry NIST-stated 0.85 paths,
  and PCI carries a bundled 0.60 path — the tier on each result says which.
- **SOC 1** has no public control layer (SSAE 22 / AT-C 320 define report standards) — it can
  never be projected without fabrication; only aggregate `inferred_er` overlap exists.
- **CMMC L1/L2/L3 level tiering** is still unmodeled — CMMC is practice→control edges only.
- **PCI's bundled tier** is a single compiler's co-citation: treat 0.60-confidence PCI rows
  as leads, not statements; consensus corroboration (votes) is the strengthening signal.
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

## The master mapping surface (`master_mappings`, Phase 19)
What the old "proposed `mapping_edges`" section sketched now exists as a build artifact:
one row per unordered canonical framework pair, unioned from every mapping surface
(`framework_projection`, `unified_mappings`, `consensus_edges` strong+moderate, the OLIR
CSF-2.0 pair sets, the AICPA-TSP↔HITRUST matrix, and aggregate ER production evidence),
assembled deterministically by `cross-mapping/engine/master_surface.py`.

Tier arbitration (strongest wins the primary row; every losing surface's claim is preserved
verbatim in the `corroboration` JSON column — minority report, dissent never dropped):

| tier | provenance | confidence |
|---|---|---|
| `owner_direct` | cmmc171 | 0.95 |
| `nist_stated` | direct_olir · direct_800_66 · direct_csf2 · direct_cprt_171r3 · direct_cprt_172r3 · olir_csf2_pair | 0.85 |
| `hub` | hitrust_hub · transitive_unified · aicpa_tsp_hub | 0.65 |
| `bundled` | master_crosswalk | 0.60 |
| `consensus` | multi-voter derived (votes reported) | — |
| `production_aggregate` | co-occurrence counts, public ids only | — |

Rules: one canonical label per framework (`framework_labels` registry — explicit aliases from
`framework_vocab.json`, identity self-registration for the long tail); provider-proprietary
ids are refused at assembly and triple-scanned (tests + validate_spine check 8 + health
audit); SOC 1 has no id-level rows (no public control layer — structured data gap); FedRAMP
appears as baseline *scope*, not pair rows; single-voter consensus pairs are excluded.
Query: `dbz_query.py master` (pair / control / audit-scope modes) and the `master-crosswalk`
atom. Gates: validate_spine check 8 (integrity, leak, label round-trip, HIPAA direct↔hub
reconciliation ≥50% [observed 73.2%], CSF2 parity ≥95% [observed 100%], PCI on-spine,
matrix completeness C(14,2)=91).

The catalog-JSON export (`mapping_edges` on a control in
`cross-mapping/schema/enhanced_framework_schema.json`) remains a deliberate schema-evolution
decision that is **not** silently added — the catalog schema is unchanged until that export
is built.
