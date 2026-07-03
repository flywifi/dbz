# Standards currency — audit of 2026-07-02

> **Phase 14 refresh (same day):** live data feeds populated (CISA KEV 2026.07.01 — 1,631 CVEs;
> MITRE ATT&CK v19.1 — 697 techniques; eCFR 45 CFR 164 subpart C — 9 sections), new artifacts
> fetched and sha-pinned (NIST SP 800-172 Rev 3 OSCAL, SCF 2026.1.1, Microsoft SSPA DPR v12,
> CSA STAR bundle incl. CCM v4.0.13 + CCM OSCAL dataset + AICM v1.1), and the keep-current
> pipeline stood up: `tools/standards_refresh.py` (check/fetch/gate stages),
> `.github/workflows/standards-watch.yml` (monthly cron + drift issue), registry hygiene
> fields (`auto_fetch` / `artifact_status` / `last_verified`) on all 129 feeds, and a
> dead-cron alarm in `health_audit.py`. Operating procedure: `docs/standards-refresh-runbook.md`.
>
> **SOC report-type classification:** SOC 1/2 "Type 1" vs "Type 2" are report types
> (point-in-time vs period), not framework versions. The four ER crosswalk CSVs map to two
> standards: SOC 1 → SSAE clarified standards (AT-C 320, SSAE No. 22 current), SOC 2 → AICPA
> TSC 2017 + 2022 revised points of focus.
>
> **Phase 15 (2026-07-02):** full SCF ecosystem ingested (user-provided) — controls xlsx
> 2026.1.1 verified byte-identical to the GitHub fetch, plus the pieces the xlsx-only fetch
> missed: **Errata 2026.1.1** (ISO 27002 trailing-zero fix; 13 authoritative sources added,
> 800-63B/OWASP-2021/FedRAMP-R4 removed), Guidebook **2026.2**, CAP Body of Knowledge, 12
> assessment guides, CDPAS/MADSS, SCRMS playbook (`source_data/scf/`). Authority semantics
> refined to the **acceptance model**: an owner's crosswalk states what THEY accept for their
> own framework's audits (CSA→STAR, SCF→CAP) — scope-relative, never modifying other
> standards; see the runbook's authority-model section.
>
> **Phase 17 (2026-07-03):** ISO/IEC 27001:2022 Annex A text on disk (user-provided workbook,
> manifest id `iso-27001-2022-annex-a-text`) — a licensed private verification copy covering
> all 93 Annex A controls (the workbook stores ids as numbers, so `5.10`-style ids are
> recovered from ordinal position; see the manifest note). Annex-side strong consensus pairs
> upgrade from `pending_licensed_artifact` to `texts_on_file_licensed`; ISMS-clause pairs stay
> pending (only selected clause excerpts on file). A certification-body impartiality guidance
> doc (`iso-cert-body-guidance`) is registered as reference-only.
>
> **Phase 18 (2026-07-03):** the consensus provenance tier went live behind the
> `consensus_provenance` flag after its oracle-validation gate passed (validate_spine check 6:
> structural metrics identical tier-on/off with the SOC2×ISO band held; production-corroboration
> enrichment 2.33× strong vs moderate; ISO-side oracle coverage 55.9%). Overlap pairs
> corroborated by strong text-confirmed consensus now report confidence 0.85
> (`provenance: consensus`) instead of the hub-gated 0.65 — confidence-only, still
> `needs_confirmation`. Schema 3.6 adds consensus corroboration counts to `overlap_matrix`.

Every framework version pinned in this repo was checked against the latest published release
(live sources: csrc.nist.gov, hitrustalliance.net, pcisecuritystandards.org, cisecurity.org,
hhs.gov, fedramp.gov, cloudsecurityalliance.org, dl.dod.cyber.mil, aicpa-cima.com).
`canonical-sources/feed_registry.json` is the machine-readable registry; this note records the
audit verdict and the deliberate pins.

