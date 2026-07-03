---
name: overlap-query
description: >
  Compute the percentage of shared audit work between two compliance frameworks, anchored on the
  NIST 800-53 sub-part + CCI spine. Returns Jaccard overlap, directional coverage, and a per-control
  full/partial/none breakdown with the exact met vs. unmet sub-parts and parameter (ODP) status.
  Never errors on a cross-framework comparison — it degrades gracefully and always returns a number.
  Use this atom for the sales/CS "shared audit work %" deliverable and for "exactly where do A and B
  overlap" questions. Do NOT use for single-control mapping (use compliance-crosswalk). Do NOT use for
  gap lists (use gap-analysis). Do NOT fabricate overlap numbers — every figure traces to a real
  source row in grc.db.
---

# overlap-query

Computes framework overlap on the **spine**: every framework's native controls are projected onto
NIST 800-53 sub-parts (and CCIs where they exist), and overlap is the shared spine footprint. This
replaces the old ER-set metric, which is retained only as a labeled `inferred_er` fallback for
frameworks that have no spine path.

## Input

```json
{
  "framework_a": "SOC 2",
  "framework_b": "ISO 27001/2 (2022)",
  "db_path": "cross-mapping/output/grc.db",
  "per_control": false,
  "basis": "auto"
}
```

`basis` is one of `auto | cci | subpart | control` (default `auto` = finest available). The `cci`
basis counts the finest **testable atoms**: DISA CCIs plus 800-53A assessment objectives (disjoint
id spaces, both anchored at the sub-part level — objectives cover the PT / SR / PM families where
DISA issued no CCIs).

## Output

(example shows the un-lifted shape, i.e. with the `consensus_provenance` flag off — see below)

```json
{
  "tool": "overlap-query",
  "framework_a": "SOC 2",
  "framework_b": "ISO 27001/2 (2022)",
  "basis": "cci",
  "provenance": "spine",
  "overlap_pct": 53.0,
  "a_covers_b_pct": 81.8,
  "b_covers_a_pct": 60.2,
  "shared_count": 1351,
  "framework_a_count": 2246,
  "framework_b_count": 1652,
  "confidence": "low",
  "confidence_score": 0.65,
  "needs_confirmation": true,
  "consensus_support": {"strong_edges": 21, "text_confirmed": 8},
  "caveats": ["hub-mediated mapping (confidence 0.65); parameter and sub-part precision are approximate"],
  "human_review_required": true
}
```

`consensus_support` reports how many strong cross-source consensus pairs corroborate the
framework pair (and the text-confirmed subset). When the `consensus_provenance` feature flag is
effective and `text_confirmed >= 1`, hub-gated pairs instead report `confidence_score: 0.85`
with `provenance: "consensus"` and `relationship_basis: "multi_source_consensus"` — a
confidence-only lift (structural metrics are identical, owner-direct 0.95 pairs are never
touched, `needs_confirmation` stays true). See `docs/overlap-spine.md` for the tier's rules.

With `per_control: true`, also returns a `per_control` array; each entry classifies one of A's native
controls as `full | partial | none`, with `corresponds_to` (B's matching controls), `shared_subparts`,
`a_unmet_subparts`, and `odp` (parameter alignment status).

## The never-error ladder
The atom always returns a number (exit 0), degrading through: CCI basis → sub-part basis → control
basis → `inferred_er` co-occurrence (labeled) → `basis: "none"` with a `data_gap`. Only an unknown
framework **name** returns `overlap_pct: null` with an `error` and `known_frameworks`.

## Do NOT use this atom for
- Single-control lookups (use compliance-crosswalk)
- Gap lists / which controls are missing (use gap-analysis)
- Pair-by-pair mapping enumeration or audit-scope filtering (use master-crosswalk)
- Fabricating overlap numbers not computed from the spine or ER data in grc.db

## Framework coverage note (Phase 19)
PCI DSS v4.0, NIST CSF 2.0, NIST SP 800-171 r3, and NIST SP 800-172 r3 are spine
frameworks (PCI at the bundled 0.60 tier from the master crosswalk; the others
NIST-stated at 0.85), and HIPAA Security's best path is now the NIST SP 800-66r2
direct projection (0.85). SOC 1 remains `inferred_er`-only — it has no public
control layer, so no spine path can exist without fabrication.

## Pipeline note
Delegates to `cross-mapping/engine/spine_overlap.py`, reading `framework_projection`, `cci_bridge`,
`assessment_objectives`, `nist_subparts`, `odp_values`, and (for the fallback) `er_mappings` in
`grc.db`.

Script: `skills/atoms/overlap-query/scripts/overlap_query.py`

```bash
python3 skills/atoms/overlap-query/scripts/overlap_query.py \
    --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)" --per-control --format summary

python3 cross-mapping/engine/dbz_query.py overlap \
    --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)" --per-control
```

Prerequisite: `grc.db` must exist. Build it with:
```bash
python3 cross-mapping/engine/build_db.py
```

Oracle CSVs (`SOC 2 T2 & ISO 27001.csv` etc.) remain validation oracles for the `inferred_er` path.

`human_review_required: true` — overlap is advisory; actual audit scope depends on organization
context, and hub-mediated / inferred figures carry `needs_confirmation`.

## Conflicting sources — minority-report policy
When two provenance tiers (direct vs. hub vs. inferred_er) yield materially different overlap for the
same pair, or a hub-mediated figure carries `needs_confirmation`, emit `minority_report.conflicts`
with the competing citations before returning the primary metric. Direct beats hub beats inferred_er.
(The flag-gated `consensus` tier relabels confidence on the same structural figure as the hub path,
so it creates no new conflict class.) See canonical policy: `skills/shared/minority-report.md`.
