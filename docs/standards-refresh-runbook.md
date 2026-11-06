# Standards refresh runbook

How the repo's framework versions stay accurate. The machine does the watching;
a human does the confirming.

## Cadence

| When | What | How |
|---|---|---|
| Weekly, Monday (automated; monthly until phase 51) | Drift check | `.github/workflows/standards-watch.yml` runs `tools/standards_refresh.py --check`, uploads the drift report, and files/updates a `standards-drift` issue when anything moved (including a 45-day inactivity warning) |
| Weekly, Tuesday–Thursday (automated; phase 51) | Data refresh, proposed as pull requests | `.github/workflows/weekly-refresh.yml` runs one slot of `canonical-sources/fetch_schedule.json` per day and opens or updates one PR per slot for human review; report-only results go to the `weekly-digest` issue. See **Weekly rotation** below |
| Quarterly (human) | Artifact refresh | `python3 tools/standards_refresh.py --check --fetch --gate` locally; review the diff; commit with sha256 + `retrieved` bumps in `source_manifest.json` |
| On any `major_revision` in the drift report | Phase task | Open a dedicated phase (like Phase 13's ISO work) — a major revision is a data-model event, never a silent re-pin. The pending CMMC→800-171r3 transition is the canonical example |

## The four stages (`tools/standards_refresh.py`)

1. **check** — `framework_monitor.py` + `announcement_monitor.py` signals, classified per feed:
   `current / registry_stale / artifact_stale / licensed_pinned / metadata_only / on_demand /
   check_failed`. Report: `cross-mapping/output/standards_drift_report.json`.
   Every row carries a `signal` field saying what its classification is worth:
   `github_release_api` rows are **live version comparisons** (the 19 `check_strategy:
   github_release` feeds; latest release tag vs `current_version`, boundary-guarded, failing
   CLOSED to `check_failed` when the API is unreachable — fixture proof:
   `standards_refresh.py --selftest-release-check`); `stored_status_only` rows merely echo the
   stored `artifact_status` and are **not** a live verdict (phase 45: SCF 2026.2 sat behind a
   "current" echo for ten weeks). A `registry_stale` row is **blocking-until-triaged**:
   re-verify at origin, update the feed via `registry_io`, and route any artifact impact
   through the normal human-reviewed loader phase.
2. **fetch** (`--fetch`) — re-downloads ONLY `auto_fetch: true` feeds (KEV, ATT&CK — from
   MITRE's TAXII server with the CTID NIST mapping since phase 51, the Thursday slot's source —
   DISA CCI, 800-53 OSCAL, SCF). Nothing semantic is auto-merged.
3. **diff** — version transitions land in `framework_changelog.json` as
   `human_confirmed: false` stubs; OSCAL sources can be diffed control-level with
   `cross-mapping/engine/oscal_diff.py --write-changelog`.
4. **gate** (`--gate`) — rebuild grc.db + the deterministic gate battery; red run = human looks.
   The double-build digest comparison covers every content table by derivation (exclusions,
   each reasoned in `build_db.py`: SQLite internals, FTS5 shadow tables, `db_metadata`).
   The full local battery (authority list: `protocol-layer/quality-gates.md`) adds, on a built
   grc.db: the oracle accuracy benchmark (`cross-mapping/tests/benchmark_oracles.py --check`;
   policy in `docs/BENCHMARK.md`), the twelve-scenario end-to-end battery
   (`cross-mapping/tests/run_scenarios.py`), and the scoreboard drift check
   (`tools/metrics.py --check`, also sync_check invariant 13). Build-independent gates run in
   pre-commit: `tools/output_validate.py --selftest`, `score_output.py --selftest`, and the
   staged-diff `tools/secret_scan.py`. CI runs the build-dependent set in `standards-watch`
   after its fresh build; `health.yml` runs the build-independent set on every push.
   Registry edits additionally surface as advisories via `tools/registry_currency.py --check`
   (writes go through the single writer, `tools/registry_io.py`).

## Rehearse CI before pushing (`tools/ci_rehearsal.py`)

Run `python3 tools/ci_rehearsal.py` before every push. It stashes the gitignored build
outputs so the tree matches CI's fresh checkout, runs every step of
`.github/workflows/health.yml` verbatim (a drift check warns if the workflow and the harness
ever diverge), restores the artifacts unconditionally — even after an interrupted run — and
prints a per-step PASS/FAIL table. This closes the recurring failure class where a check
passes on a built workspace but fails on CI. Never run it concurrently with `build_db.py`.

**Package-free, like the runner (phase 51).** `health.yml` installs no packages, so the rehearsal
runs the health steps under a throwaway venv with no packages, first on PATH. A health-step
script or test must therefore need only the standard library (load one function from its source,
as `test_attack_loader.py` does with `build_db.load_attack_data`, rather than import a module
that pulls in pandas). The first 0.16.0 CI run (41958122419) went red on exactly that import,
after a rehearsal on an interpreter that had pandas had passed.

**Coverage limit:** the rehearsal mirrors `health.yml` only. `standards-watch.yml` runs a
different step list (drift check + fresh build + benchmark) and has its own fresh-checkout
failure mode — rehearse it with `python3 tools/ci_rehearsal.py --standards-watch` before
touching that workflow or the generators it depends on.

## Phase hygiene (learned rules — phase-33 audit)

- **Commit messages are 1–2 plain sentences.** If the change list does not fit, it belongs in
  the `changes/CHANGELOG.md` entry, not in the message. (Two phase-32 commits ran to 3–4
  sentences; the itemization should have gone to the changelog.)
- **Cut the phase snapshot anchor BEFORE the first data-touching commit,** as its own commit.
  An anchor added inside the first data commit cannot serve as that commit's rollback point.
- **Deliberate scope drops get recorded.** If a planned deliverable is dropped for a good
  reason (typically the provenance floor: nothing citable), say so in the changelog entry —
  a silent deviation is indistinguishable from an oversight when read later.

## Shared fetch layer (`cross-mapping/engine/fetchkit.py`)

All live fetching in the monitors routes through fetchkit: per-host pacing (min interval +
jitter + robots Crawl-delay), Retry-After / RateLimit-Reset respect, a circuit breaker
(4 consecutive 403/429/503 → 15-minute cooldown), each host's **published usage rule**
(next section), a runaway ceiling of 600 requests per run, and an ETag/Last-Modified + sha256
conditional-GET cache. Learned limits and cache state persist in
`.fetch-cache/` (gitignored). Repeat refresh runs are therefore mostly 304 header exchanges.

**Wayback labeling rule (non-negotiable):** `fetchkit.resilient_get` can fall back to a
Wayback snapshot on hard failure, and the result is ALWAYS labeled (`source="wayback"` +
`snapshot_ts`). An archive copy is never live currency: any consumer must record the label in
its notes, must never update a feed's currency fields from it, and HEAD-based currency polls
set `allow_wayback=False`. Canonical-artifact fetches in `standards_refresh.py` are live-only.
Escape hatch for manual verification: delete `.fetch-cache/fetch_state.json` to force full
re-downloads. Offline unit tests: `cross-mapping/tests/test_fetchkit.py`.

## Host usage rules — never overload a source (Phase 50)

`canonical-sources/host_policies.json` records, for every host the monitors contact, the host's
**published** usage rule quoted verbatim (or `none published` with the date it was checked) and
the limits the governor enforces. The rules recorded on 2026-11-04 include:

| host | published rule | enforced |
|---|---|---|
| ncp.nist.gov | "use the META file … less than 200 requests per day" | read `.meta` before any `.xml.gz`/`.zip`; 10 per run |
| services.nvd.nist.gov | 5 per rolling 30 s (50 with an API key) | the same rolling window |
| api.github.com | 60/h unauthenticated; 1,000/h per repository with `GITHUB_TOKEN` | 50 per run; the Monday and weekly-refresh workflows pass their token |
| www.ecfr.gov | the full-XML endpoint requires `Accept-Encoding` | header added automatically; 4 s; robots override for that one documented API path, with both citations |
| github.com | robots.txt: "If you would like to crawl GitHub contact us … We also provide an extensive API"; `*` group disallows `/*.atom$` | `…/releases.atom` refused (release currency is read through api.github.com); 25 per run |
| all others | none published | 1.5 s between requests, 25 per run |

How it is enforced:

- **robots.txt follows RFC 9309.** A 4xx means no rules. A 5xx or a transport failure means
  complete disallow for that run, and the refusal names the error (TLS, timeout). An HTML page
  answering for `/robots.txt` is not a robots file.
- **Blank lines are not group breaks.** Python's stdlib parser treats them as breaks and so
  drops real Disallow rules. fetchkit strips blank lines first; this is pinned by a fixture.
- **The most specific rule wins** (RFC 9309 §2.2.2): the longest matching pattern decides, an
  `Allow` wins a tie, and `*` / `$` are honoured. Every group naming our product token is
  merged; failing that, the `*` groups apply. The stdlib parser applies the *first* match, and
  on the first CI dispatch it refused `www.ismap.go.jp/csm`, the one path that file allows
  (`Disallow: /` is listed before `Allow: /csm`). Since 0.15.1 fetchkit evaluates robots
  itself (`RobotsRules`), pinned by the ISMAP fixture and the RFC's own examples. Any group
  record (`Crawl-delay` included) ends a run of user-agent lines: law.lis.virginia.gov's
  `GPTBot: Disallow: /` must not merge into its `*` group (fixture-pinned).
- **Every refusal is recorded.** A broken rule raises `PolicyRefused`. It is written to the
  per-run ledger (`fetch_ledger` / `policy_refusals` in the drift report) and surfaces in the
  drift issue. It is never retried in the same run.

The CI gate is `python3 tools/fetch_census.py --check`. It replays one Monday `--check`
offline and fails if any request bypasses the governor or any host's planned count exceeds its
cap. Since phase 51 it also sums each weekday's slot load from `fetch_schedule.json` against the
same caps and checks that every slot's cron is in its workflow file (see **Weekly rotation**). It is an upper bound: every landing page costs HEAD+GET, and every GitHub repo answers "no
releases", so each release feed also costs its tags call. In 0.15.1 it planned **327 requests to 96 hosts,
with api.github.com the busiest at 38 of 50**, and the first CI dispatch made 272; after phase 52
(release rows moved to landing polling, the atom entries gated, cmmc exempt, the build's OSCAL fetch
gone) the Monday plan is 230 requests with api.github.com at 8 of 50, and the 2026-11-06 dispatch
made 233 requests to 94 hosts with 0 refusals. (The 0.15.0
census answered GitHub with a release and counted 37, while the live run made 54. The monitor
and `standards_refresh` both looked up every release feed. Since 0.15.1 the monitor skips them
there with `--skip-strategy github_release`, and the census models the tags fallback.)

**Correction of record (phase 51).** 0.15.0 and 0.15.1 said every monthly fetch went through
the governor. It did not: `standards-watch.yml`'s build step warms the OSCAL cache with
`oscal_diff.py --oscal-cache … --dry-run`, which read the 5,136,923 B catalog in 512 KiB Range
windows (1 probe + 10 windows = 11 requests to raw.githubusercontent.com) through its own
ungoverned loop. The census replayed only `--check`, so the step was invisible to it. Since
phase 51 the windows are governed (`fetchkit.fetch`, one counted request each), and the census
counts them as `build_requests_measured` on every day whose workflow builds.
**Phase 52 removed the warm-up altogether:** the OSCAL catalog the build reads is committed at
`canonical-sources/source_data/nist-800-53/NIST_SP-800-53_rev5_catalog.json` (sha256 pinned in
`source_manifest.json`), so the build makes no network request, `build_requests_measured` is
empty, and a fresh checkout builds from the same input as the committed derived data. An
upstream OSCAL refresh arrives through `standards_refresh --fetch`, which now writes that
committed path, as a reviewed diff.

To add a host:
1. Quote its rule from its own page into `host_policies.json` via `registry_io`, with `verified`
   and `probe`.
2. Set `enforced` at or below the rule.
3. Run the census.
4. **Re-verify every host's rule yearly** (each entry carries its `verified` date).

The first governed live run (2026-11-04) refused exactly what the rules require:
- `capitol.texas.gov` disallows `/BillLookup/`, so the `texas-tdpsa` feed now polls the codified
  statute instead.
- `www.ismap.go.jp` allows only `/csm`, so the `japan-ismap` feed now polls `/csm`.
- Four hosts' robots.txt failed TLS or timed out from that network (`www.acq.osd.mil`,
  `www.cnss.gov`, `www.ilga.gov`, `www.cyber.gov.au`). Their pages fail the same way, so this is
  no regression. The ledger now names the cause.

