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

## STIG library harvest + delta procedure (Phase 21)

The STIG layer is **CCI application evidence**, not a STIG registry. Keeping it current:

1. **Delta check** — `standards_refresh.py --check` runs `stig_harvest.py --check`, comparing
   the live cyber.trackr.live catalog (1 API call) against the committed `stig_catalog.json`.
   Drift = new / removed / changed titles + stale harvested benchmarks.
2. **Incremental refresh** — `standards_refresh.py --fetch` runs `stig_harvest.py
   --refresh-stale`: re-harvests only the drifted benchmarks (per-title DISA zip first,
   trackr per-rule crawl as fallback) and rewrites the two artifacts deterministically.
3. **Quarterly library refresh** — when DISA posts a new SRG-STIG Library compilation,
   fetch it and run `stig_harvest.py --full --from-zip U_SRG-STIG_Library_<Month>_<YYYY>.zip`
   (the multi-hundred-MB zip is NEVER committed). The URL is discovered at run time
   (`dl.dod.cyber.mil/.../U_SRG-STIG_Library_{Month}_{YYYY}.zip`, months Jan/Apr/Jul/Oct).
4. **Rebuild** — `--gate` regenerates the DB tables (build artifacts, never hand-patched);
   validate_spine check 9 + test_spine STIG fixtures must stay green.

Historical/sunset titles stay catalogued (delta-tracked) but rule-harvested on demand
(`stig_harvest.py --via-trackr --titles ...`) — they add ~0 new CCIs (the CCI vocabulary is
product-agnostic).

## Source-class completeness checklist (every ingestion + quarterly)

**Root-cause guard.** The CCI *definition* source (DISA CCI List) was ingested in Phase 11,
but the layer where CCIs are *applied* (STIGs) went unevaluated until Phase 21 — an avoidable
coverage gap. For **every** source, explicitly evaluate and record a verdict for its adjacent
layers as candidate feeds:

- **Upstream (what defines it):** the standard/authority the source derives from.
- **Downstream (what applies/consumes it):** the artifacts that implement or reference it.
- Record each verdict in `feed_registry.json` (ingest / watch-only / not-applicable) so a
  skipped layer is a decision on the record, never an oversight.

Worked example (the CCI class): CCI List (definition) → **STIGs** (application, Phase 21) →
**SRGs** (the requirement templates STIG rule version-ids trace to). SRG-level ingestion is
**evaluated and queued** as a named follow-up (STIG `version_id`s carry SRG lineage), not
silently ignored.

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
- `validate_spine.py` also holds the **consensus provenance gate** (Phase 18): the flag-gated
  `multi_source_consensus` overlap tier (`consensus_provenance` in `feature_flags.json`) may
  stay enabled only while (a) the tier changes no structural overlap metric and the SOC2×ISO
  band holds with the tier on, (b) strong consensus pairs remain production-corroborated at
  ≥ 1.2× the moderate-tier rate with ≥ 10 corroborated strong pairs, and (c) the ISO ids on
  eligible strong pairs cover ≥ 50% of the ISO ids the ER production oracle co-cites with
  SOC 2 (thresholds pinned below measured values at gate-authoring time — 2.3× and 55.9%).
  A red gate run means: disable the flag (`enabled:false` or `DBZ_FF_CONSENSUS_PROVENANCE=0`),
  then investigate — the overlap engine degrades cleanly to hub-gated 0.65 confidence.
- `validate_spine.py` check 8 holds the **master-surface gates** (Phase 19): tier/provenance
  integrity, hard-zero proprietary-id leak, label round-trip through `framework_labels`,
  HIPAA 800-66↔hub citation reconciliation ≥ 50% (observed 73.2%), CSF2 OLIR↔concept-crosswalk
  parity ≥ 95% (observed 100%), PCI on-spine sanity, and matrix completeness (C(14,2)=91).
  `master_mappings` and all projections are **build artifacts** — a refreshed source flows
  through `--gate` (rebuild + battery) and the master DB regenerates; it is never hand-patched.
  Determinism comparator: `grc_manifest.json → table_digests` (sorted-row sha256 per table),
  identical across double builds.

## Day-1 completeness policy

Everything a user needs ships in the repo — no runtime fetches, no surprise token/network
usage. Data feeds are stored artifacts (KEV, ATT&CK, eCFR, EDGAR are in `canonical-sources/`
and loaded into grc.db at build). A feed may only be `fetch_blocked` (endpoint unreachable —
listed below with the fix) — never silently "on demand".

