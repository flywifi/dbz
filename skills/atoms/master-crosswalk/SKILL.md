---
name: master-crosswalk
description: >
  Query the master mapping surface: any compliance framework <-> any other, in one
  tier-arbitrated table (master_mappings in grc.db) that unions every mapping source —
  owner-stated crosswalks, NIST-published mappings (OLIR/CPRT incl. SP 800-66r2 HIPAA and
  CSF 2.0), the HITRUST hub, the bundled master crosswalk, multi-source consensus, and
  aggregate production evidence. Three modes: pair enumeration (every mapping between
  frameworks A and B), control fan-out (everything one native id maps to, any framework), and
  audit-scope filtering ("which SOC 2 work counts toward FedRAMP Moderate / CUI / a NIST
  family"). Every row carries its tier, provenance, confidence, and a
  minority-report `corroboration` column preserving every non-winning surface. Use this atom
  when the question spans mapping sources or needs the strongest-available claim per pair.
  Do NOT use for single-NIST-control fan-out (use compliance-crosswalk), overlap percentages
  (use overlap-query), gap lists (use gap-analysis), or consensus-evidence inspection
  (use dbz_query consensus). Do NOT fabricate mappings — every row traces to a committed
  source, and absent pairs are absent, never guessed.
---

# master-crosswalk

The all-in-one master mapping database (Phase 19): private-sector audit frameworks
(SOC 2/TSC, ISO 27001/2:2022, HIPAA Security, HITRUST CSF, GDPR, PCI DSS v4.0) merged with
the NIST-based audit universe (800-53 r5 + FedRAMP baselines, 800-171 r2/r3, 800-172 r3,
CMMC 2.0, CSF 2.0) in one table with one canonical label per framework
(`framework_labels` registry).

## Tier model (strongest wins the row; dissent never dropped)

| tier | provenance | confidence |
|---|---|---|
| `owner_direct` | cmmc171 | 0.95 |
| `nist_stated` | direct_olir, direct_800_66, direct_csf2, direct_cprt_171r3, direct_cprt_172r3, olir_csf2_pair | 0.85 |
| `hub` | hitrust_hub, transitive_unified, aicpa_tsp_hub | 0.65 |
| `bundled` | master_crosswalk | 0.60 |
| `consensus` | consensus (strong/moderate; votes reported) | — |
| `production_aggregate` | production co-occurrence counts (public ids only) | — |

The non-winning surfaces for a pair are preserved verbatim in `corroboration` (JSON) —
the minority-report policy. `needs_confirmation` stays 1 below `nist_stated`.

## Modes

```bash
# pair: every mapping between two frameworks, strongest tier first
python3 cross-mapping/engine/dbz_query.py master \
    --framework-a "SOC 2" --framework-b "PCI DSS v4.0" [--min-tier hub]

# control: everything one requirement maps to, across all frameworks
python3 cross-mapping/engine/dbz_query.py master \
    --framework "HIPAA Security" --control "164.312(a)(1)"

# audit scope: which of A's requirements touch an in-scope NIST control set
python3 cross-mapping/engine/dbz_query.py master \
    --framework-a "SOC 2" --scope-fedramp moderate [--cui] [--family IA]
```

Wrapper script: `skills/atoms/master-crosswalk/scripts/master_crosswalk.py` (same flags,
`--format json|table`). All modes emit `human_review_required: true` — the master surface
is advisory evidence with citations; actual audit scope depends on organization context.

## Honest limits

- **SOC 1** has no public control layer (SSAE 22 / AT-C 320) — queries return a structured
  `data_gap: no_public_control_layer`; only aggregate `inferred_er` overlap exists.
- **HIPAA citations come in three real granularities** that are never rewritten: section
  (`164.308`, consensus keys), CPRT standard (`164.312(a)`, the 800-66 direct set), and full
  citation (`164.312(a)(1)`, the hub set). The validate_spine reconciliation check quantifies
  their agreement.
- **FedRAMP** appears as baseline scope (audit-scope mode), not as id-level pair rows — its
  "native ids" are baseline-annotated 800-53 ids.
- Firm-local/provider ids never appear anywhere (enforced at assembly, in tests, and by the
  health audit); production evidence contributes counts only.
- Single-voter consensus pairs are excluded (inspect them via `dbz_query.py consensus --tier all`).

## Do NOT use this atom for
- Single-NIST-control fan-out with STRM detail (use compliance-crosswalk)
- Overlap percentages / shared-audit-work figures (use overlap-query)
- Gap lists / which controls are missing (use gap-analysis)
- Inspecting consensus voter evidence or single-voter pairs (use `dbz_query.py consensus`)
- Fabricating mappings — absent pairs are absent; every row traces to a committed source

## Conflicting sources — minority-report policy

When surfaces disagree on a pair's relationship, the strongest tier wins the primary row and
every dissenting claim stays in `corroboration` with its provenance and source. See canonical
policy: `skills/shared/minority-report.md`.

## Pipeline note

Reads `master_mappings`, `framework_labels`, `controls`/`enhancements` (baseline flags) in
`grc.db`. Assembly: `cross-mapping/engine/master_surface.py` (build-time, deterministic).
Prerequisite: `python3 cross-mapping/engine/build_db.py`.