The first CI dispatch (run 41936204283, 2026-11-04) read the STIG verdict live (library, NCP
and trackr all `same`). It showed the four TLS/timeout hosts fail the same way from GitHub's
runners (the three TLS hosts fail certificate verification with "unable to get local issuer
certificate"; cyber.gov.au timed out). It also found the two defects fixed in 0.15.1 (robots
precedence; duplicate GitHub lookups).

## Weekly rotation (Phase 51)

Everything that can be automated runs once a week, spread over four weekdays so no host is hit by
two slots on one day. The schedule is `canonical-sources/fetch_schedule.json` (written only via
`registry_io`); it is the authority over any cadence written in prose.

| Slot | Cron (UTC, provisional) | Workflow | Jobs | Mode |
|---|---|---|---|---|
| `mon-standards-check` | `17 6 * * 1` | `standards-watch.yml` | `standards_refresh.py --check` | drift issue |
| `tue-regulatory` | `41 14 * * 2` | `weekly-refresh.yml` | `fr_watcher` (7 days), eCFR 45 CFR 164 subpart C, eCFR 32 CFR 170 | PR |
| `wed-vulnerability` | `47 14 * * 3` | `weekly-refresh.yml` | KEV (PR); NVD 7-day window (report only) | PR + digest |
| `thu-dod-mitre` | `53 14 * * 4` | `weekly-refresh.yml` | ATT&CK when MITRE's TAXII version differs from ours; STIG library when DISA publishes a newer quarter (`stig_harvest --auto-library`); `horizon_monitor --check` (report only) | PR + digest |

