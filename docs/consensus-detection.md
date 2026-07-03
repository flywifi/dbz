# Cross-source consensus detection

When several independent mapping authorities each imply the SAME third-party framework pair —
a TSC criterion and an ISO control routed through one SCF control, through one CCM control, and
through shared 800-53 sub-parts — that agreement is strong derived evidence the two requirements
genuinely overlap. `cross-mapping/engine/consensus_detector.py` finds those agreements, scores
them, and characterizes how/why/to-what-extent each pair overlaps. Results live in the
`consensus_edges` table; query with `dbz_query.py consensus`.

## The voters

| Voter | Owner | Path | Semantics carried |
|---|---|---|---|
| `scf` | Secure Controls Framework | pivot: SCF control co-cites TSC / ISO / PCI / CIS / CSF / 800-53 / 171 / HIPAA / GDPR ids | co-citation (STRM published separately) |
| `csa` | Cloud Security Alliance | pivot: CCM v4.0.13 Scope Applicability sheet (TSC, ISO 2022, 800-53 r5, CSF 2.0, PCI 4.0, CIS 8.0) | CSA's own Gap Level per mapping |
| `hitrust` | HITRUST | pivot: v11.4 cross-reference | co-membership |
| `olir` | NIST | direct: 800-53 ↔ ISO 27001:2022 | derived cardinality |
| `cmmc171` | DoD/NIST | direct: CMMC + 171 ↔ 800-53 objectives | source-stated STRM |
| `master` | user-provided master crosswalk | pivot: 800-53 co-cites TSC / ISO / CSF / PCI / HIPAA / 171r3 | co-citation |
| `pci_iso` | pair-direct file | direct: PCI 4.0 ↔ ISO 27001:2022 | co-citation |

**Independence rules:** CSA's two artifacts (mapping sheet + OSCAL) count as one voter. `olir` and
`cmmc171` are separate instruments but share NIST ancestry — pairs where both vote carry
`nist_ancestry_overlap=1` so shared lineage can't masquerade as extra independence. Production
audit evidence is not a voter: it contributes `production_support` (aggregate co-occurrence
counts from real audits) with **no provider-proprietary identifiers ever read into results**
(CLAUDE.md publication hygiene; enforced by a leak test in `test_spine.py`).

## Scoring and characterization

Pairs are keyed on canonical ids (`spine_normalize`: `normalize_tsc_id`, `normalize_iso_id`,
`normalize_pci_id`, `normalize_control_id`, plus HIPAA §-section / CIS / CSF 2.0 / 171 / GDPR
article forms). Tiers: **strong** = ≥3 distinct voters, moderate = 2, single = 1 (stored, not
surfaced by default).

Every strong pair gets:
- **extent** — spine-footprint containment (`equal / a_subset_b / b_subset_a / intersect /
  atoms_disjoint / no_spine_footprint`) computed from each side's 800-53 sub-part footprint;
- **shared_atoms** — the specific sub-parts both requirements reach (the "how they overlap");
- **text_confirmation** — `texts_on_file` where we hold both requirement texts;
  `texts_on_file_licensed` where the ISO side is an Annex A control covered by the licensed
  ISO/IEC 27001:2022 verification copy on disk (manifest id `iso-27001-2022-annex-a-text` —
  the text is used for confirmation only and never reproduced in outputs);
  `pending_licensed_artifact` where the ISO side is an ISMS clause id (only selected clause
  excerpts are on file — coverage is never overstated);
- a deterministic `uncertainty_id` and `needs_confirmation=1` — strong consensus makes a pair
  worth confirming, it does not make it confirmed.

## What consensus is — and is not (acceptance-authority model)

Each owner's crosswalk is the acceptance rule for THEIR OWN framework (see the runbook's
authority-model section). Consensus across owners is **our derived evidence with citations to
every voter** — a prioritized confirmation queue, not a new authority. It never overrides any
owner's mapping and never modifies any standard's data. Voters disagreeing on *extent* while
agreeing on *existence* is normal and preserved verbatim in the `evidence` column; material
extent disagreement on a single framework's acceptance question follows the minority-report
policy (owner mapping wins as primary, dissent recorded).

