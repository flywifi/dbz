# Standards refresh runbook

How the repo's framework versions stay accurate. The machine does the watching;
a human does the confirming.

## Cadence

| When | What | How |
|---|---|---|
| Monthly (automated) | Drift check | `.github/workflows/standards-watch.yml` runs `tools/standards_refresh.py --check`, uploads the drift report, and files/updates a `standards-drift` issue when anything moved |
| Quarterly (human) | Artifact refresh | `python3 tools/standards_refresh.py --check --fetch --gate` locally; review the diff; commit with sha256 + `retrieved` bumps in `source_manifest.json` |
| On any `major_revision` in the drift report | Phase task | Open a dedicated phase (like Phase 13's ISO work) — a major revision is a data-model event, never a silent re-pin. The pending CMMC→800-171r3 transition is the canonical example |

## The four stages (`tools/standards_refresh.py`)

1. **check** — `framework_monitor.py` + `announcement_monitor.py` signals, classified per feed:
   `current / registry_stale / artifact_stale / licensed_pinned / metadata_only / on_demand /
   check_failed`. Report: `cross-mapping/output/standards_drift_report.json`.
2. **fetch** (`--fetch`) — re-downloads ONLY `auto_fetch: true` feeds (KEV, ATT&CK STIX,
   DISA CCI, 800-53 OSCAL, SCF). Nothing semantic is auto-merged.
3. **diff** — version transitions land in `framework_changelog.json` as
   `human_confirmed: false` stubs; OSCAL sources can be diffed control-level with
   `cross-mapping/engine/oscal_diff.py --write-changelog`.
4. **gate** (`--gate`) — rebuild grc.db + the deterministic gate battery; red run = human looks.

## Licensed-artifact checklist (quarterly, cannot be auto-fetched)

| Artifact | Where to obtain | What to re-pin |
|---|---|---|
| HITRUST Authoritative Sources Cross-Reference | hitrustalliance.net (licensed) | `hitrust-csf-cross-reference` manifest entry + hub loader column headers (versioned!) |
| ISO 27001/27002 texts + Annex B 2013↔2022 correspondence | iso.org (purchase) | Enables the legacy-ISO-id bridge (see docs/standards-currency.md) |
| CIS Controls v8.1 mapped artifact | cisecurity.org (registration) | Would lift the HITRUST hub's CIS column off v8.0 ids |
| CSA CCM v4.1 xlsx | cloudsecurityalliance.org (registration) | `csa-ccm-v4` manifest entry |

## Confirm loop

Machine-generated changelog entries carry `human_confirmed: false`. After verifying a
transition against the primary source, flip it to `true` and fill `confirmation_source`.
The health auditor treats unconfirmed entries as advisory, never authoritative.

## Alarms

- `health_audit.py --scan` warns when any `auto_fetch` feed's `last_checked` is older than
  90 days — the dead-cron detector.
- `validate_spine.py` holds the CPRT 5.2.0 completeness oracle + sub-part inventory checks,
  so a botched refresh fails the gate rather than shipping.

## Day-1 completeness policy

Everything a user needs ships in the repo — no runtime fetches, no surprise token/network
usage. Data feeds are stored artifacts (KEV, ATT&CK, eCFR, EDGAR are in `canonical-sources/`
and loaded into grc.db at build). A feed may only be `fetch_blocked` (endpoint unreachable —
listed below with the fix) — never silently "on demand".

## Authority scoping — CSA STAR

CSA materials (CCM, CAIQ, AICM, STAR) are authoritative **only for CSA STAR audits and
certifications**. They must never override or modify NIST / ISO / other standards' data. Any
canonical conflict between CSA and another standard is surfaced through the minority-report
policy (`skills/shared/minority-report.md`) with both citations — reported, not merged.
Id-level check 2026-07-02: all 1,684 CCM→800-53 OSCAL mapping targets resolve in the
r5.2.0 catalog (zero conflicts found); semantic mapping-quality conflicts will be evaluated
if/when a CSA projection phase is approved.

## Known open follow-ups (as of 2026-07-02)

- `nist-800-63b-requirements.json` still derives from 63B **r3**; regenerate from 63B-4.
- CMMC → 800-171 r3 transition: waiting on DoD rulemaking (12–24 mo notice expected);
  DoD's Apr-2025 Rev-3 ODP memo is the seed for `odp_values` when it starts.
- `olir_crawler.py` endpoint (`csrc.nist.gov/api/olir/finalized`) 404s — re-point to the
  CPRT OLIR catalog.
- SCF + CCM OSCAL loaded as pinned artifacts only — spine projection is a future phase
  (CSA subject to the authority-scope rule above).
- **fetch_blocked** (endpoint fixes needed): NVD (set `NVD_API_KEY`, run
  `nvd_api_loader.py --days 90`), EUR-Lex (rework loader against the Cellar/ELI API),
  FIPS-CMVP (re-point the loader). EDGAR is fetched and stored (85 disclosures).