How a slot runs (`tools/fetch_rotation.py`):
- **The cron that fired picks the slot** (`github.event.schedule`), never the date. A run GitHub
  starts hours late (measured: 3h20m–8h08m for our 06:17 cron) still runs its own slot.
- **Date-only changes are reverted.** A `pr` job's output that differs only in a volatile stamp
  (`volatile_keys`: `_as_of_date`, `fetched_at`, …) is restored byte-for-byte, so a PR never
  carries date noise (measured 2026-11-05: the live 45 CFR 164 differed from the committed file
  only in `_as_of_date`).
- **A `report` job never leaves a change.** Its output is kept as a workflow artifact and
  summarised in the digest.
- **When a `pr` job changed a file,** the battery runs on the refreshed tree (generate, build,
  oracle benchmark, scenarios; the OSCAL warm-up went with phase 52). If it passes, `tools/rotation_commit.sh` commits
  the changed files to `auto/refresh-<slot>` under GitHub's noreply bot identity, with a plain
  trailer-free message, and force-pushes that branch only. The default branch is never pushed by
  the bot. The workflow then opens or updates one PR per slot (label `auto-refresh`) and
  dispatches `health.yml` on the branch, because pushes made with `GITHUB_TOKEN` start no
  workflow (the documented exception is `workflow_dispatch`).