Since Phase 18 that derived evidence also feeds a **flag-gated overlap-confidence tier**
(`consensus_provenance` in `feature_flags.json`): framework pairs corroborated by at least one
strong, text-confirmed consensus pair with a real shared spine footprint report overlap
confidence 0.85 (`provenance: consensus`, `relationship_basis: multi_source_consensus`) instead
of the hub-gated 0.65. This is still not an authority: the tier is confidence-only (structural
metrics are byte-identical either way), never touches owner-direct 0.95 pairs, and results stay
`needs_confirmation` until individually confirmed. The flag may be enabled only while the
oracle-validation gate in `validate_spine.py` passes — see `docs/overlap-spine.md` for the
tier's precedence rules and `docs/standards-refresh-runbook.md` for the gate.

Phase 19 notes: strong + moderate consensus pairs also feed the master mapping surface
(`master_mappings`) as the `consensus` tier — arbitrated below every stated surface, with
votes reported instead of a confidence number; single-voter pairs stay out of the master
surface (inspect via `dbz_query.py consensus --tier all`). The PCI appendix-id normalizer
extension (A1/A2/A3.x) and the PCI/CSF entries added to the label maps expanded the
consensus key space (41,427 → 42,146 pairs; 834 → 845 strong) and gave existing PCI/CSF
pairs real spine footprints where they previously characterized `no_spine_footprint`;
the Phase 18 pinned gates re-measured green without re-pinning (enrichment lift 2.37×,
ISO coverage 55.9%).

## SOC 2 comparability — controls vary by audit firm

SOC 2 has **no standardized control list**. Per the AICPA, the [2017 Trust Services Criteria
(with 2022 revised points of focus)](https://www.aicpa-cima.com/resources/download/get-description-criteria-for-your-organizations-soc-2-r-report)
do not define the controls a service organization must implement — each organization identifies
its own controls that meet the criteria, and the [points of focus are considerations, not
requirements](https://linfordco.com/blog/trust-services-critieria-principles-soc-2/), which
[may not all be applicable to every organization](https://www.ey.com/en_us/technical/accountinglink/to-the-point-aicpa-revises-guidance-on-applying-its-trust-services-criteria-and-soc-2-description-criteria).
In practice every audit firm and compliance platform brings its own SOC 2 control template.

Consequences here:
1. Consensus edges key on **TSC criteria only** (CC/A/C/PI/P series — the one stable public
   layer). `normalize_tsc_id` rejects anything else by design.
2. Firm-local control ids (any platform's internal SOC 2 requirement set) never key a consensus
   edge; production evidence flows in as aggregate corroboration only.
3. Downstream users must not assume a universal SOC 2 control list exists — two firms' SOC 2
   reports can test different controls against the same criteria.

## Reading the output

```
python3 cross-mapping/engine/dbz_query.py consensus \
    --framework-a "SOC 2 (TSC)" --framework-b "ISO 27001/2 (2022)"
```

Example (real result): `TSC CC5.3 ↔ ISO 5.1` — voters `csa + master + scf`, extent `intersect`,
2 shared spine atoms, `texts_on_file_licensed` (the Annex A 5.1 wording is on disk in the
licensed verification copy). Three authorities that never coordinated all connect "COSO
Principle 12 / control deployment" territory to ISO's policy control — go confirm against the
authoritative texts, starting from the shared atoms.

## Current results (build of 2026-07-03)

41,427 scored pairs → **834 strong**, 5,775 moderate; 282 pairs carry production corroboration;
21 strong SOC2(TSC)↔ISO pairs (the canonical example class). Of the 226 ISO-side strong pairs,
200 are `texts_on_file_licensed` (Annex A controls covered by the licensed verification copy);
the 26 still `pending_licensed_artifact` are ISMS clause ids (4.x, 6.1.x, 7.5.x, 9.1, 10.1).
Deterministic across rebuilds.

Oracle-validation gate results (Phase 18, measured on this build): strong pairs are
production-corroborated at 3.8% vs 1.6% for moderate pairs — a **2.3× enrichment lift**
(32 corroborated strong pairs), and the ISO ids on eligible strong consensus pairs cover
**55.9%** of the 93 ISO ids the ER production oracle co-cites with SOC 2. Both clear the
pinned gate thresholds (lift ≥ 1.2×, coverage ≥ 50%), the SOC2×ISO overlap band (40–70%) is
unchanged with the tier on, and 8 eligible TSC↔ISO pairs corroborate the canonical example
class — so the `consensus_provenance` flag is enabled.