| Standard | Current (verified 2026-07-02) | Repo state |
|---|---|---|
| NIST SP 800-53 / 800-53A | Release 5.2.0 (Aug 2025; OSCAL content last modified 2026-05-11) | Catalog data 5.2.0-complete; verified against the NIST CPRT 5.2.0 export (validate_spine oracle) |
| DISA CCI List | 2025-01-23 | Ingested XML is that release (native rev-5 references) |
| NIST SP 800-171 | Rev 2 remains the CMMC basis (DoD class deviation, May 2024); Rev 3 published May 2024 | Crosswalk pinned to r2 — correct for CMMC; DoD's April-2025 Rev-3 ODP-values memo is a candidate future `odp_values` seed |
| CMMC | 2.0 (final rule Dec 2024); Phase 2 (C3PAO for Level 2) begins Nov 2026 | Current |
| SOC 2 / AICPA TSC | 2017 TSC with 2022 revised points of focus | Current |
| ISO/IEC 27001 / 27002 | 2022 editions (+Amd 1:2024, climate text — no control changes); 2013 certs expired 2025-10-31 | Current. The 2013→2022 major revision (114 controls/14 clauses → 93 controls/4 themes, 11 new controls) is recorded in `framework_changelog.json`; `feed_registry.json` tracks 27001 and 27002 separately. |
| HIPAA Security Rule | 2013 Omnibus still the enforceable standard; Jan-2025 NPRM not finalized (OCR missed its spring-2026 target) | Current; registry tracks the pending NPRM |
| HITRUST CSF | v11.8.0 (2026-05-08; mandatory for new e1/i1 since 2026-05-07) | **Deliberate pin:** the hub mapping uses the licensed v11.4.0 authoritative-sources cross-reference (March 2025) — the newest artifact on disk. Registry records v11.8.0 as current. |
| PCI DSS | v4.0.1 (no v4.1 exists; all future-dated requirements mandatory since 2025-03-31) | Current (spec PDFs + PCI↔ISO crosswalk on disk) |
| CIS Controls | v8.1 (Jun 2024) | Registry current; the HITRUST hub's CIS column maps to v8.0 ids (what that source states) |
| NIST CSF | 2.0 | Current |
| CSA CCM | v4.1 (2026-01-28); CAIQ v4.1 | Registry current; raw CCM artifact remains v4.0.x pending refresh |
| FedRAMP | Rev 5 baselines active; 20x transition underway — Certification Classes A–D (NTC-0004, Feb 2026; CR26 consolidated rules valid through 2028), submissions open Jul 2026, Rev 5 expected to retire end-2027 | Registry tracks both |
| GDPR | 2016/679 unchanged | Current |

## ISO 27001/27002:2022 canonical id policy

All ISO data in the repo is 2022-edition, but the three sources spell the same identifiers
differently (OLIR `A.5.1`; HITRUST hub `5.1a`; ER production CSVs `A.05.01` / `06.01.01`).
`spine_normalize.normalize_iso_id()` canonicalizes at load time — Annex A controls are
A-prefixed and unpadded (`A.5.1`), ISMS management clauses are bare with space-separated
sub-parts (`10.2 a.1`) — so citations join across sources. A bare 2-segment id that falls
inside both the ISMS-clause and Annex-A ranges (e.g. `5.1`) is classified `ambiguous` and kept
bare, never promoted — the build reports the count (`iso_ambiguous`). The official 2013↔2022
correspondence lives in ISO/IEC 27002:2022 Annex B; that artifact is not in the repo, so no
legacy 2013-id bridge exists yet — add the artifact before loading 2013-cited report data.
Raw ER CSVs stay untouched on disk (canonical production data); normalization is load-time only.

## Deliberate pins (not staleness)

- **HITRUST v11.4.0 cross-reference** — the authoritative-sources cross-reference spreadsheet is
  a licensed artifact; v11.8.0's equivalent is not freely redistributable. The mapping stays
  pinned to the artifact we hold, the registry records the true current version, and the delta
  is visible in `framework_changelog.json`.
- **NIST 800-171 r2 for CMMC** — r2 is what CMMC assessments legally target until DoD completes
  Rev-3 rulemaking (expected 12–24 months notice).
- **CIS v8.0 ids in the HITRUST hub** — that column is what the v11.4.0 source states; upgrading
  the label without a v8.1-mapped source would fabricate a crosswalk.

## How this stays current

`canonical-sources/feed_registry.json` drives `announcement_monitor.py` (RSS/landing polling) and
`framework_monitor.py`; version transitions land in `canonical-sources/framework_changelog.json`
(machine-generated entries carry `human_confirmed: false` until verified). The CPRT completeness
oracle and the sub-part inventory checks run in `cross-mapping/tests/validate_spine.py` on every
validation pass.
