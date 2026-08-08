# Evidence standards

The authority file for how dbz establishes, labels, and cites evidence. Every rule here
formalizes behavior that already exists elsewhere in the repo; each cites its source. Other docs
should cite this file rather than restate the rules.

Scope note: mapping-data evidence (tiers, precedence, confirmation) lives here. Provenance for
**regulatory events** — rule publications, effective dates, suspensions, agency projections —
lives in `regulatory-provenance.md`; the seven-tier model below is untouched by that file.

## Source precedence (source: `CLAUDE.md` — Non-negotiables)

When sources disagree about a mapping, precedence is:

1. **Explicit report text** (what the audited document actually says)
2. **Source-provided mappings** (the framework owner's own published crosswalk)
3. **Bundled crosswalks** (third-party compilations shipped with tools)
4. **Blank** — when none of the above supports a claim, the field stays empty.
   Never fabricate an ID, citation, date, or crosswalk relationship.

## Provenance tiers (source: `docs/consensus-detection.md`, `docs/cross-mapping-architecture.md`)

Every `master_mappings` edge carries one of seven tiers, ranked:

`owner_direct > nist_stated > owner_stated > hub > bundled > consensus > production_aggregate`

- The tier records **how the edge was established**, not how strongly it is corroborated.
- Consensus across owners is *derived evidence with citations to its voters* — it never
  impersonates an owner statement (acceptance-authority model, `docs/consensus-detection.md`).
- Corroborating non-winning surfaces are preserved on the edge (`corroboration` field), never
  discarded (source: master arbitration, `cross-mapping/engine/master_surface.py`).

## Evidence-state ladder (source: `cross-mapping/engine/master_surface.py`, schema 3.13)

Orthogonal to the tier: the tier says HOW an edge was established, the **evidence_state** says
HOW STRONGLY it is corroborated. Derived deterministically from existing fields only, highest
applicable state wins:

| State | Meaning | Predicate |
|---|---|---|
| `oracle_confirmed` | the production ER oracle co-cites the pair | `production_support ≥ 1` or tier = `production_aggregate` |
| `cross_validated` | independently corroborated | ≥1 corroborating surface, or consensus votes ≥ 2 |
| `columns_aligned` | one directly-stated surface | tier ∈ {owner_direct, nist_stated, owner_stated, hub} |
| `asserted_by_source` | one compiled/bundled surface only | everything else |

Filter with `dbz_query.py master --evidence-state <state>`. Gated by `validate_spine.py`
check 14 (vocabulary exact, no missing states, monotonicity, independent recomputation).

## Citation requirements (source: `tools/output_validate.py`, `docs/BENCHMARK.md`)

- Every control/CCI id cited in an output must exist in the catalog; unknown ids are treated as
  possible fabrication (HIGH severity).
- Percentages and material counts must sit near a citation marker (a tier tag, `per grc.db`, a
  source name) or carry an explicit `[estimated]` / `[unverified]` label.
- High-confidence language (`confirmed`, `established`, `definitive`) requires an authoritative
  tier (`owner_direct` / `nist_stated` / `owner_stated`) behind the claim.
- Published accuracy numbers are measured, then pinned below measurement — never aspirational
  (source: `docs/BENCHMARK.md` regression policy).

## Currency evidence (source: `docs/standards-refresh-runbook.md`)

An archive (Wayback) copy is never live currency: any consumer of a `source="wayback"` fetch
must record that label and must not update a feed's currency fields from it. HEAD-based
currency polls are live-only (`allow_wayback=False`).