- **Nothing merges automatically.** Review the PR's job table and battery output, then merge by
  hand. A stale PR is simply superseded by the next week's force-push.

**Owner setting (one time).** Settings → Actions → General → Workflow permissions → *Allow GitHub
Actions to create and approve pull requests*. Until it is on, the PR step fails and the digest
says so; the refresh branch is still pushed. Optional: an `NVD_API_KEY` repository secret raises
NVD's window from 5 to 50 requests per 30 s.

**The weekly digest.** One open issue labelled `weekly-digest`, edited in place: each slot
replaces only its own section (job table, failed-battery or failed-PR notes, and "Suggested to
commit at your next session"). NVD is report-only and never committed by the schedule; FIPS, OLIR
and CPRT are not scheduled at all, because NIST publishes no machine source for them (phase 52;
`fetch_schedule.json` `not_scheduled` records each probe). `CLAUDE.md` tells every new session to read the digest and the open `auto-refresh` PRs
first. The NVD suggestion is computed from the run: on 2026-11-05 a 7-day window was 9,676 CVEs,
7.3 MB as one file, so the suggestion was "not as weekly snapshots" (about 382 MB a year of
history; commit one rolling file or keep it local, since `build_db` loads it when present).

**Not scheduled** (`fetch_schedule.json` `not_scheduled`, each with its measured reason):
FIPS (the CMVP API is unavailable and NIST publishes no machine listing), OLIR
(`/api/olir/finalized` 404) and CPRT (`/api/catalog/pubs/page` 404). Scheduling them would automate
emptiness. EUR-Lex was on this list until phase 52: its HTML page answers automated clients with a
bot challenge (0 articles), and the loader now reads the Publications Office Cellar, EUR-Lex's
documented reuse channel (322 articles; Tuesday slot). OSCAL is not a job at all: since phase 52 the
catalog is committed and the build reads it.

**Load.** `fetch_census.py --check` (CI) sums each weekday's `requests_measured` per host (the
build makes no request since phase 52) and fails on a cap breach or on one host in two slots of one
day. Today (2026-11-06): Monday 230, Tuesday 10, Wednesday 6, Thursday 65 requests (upper bound;
241/17/17/76 before phase 52).

