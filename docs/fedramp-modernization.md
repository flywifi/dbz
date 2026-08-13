# FedRAMP modernization — Consolidated Rules 2026, KSIs, and the confirmation-layer transition

## The framing: an audit-framework revision, not a spine change

**NIST 800-53 r5 remains the master mapping spine — unchanged.** FedRAMP was derived from 800-53,
and what changed in 2026 is the *assessment/confirmation methodology built on top of it* — the same
shape as ISO/IEC 27001's 2013→2022 revision (handled by this repo's version-transition pattern):

| Axis | Rev5 program (old) | Consolidated Rules 2026 (new) |
|---|---|---|
| Confirmation | authorizations (agency/JAB) | **certifications, Classes A–D** |
| Monitoring | legacy ConMon deliverables | **Collaborative Continuous Monitoring (CCM)** + KSI validations |
| Reporting | document packages | **11 machine-readable schemas** (OCR, SCN, incident, VDR…) |
| Control substance | 800-53 r5 baselines | **the same 800-53 r5 controls** (KSIs cite them directly) |

FedRAMP r5 keeps its first-class seat among the 16 matrix frameworks. The new layer is contained
(query-surface tier) and recorded as a **version transition** in `framework_changelog`
(`chg-fedramp-cr26-transition`). Carry-over is measured, not assumed: **95.2%** of the distinct
KSI-cited controls sit inside the FedRAMP r5 Moderate baseline (the 10 outliers are enumerated by
the gate — largely PM/organizational controls).

## The canonical source (FedRAMP's own directive)

FedRAMP's sources page: *"All FedRAMP rules are machine-generated from structured JSON. Do not
attempt to parse the HTML… process the source data directly."*

- **Dataset:** `github.com/FedRAMP/rules` → `fedramp-consolidated-rules.json`
  (v2026.07.06.01; committed complete + verbatim at
  `canonical-sources/source_data/fedramp/fedramp-consolidated-rules.json`, sha-pinned).
  Contents: **FRD** 75 definitions; **FRR** 17 rule families / 246 leaf rules with a
  `pipeline` dimension (`all` 225 / `rev5` 12 / `20x` 9 — the transition encoded in the data);
  **KSI** 10 families / 46 indicators, each carrying FedRAMP's own 800-53 control array;
  **CTL** 79 control entries (16 ODP parameter pins + 65 guidance entries, all captured).
- **Reporting schemas:** `fedramp.gov/schemas/` — 11 date-versioned JSON schemas (2026-06-24 set),
  all committed complete under `source_data/fedramp/schemas/`. A filename dated after 2026-06-24
  is the new-version signal.
- **Narrative corpus:** `FedRAMP/2026-markdown` (291 files, published for machine consumption),
  mirrored whole under `source_data/fedramp/2026-markdown/`; `_sources.json` is the drift signal.
- **Legacy:** `FedRAMP/docs` carries an explicit "not a source of truth" warning;
  **GSA/fedramp-automation was archived 2025-07-01** (Rev5 OSCAL baselines/templates frozen there;
  automate.fedramp.gov is the docs site — proxy-blocked in this environment).

## The DB model (schema 3.12 at introduction; current schema 3.15, contained)

`spine_loader.load_fedramp_rules()` →
`fedramp_ksi` (46) · `fedramp_ksi_controls` (373 edges, `basis='fedramp_stated'`, confidence 0.9,
0 unresolved) · `fedramp_rules` (246, keyed rule×pipeline×subgroup) · `fedramp_odp_pins` (16) ·
`fedramp_ctl_guidance` (65). Never enters `framework_projection` / `overlap_matrix` /
`master_mappings` — the matrix stays 120 pairs and FedRAMP r5's projection rows are untouched.
Query: `dbz_query.py fedramp --coverage | --ksi FAM | --indicator ID | --control CTRL | --rules FAM`.

## The verified timeline (fedramp.gov/2026/timeline/)

2026-07-04 optional early adoption · 2026-07-06 initial implementation + Marketplace listings ·
2026-07-28 FedRAMP Ready → legacy · 2026-08-03 Class A pipeline · 2026-08-10 temporary Rev5 B/C
pipelines · 2026-08-31 Class B/C pipelines · **2027-01-01 mandatory adoption** ·
**2027-06-11 end of NEW Rev5 certifications** (existing ones persist). All tracked as
`au-fedramp-*` horizon records; the rules dataset itself is watched via `info.last_updated`
(feed `fedramp-20x`, api_poll) and the schema set via the date-versioned filenames
(feed `fedramp-schemas`). The RFC pipeline (`/rfcs/`, latest observed RFC-0031) is watched by
`fedramp-rfcs`.

## Cross-mapping verdicts

- **Official, ingested:** KSI→800-53 r5 (373 edges — FedRAMP's own published mapping); FedRAMP
  CTL ODP pins + guidance; Rev5 baselines⊂800-53 (already in the DB via the 53B pins).
- **Officially absent (recorded, never fabricated):** KSI→CSF 2.0 / ISO / SOC 2. Transitive
  KSI→commercial-framework reach via the existing spine bridges is a named follow-up behind a
  design review.
- **Verify-before-trust follow-ups:** FedRAMP↔DoD IL equivalency, FedRAMP↔StateRAMP/GovRAMP
  reciprocity, FedRAMP↔CMMC statements, a machine-readable Marketplace export
  (api.fedramp.gov / automate.fedramp.gov are proxy-blocked here — probe locally via
  `tools/crawl_seed.ps1`).

## Gates

`test_spine`: 46/10 KSI counts, ≥370 edges, 0 unresolved controls, pipeline vocabulary exact,
CTL completeness (16+65), carry-over ≥90% (measured 95.2%), containment + FedRAMP r5 seat.
`validate_spine` check 13: fedramp_stated tracing, id/status/lifecycle enums, ODP well-formedness,
containment. Deterministic rebuild ×2; the full battery unchanged.
