# Horizon scanning — anticipated updates

The keep-current pipeline (`framework_monitor` / `announcement_monitor`) catches changes that
**already happened**. Horizon scanning covers changes that are **expected to happen**, so a
scheduled or signaled revision is watched-for and never missed or overlooked. It is the answer to
"CSA published the CCM v4.1 catalog but the mappings say *not available yet*" — we record the
expectation and actively watch for it, rather than statically deferring.

## The registry — `canonical-sources/anticipated_updates.json`

One structured record per anticipated artifact. Fields:

| Field | Meaning |
|---|---|
| `id` / `feed_id` | record id (`au-…`) / the feed_registry entry it tracks |
| `authority` / `artifact` / `current_version` | who publishes it / what's expected / the baseline in force |
| `expected_type` | major_rev · minor_rel · amendment · mapping_dataset · points_of_focus · quarterly_bundle |
| `lifecycle_stage` | normalized authority stage: ipd/fpd/final · wd/cd/dis/fdis/is · advisory_pending · best_practice_until · catalog_out_mappings_pending |
| `expected_window` | `{earliest, latest, basis}` **or** the string `"no_fixed_date"` — **never a fabricated date** |
| `confidence` | high (fixed date/cadence) · med (window) · low (signaled, no date) |
| `trigger_signal` / `detection` | the observable event that proves it landed / `{url, method, match}` to poll |
| `poll_frequency` / `source_urls` | cadence / authority URLs |
| `dependent_of` | models the CSA "catalog-first, mappings-later" dependency |
| `status` | watching · draft_observed · materialized · superseded |
| `escalate_after_days` / `last_checked` / `last_change_detected` | overdue grace / audit timestamps |
| `provenance` | schema 1.1: `{primary_source_url, retrieved_at, verbatim, support, terminal_state}` per `protocol-layer/regulatory-provenance.md` |

## Provenance (schema 1.1)

Since phase 32 every record carries a claim provenance block: the issuing authority's own URL,
the retrieval date, a verbatim snippet stating the claim, a support label
(`WELL_SUPPORTED` · `CONTESTED` · `THIN` · `UNSUPPORTED`) and a terminal state (`ORIGIN` ·
`ORIGIN_RECOVERED` · `DEAD_END` · `ORPHAN_CONFIRMED` · `CIRCULAR_UNRESOLVED`). The build
(`load_anticipated_updates`) hard-fails on out-of-vocabulary labels. All 76 records were
origin-verified or honestly degraded in the phase-32 backfill — unreachable primaries are
recorded `THIN`/`DEAD_END` with the obstacle named, never as fabricated confirmations; the
backfill also repaired ten records whose claims had drifted from their authorities' pages
(stale versions, a two-year-stale "not yet released" watch, a lapsed bill, a passed
final-rule window). Rules of evidence: `protocol-layer/regulatory-provenance.md`.

The table `anticipated_updates` in `grc.db` holds the static records (deterministic); the dynamic
overdue/materialized state is computed at query time by `horizon_monitor.py`.

## The watcher — `cross-mapping/engine/horizon_monitor.py`

- `--list` / `--upcoming N` — the horizon, nearest expected window first.
- `--overdue` — **the core guarantee**: records past their window (`now > latest + escalate_after_days`)
  or undated-but-due-for-review are surfaced as `OVERDUE` / `DUE_REVIEW` so the source is
  re-investigated and a landed update is never silently missed. Undated low-confidence "not
  announced" items stay passively `watching` (they'd otherwise flood the report); undated med/high
  or staged items (e.g. the CCM v4.1 flagship) are surfaced for periodic re-check.
- `--check` — best-effort, offline-safe materialization poll of each watching record's detection URL.
- `--summary` — one-line JSON counts by state (used by `standards_refresh`).
- `--as-of YYYY-MM-DD` — override "today" (deterministic for tests).

Query surface: `dbz_query.py horizon --upcoming N | --overdue | --materialized`. Pipeline: a
`horizon` section in `standards_refresh.py --check`. **Materialized items still route through the
human-reviewed loader — the horizon never auto-ingests.**

## Auto-seeding from a crawl

When a source traversal hits an **anticipatable signal**, add/refresh a record so every future
crawl feeds the horizon:

- a "not available yet" placeholder (CSA catalog-first, mappings-later) → `catalog_out_mappings_pending`;
- a draft/IPD/FPD status, an ISO DIS ballot, a numbered HITRUST advisory → `draft_observed`;
- a transition-timeline date, a PCI "best practice until `<date>`, then mandatory" clause → a dated window.

Worked example (implemented): the CCM v4.1 traversal seeded `au-csa-ccm` — authority CSA, artifact
"CCM v4.1 cross-framework mappings", `no_fixed_date`, detection = the CSA artifact page +
CloudSecurityAlliance GitHub releases + the v4.1 mappings sheet no longer reading "not available yet".

## Per-authority signal catalog (what to poll)

| Authority | Lifecycle signal | Pollable |
|---|---|---|
| **NIST CSRC** | IPD → FPD → Final → Withdrawn; real-time comment site | `csrc.nist.gov/CSRC/media/feeds/pubs/drafts-open-for-comment.{json,xml}`; versioned `/pubs/sp/800/53/r5/ipd\|fpd\|final` |
| **DISA (CCI List only)** | fixed quarterly (Jan/Apr/Jul/Oct) | announcement feed + the versioned `U_CCI_List.zip` `<version>`. **STIGs are out of scope** — no STIG record, no STIG update. |
| **CSA** | catalog-first, mappings-later; transition-timeline blog | artifact pages ("not available yet" state) + `github.com/CloudSecurityAlliance` releases |
| **ISO/IEC** | stage codes; **DIS (40) = imminent**; ~5-yr systematic review; amendments | iso.org standard-page stage badge |
| **PCI SSC** | future-dated "best practice until `<date>`" clauses | blog + versioned document library |
| **HITRUST** | ~quarterly; numbered HAA advisories with sunset deadlines | `hitrustalliance.net/advisories` |
| **AICPA** | low cadence; points-of-focus refreshes | AICPA resources page |

## Gates
`validate_spine` check 11: every record is well-formed — status/confidence in enum, detection
present, `expected_window` is `no_fixed_date` or real ISO dates (**no fabricated dates**),
`dependent_of` resolves. `test_spine`: the overdue/future/undated/materialized `classify` logic +
the CCM v4.1 flagship's presence. The table is in `table_digests` (deterministic build).