**Slot times: least GitHub traffic, measured.** GitHub publishes no quiet hour, only that the top
of every hour is busy and that queued scheduled jobs may be dropped under load. So the times above
are provisional. `schedule-probe.yml` (temporary) fires at six candidate times a day and titles
each run with the cron that fired; `tools/schedule_delay.py <runs.json>` gives each time's median
and p90 queue delay and the pin order. **Pin rule:** per slot, the candidate with the lowest median
delay (a tie goes to the lower p90), never minute :00 or :30. After 14 days (2026-11-19 or later)
the slot crons are pinned in `fetch_schedule.json` and both workflows, and the probe is deleted.
Re-check quarterly from the real slot runs; move any slot whose median delay passes 4 h.

**Inactivity.** GitHub disables a public repository's scheduled workflows after 60 days without
activity. The Monday check warns from 45 days since the last commit (drift issue row
`inactivity`); merging a refresh PR counts as activity.

**Add a job.** Add it to `jobs` (argv, mode, outputs, and `requests_measured` from a governed live
dry run, with its date and probe) and to one slot, via `registry_io`; run
`python3 tools/fetch_census.py --check` and `python3 tools/fetch_rotation.py --plan --slot <slot>`.

## STIG library harvest + delta procedure (Phase 21)

The STIG layer is **CCI application evidence**, not a STIG registry. Keeping it current:

1. **Currency check (three signals, phase 50).** `standards_refresh.py --check` runs
   `stig_harvest.py --check --json`, which prints one JSON line:
   - **library:** HEAD probes for a DISA compilation newer than the pinned one. An unpublished
     quarter is a clean 404. This is the complete signal.
   - **NCP:** the NIST checklist feed, under NCP's meta-first rule. It covers about 96
     benchmarks, with sha-256 hashes for the per-title zips.
   - **trackr:** corroboration.

   The verdict is drift if any signal sees a newer release, and `check_failed` only if all three
   fail, each with its reason. *Correction of record:* from July to November 2026 this check
   could only say `check_failed`. It parsed the last line of an indented report, and it kept
   only the last 4,000 characters of output. The trackr host was reachable all along.
2. **Quarterly library refresh** (the usual case): run
   `stig_harvest.py --full --from-zip U_SRG-STIG_Library_<Month>_<YYYY>.zip --retain-absent --refresh-final`.
   - The multi-hundred-MB zip is NEVER committed.
   - `--retain-absent` keeps benchmarks DISA dropped, flagged `not_in_current_library` with
     `last_library`. They are never deleted (schema 3.19).
   - `--refresh-final` fetches DISA's final release for them when the zip name is derivable.
3. **Out-of-cycle titles:** run `stig_harvest.py --refresh-stale`. It tries the NCP-listed zip
   first (sha-256 verified), then DISA's V/R zip rewrite. The trackr per-rule crawl runs only
   with `--allow-trackr-crawl` and is capped by trackr's host policy. Above `--max-delta` it
   refuses, because that is library-scale drift and belongs to step 2.