## Authority model — acceptance rules, not adversarial claims

A framework owner's crosswalk is the **acceptance rule for their own framework**:

- **CSA** saying "800-53 control X maps to CCM requirement Y" means CSA accepts X as
  satisfying Y **for CSA STAR audits and certifications**. It is not a claim about what
  NIST accepts.
- **SCF** saying "SCF #1 maps to control X" means SCF accepts X as satisfying SCF #1
  **for SCF/CAP purposes**. Same principle.

Consequences the engine and future loaders must respect:
1. Owner-authored mappings are authoritative *within the owner's scope* (source-provided
   tier). Third-party views of someone else's framework (e.g. SCF's CCM column, HITRUST's
   ISO column) are bundled-crosswalk tier — one rung lower in the CLAUDE.md precedence.
2. Divergences BETWEEN owners (CSA's CCM→NIST vs SCF's CCM↔NIST view) are **not conflicts
   to adjudicate** — both are simultaneously valid in their own scopes. They become
   minority-report entries only when the engine must answer a single question (e.g. "does
   satisfying AC-2 satisfy CCM IAM-04 for a STAR audit?") and sources of different tiers
   disagree: the owner's mapping wins as primary, the dissent line records the
   lower-tier variance with both citations.
3. No owner's mapping ever modifies another standard's data.

Id-level sanity check 2026-07-02: all 1,684 CCM→800-53 OSCAL mapping targets resolve in the
r5.2.0 catalog. The CCM↔SCF divergence analysis (194 controls compared) lives in
`cross-mapping/output/ccm_discrepancy_report.json` — under this model those divergences are
scope-relative acceptance differences, not errors.

## Known open follow-ups (as of 2026-07-03)

- `nist-800-63b-requirements.json` still derives from 63B **r3**; regenerate from 63B-4.
- CMMC → 800-171 r3 transition: waiting on DoD rulemaking (12–24 mo notice expected);
  DoD's Apr-2025 Rev-3 ODP memo is the seed for `odp_values` when it starts. **Phase 19
  landed the data side**: 171r3 + 172r3 CPRT datasets pinned with NIST's own →800-53
  mappings loaded as spine frameworks, NIST's r2→r3 analysis workbook + r3 CUI overlay
  pinned, and `framework_changelog` entries seeded.
- 171A r3 / 172A r3 assessment-objective loading (artifacts pinned, 157 objective-level
  refs to 800-53A 5.1.1 available) — assessment-procedure depth for the r3 line.
- **SRG-level ingestion (queued, Phase 21 source-class checklist):** STIG rule `version_id`s
  (e.g. `AZLX-23-000100`) carry SRG lineage; ingesting the SRGs themselves would add the
  requirement-template layer between the CCI list and STIGs. Evaluated, not yet built.
- 800-66 / CSF2 / 171r3 OLIR sets as **consensus voters** (currently projections/pairs
  only) — would add NIST-ancestry voters, so it needs a re-measured Phase 18 gate first.
- CSF 2.0 OLIR graph artifacts also carry CCM / SCF / CIS 8.1 / NICE / CRI reference sets —
  raw material for the deferred SCF+CCM spine-projection phase.
- `olir_crawler.py` endpoint (`csrc.nist.gov/api/olir/finalized`) 404s — re-point to the
  CPRT OLIR catalog.
- ~~SCF + CCM OSCAL loaded as pinned artifacts only — spine projection is a future phase~~
  **CLOSED (Phase 20)**: both are spine frameworks now — `SCF 2026.1` (scf_direct 0.80,
  SCF/CAP scope) and `CSA CCM v4` (ccm_oscal 0.85 source-stated, CSA STAR scope) — under
  the new `owner_stated` master-surface tier. Remaining upgrades: SCF's per-framework STRM
  PDFs would add relationship semantics to scf_direct; a de-gated CCM v4.1 OSCAL supersedes
  the v4.0.12 pin on arrival.
- SCF errata note: the 2026.1 release REMOVED NIST SP 800-63B, OWASP 2021, FedRAMP R4 and
  others from SCF's authoritative sources and added 13 (OWASP 2025, CJIS v6.0, IEC 62443
  set, GovRAMP…) — relevant when SCF projection lands.
- **fetch_blocked** (endpoint fixes needed): NVD (set `NVD_API_KEY`, run
  `nvd_api_loader.py --days 90`), EUR-Lex (rework loader against the Cellar/ELI API),
  FIPS-CMVP (re-point the loader). EDGAR is fetched and stored (85 disclosures).
