# Standards currency — audit of 2026-07-02

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
| ISO/IEC 27001 | 2022 (+Amd 1:2024, climate text — no control changes); 2013 certs expired Oct 2025 | Current |
| HIPAA Security Rule | 2013 Omnibus still the enforceable standard; Jan-2025 NPRM not finalized (OCR missed its spring-2026 target) | Current; registry tracks the pending NPRM |
| HITRUST CSF | v11.8.0 (2026-05-08; mandatory for new e1/i1 since 2026-05-07) | **Deliberate pin:** the hub mapping uses the licensed v11.4.0 authoritative-sources cross-reference (March 2025) — the newest artifact on disk. Registry records v11.8.0 as current. |
| PCI DSS | v4.0.1 (no v4.1 exists; all future-dated requirements mandatory since 2025-03-31) | Current (spec PDFs + PCI↔ISO crosswalk on disk) |
| CIS Controls | v8.1 (Jun 2024) | Registry current; the HITRUST hub's CIS column maps to v8.0 ids (what that source states) |
| NIST CSF | 2.0 | Current |
| CSA CCM | v4.1 (2026-01-28); CAIQ v4.1 | Registry current; raw CCM artifact remains v4.0.x pending refresh |
| FedRAMP | Rev 5 baselines active; 20x transition underway — Certification Classes A–D (NTC-0004, Feb 2026; CR26 consolidated rules valid through 2028), submissions open Jul 2026, Rev 5 expected to retire end-2027 | Registry tracks both |
| GDPR | 2016/679 unchanged | Current |

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