4. **Rebuild** — `--gate` regenerates the DB tables (build artifacts, never hand-patched);
   validate_spine check 9 + test_spine STIG fixtures must stay green.

Historical/sunset titles stay catalogued (delta-tracked) but rule-harvested on demand
(`stig_harvest.py --via-trackr --titles ...`) — they add ~0 new CCIs (the CCI vocabulary is
product-agnostic).

## Horizon scanning — anticipated updates (Phase 24)

The pipeline now tracks changes that are *expected* to happen, not only ones that already did, so a
scheduled/signaled revision is never missed. Registry: `canonical-sources/anticipated_updates.json`;
watcher: `cross-mapping/engine/horizon_monitor.py`; full model + per-authority signal catalog:
`docs/horizon-scanning.md`.

- **Read the horizon:** `dbz_query.py horizon --upcoming 10` (nearest expectations) /
  `horizon_monitor.py --list`. `standards_refresh.py --check` prints a `horizon` line
  (overdue + due-for-review + draft-observed counts).
- **Act on overdue:** `horizon_monitor.py --overdue` lists records past their window (re-investigate
  the source — did it land? then ingest via the normal human-reviewed loader, and set the record's
  `status` to `materialized`/`superseded`). Materialization is never auto-ingested.
- **Elapsed-but-open (phase 45):** `--overdue` and `--summary` also surface `elapsed_open` —
  every open record whose dated window has passed, **regardless of the escalation grace**.
  Grace exists to pace escalation, not to hide an elapsed window (three elapsed windows sat
  mechanically "watching" inside grace in September 2026). A nonzero `elapsed_open` at the
  Monday check means a human decides: materialize, supersede, or re-date from a source —
  never silence the clock with a derived date.
- **Add an anticipation (crawl-seed procedure):** whenever a source traversal encounters an
  anticipatable signal — a "not available yet" placeholder, a draft/IPD/FPD status, an ISO DIS ballot,
  a HITRUST advisory, a transition-timeline date, or a PCI "best practice until `<date>`" clause — add
  a record to `anticipated_updates.json` (never fabricate a date: use `no_fixed_date`). This is how
  the CCM v4.1 mappings became `au-csa-ccm`.
- **DISA scope:** the horizon tracks the **CCI List** quarterly cadence (new CCI definitions). STIG
  currency is not a horizon record: since phase 50 the three-signal STIG check runs inside the Monday
  drift check, and since phase 51 the Thursday slot proposes a library refresh when DISA publishes a
  newer one (`stig_harvest --auto-library`). (Until phase 52 this bullet still said "STIGs are
  excluded — reference-only per Phases 21/23", which phases 50–51 had superseded.)

## Currency-run findings (2026-07-06)

A full read-only currency run (both monitors + harvest `--check`) established:
- **Monitor repairs:** `announcement_monitor.py` was crashing on every run (a `TypeError` from 16
  feeds whose `announcement_feeds` were bare URL strings) — now coerced + the 16 normalized to dicts.
  `framework_monitor` `poll_exempt`/`manual` strategy added for feeds whose origin cert cannot be
  verified here (`disa-classified-overlay` = `www.cnss.gov`, Federal-PKI). `stig-community-refs` and
  `acasehs-cci` got proper `landing` URLs (the latter points at the raw file, since github.com HEAD
  403s while raw returns 200).
- **NIST 800-53 → Release 5.2.0:** upstream current; the 7 added controls are already in the build via
  the committed 5.2.0 OSCAL supplement + CPRT oracle — a label re-pin (manifest `effective_version` +
  changelog), no data reload.
- **Tracked-deferred (newer upstream, gated/licensed):** CSA CCM v4.1 (registration-gated), HITRUST
  CSF v11.8.0 (licensed) — recorded in `source_manifest` `upstream_available`, held until the artifact
  is obtained. ISO/IEC 27001:2022 Amd 1:2024 (climate) has no Annex A change — low priority.
- **Current, no action:** PCI DSS v4.0.1, NIST CSF 2.0, AICPA TSC, 800-171 r3 / 171A r3 / 172 r3 /
  66r2, SCF 2026.1.1, and the DISA CCI dictionary (2025-01-23).
- **STIG:** deliberately not refreshed — STIGs were only the vehicle to fill missing CCIs/definitions;
  the feed *references* stay in the registry for future users, STIG data/DB are out of core currency.
- **Environmental poll failures are expected:** `framework_monitor`'s live poll returns HTTP 403/404/SSL
  for many `.gov`/`.mil`/ISO/GitHub-API feeds from this sandboxed environment. The monitor is
  offline-safe (records the error, continues, exits 0) — these are access restrictions, not repo defects.

## CCI dictionary + corroboration refresh (Phase 22)

The full DISA CCI dictionary (5,137 CCIs + definitions + status) is the authoritative source of
CCI numbers/definitions and the CCI↔800-53 mapping. Keeping it current:

1. **Delta check** — `standards_refresh.py --check` runs `cci_harvest.py --check` (CCI-list
   version + live trackr enumeration size vs the committed snapshots).
2. **CCI-list release** — when DISA posts a new `U_CCI_List.zip`, download + unzip it over
   `canonical-sources/source_data/U_CCI_List.xml`; the loader ingests the full dictionary on
   rebuild (definitions never gated on mappability).
3. **Corroboration refresh** — `standards_refresh.py --fetch` re-snapshots the acasehs
   republications (`--acasehs`) and the trackr enrichment (`--trackr --enrich --resume`).
4. **Rebuild** — `--gate`; validate_spine check 10 + test_spine CCI fixtures must stay green.

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
silently ignored. **Phase 22 verdict on the definition/mapping layer:** the CCI-list ingestion
itself was incomplete (587 CCIs + definitions dropped); now the *full* dictionary loads and a
`cci_mapping_corroboration` layer cross-witnesses the CCI↔800-53 mappings against the acasehs +
trackr republications and STIG usage — the "confirm existing / gain additional mappings" downstream.

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
  90 days — the dead-cron detector for feeds; for the schedules themselves the Monday check warns
  from 45 days without a commit, because GitHub disables scheduled workflows at 60 (phase 51).
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

## Known open follow-ups (as of 2026-11-06)

- `nist-800-63b-requirements.json` still derives from 63B **r3**, and since phase 52 it says so: the
  built-in section map, no fetched text, no control links. Regenerating from 63B-4 is its own phase.
- CMMC → 800-171 r3 transition: **no transition date is citable** — CMMC Phase 2 was
  suspended 2026-07-13 pending a Reform Task Force review (report due ~Sep 2026), and
  trade-press r3-timing figures failed the citation-loop escape. DoD's 2025-04-10 Rev-3
  ODP memo is sha-pinned with a frozen offline comparison baseline
  (`docs/cmmc-odp-baseline.md`); the `odp_values` load decision reopens after the review.
  Horizon records `au-cmmc-*` escalate on each signal. Regulatory claims entering this
  runbook's registries follow `protocol-layer/regulatory-provenance.md` (verbatim +
  support label + terminal state; mutation check at intake). When the assessment basis
  moves off r2, revisit `_MASTER_FW_GROUPS` in `dbz_query.py` — the `cmmc` alias fans out to
  `CMMC 2.0` + `NIST SP 800-171 r2` precisely because of the May-2024 class deviation. **Phase 19 landed the data
  side**: 171r3 + 172r3 CPRT datasets pinned with NIST's own →800-53 mappings loaded as
  spine frameworks, NIST's r2→r3 analysis workbook + r3 CUI overlay pinned, and
  `framework_changelog` entries seeded.
- 171A r3 / 172A r3 assessment-objective loading (artifacts pinned, 157 objective-level
  refs to 800-53A 5.1.1 available) — assessment-procedure depth for the r3 line.
- **SRG-level ingestion (queued, Phase 21 source-class checklist):** STIG rule `version_id`s
  (e.g. `AZLX-23-000100`) carry SRG lineage; ingesting the SRGs themselves would add the
  requirement-template layer between the CCI list and STIGs. Evaluated, not yet built.
- 800-66 / CSF2 / 171r3 OLIR sets as **consensus voters** (currently projections/pairs
  only) — would add NIST-ancestry voters, so it needs a re-measured Phase 18 gate first.
- CSF 2.0 OLIR graph artifacts also carry CCM / SCF / CIS 8.1 / NICE / CRI reference sets —
  raw material for the deferred SCF+CCM spine-projection phase.
- `olir_crawler.py` endpoint (`csrc.nist.gov/api/olir/finalized`) 404s, and the CPRT catalog
  endpoint 404s too (phase 52 probes): there is no machine source to re-point to, so OLIR and CPRT
  stay report-only and unscheduled until NIST publishes one.
- ~~SCF + CCM OSCAL loaded as pinned artifacts only — spine projection is a future phase~~
  **CLOSED (Phase 20)**: both are spine frameworks now — `SCF 2026.2` (scf_direct 0.80,
  SCF/CAP scope) and `CSA CCM v4` (ccm_oscal 0.85 source-stated, CSA STAR scope) — under
  the new `owner_stated` master-surface tier. Remaining upgrades: SCF's per-framework STRM
  PDFs would add relationship semantics to scf_direct; a de-gated CCM v4.1 OSCAL supersedes
  the v4.0.12 pin on arrival.
- SCF errata note: the 2026.1 release REMOVED NIST SP 800-63B, OWASP 2021, FedRAMP R4 and
  others from SCF's authoritative sources and added 13 (OWASP 2025, CJIS v6.0, IEC 62443
  set, GovRAMP…) — relevant when SCF projection lands.
- **Formerly fetch_blocked (as of 2026-11-06):** NVD works through the governor and is `on_demand`
  (weekly report-only; the digest suggests whether to commit); EUR-Lex is repaired (Cellar, phase
  52); FIPS-CMVP has no machine source. EDGAR is fetched and stored (85 disclosures); since phase 52
  its loader needs `DBZ_SEC_CONTACT` in the environment for the SEC User-Agent contact.

## Crawl-seed link-graph (Phase 25)

The recursive discovery layer expands seed roots into candidate document/link URLs so a future
run finds new documents and sub-domains on its own:

1. `python3 tools/crawl_seed.py --list --format json > candidates.json` — deterministic,
   offline candidate expansion from `canonical-sources/crawl_seeds.json` (OLIR `.rip`
   detail pages, eCFR Versioner, Federal Register saved queries, EUR-Lex CELEX, GitHub OSCAL).
2. Where the managed proxy blocks a host, run the live traversal locally:
   `pwsh -File tools/crawl_seed.ps1 -Candidates candidates.json -Out discovered.json`.
3. `python3 tools/crawl_seed.py --import discovered.json` — dedupe + review the discovered
   URLs before adding any to `feed_registry.json`. Nothing auto-ingests; anticipatable signals
   (a new draft, a transition-timeline date) route to `anticipated_updates.json` (horizon).
4. `--accept <candidate-url>` upserts a **review stub** into
   `canonical-sources/crawl_candidates.json` with its citation-graph provenance
   (`parent_source_id` — who vouched for it). Promotion to `feed_registry.json` stays a manual
   human step. `--prune-report` flags stubs unchecked >180 days or with a vanished parent —
   but fetch-**blocked** stubs are protected (**blocked ≠ gone**: several .gov hosts refuse
   this environment's egress while remaining authoritative); removal is always a human decision.

`crawl_seed.py --selftest` asserts determinism + registry well-formedness (also in the gate
battery via `test_spine`).

## FedRAMP Consolidated Rules currency (Phase 26)

The canonical dataset is continuously revised. Currency checks:
1. Poll `info.version` / `info.last_updated` in
   `raw.githubusercontent.com/FedRAMP/rules/main/fedramp-consolidated-rules.json` against the
   `fedramp-consolidated-rules` manifest pin (feed `fedramp-20x`, api_poll). On drift: re-fetch the
   complete file, re-pin sha + version, rebuild, and re-run the Phase 26 gates (KSI counts and the
   carry-over ratio are measure-then-pin — re-measure on refresh).
2. Watch `fedramp.gov/schemas/` for a schema filename dated after 2026-06-24 (feed
   `fedramp-schemas`); on a new set, mirror the complete files and update manifest pins.
3. Watch `/rfcs/` for RFC numbers above the last observed (feed `fedramp-rfcs`) and the
   2026-markdown `_sources.json` sha (feed `fedramp-2026-docs`); route dated announcements to
   `anticipated_updates.json` (the `au-fedramp-*` records track the published transition timeline).
