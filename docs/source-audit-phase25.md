# Phase 25 — full source audit + two-tier broadening

A ground-up re-audit of the canonical-source universe: assume nothing, revisit every
authority, broaden where we search/index/seed, and expand the mapping graph only where a
published crosswalk exists. Scope: all authoritative governing bodies; **two tiers — map
what maps, index the rest**; US-federal-centric plus international majors; seed + ingest +
cross-map. Every finding below was returned by a research agent with a citation and then
re-verified with read-only HTTP.

## Two tiers

| Tier | Meaning | Where it lands |
|---|---|---|
| **mappable** | has a published crosswalk to 800-53 / CSF 2.0 (or a documented 800-53 lineage) | ingested or staged for ingestion; can reach the 800-53 spine |
| **reference** | statute / rule / guidance with no published 800-53 crosswalk | indexed + watched only; never fabricated into mappings |

Feeds now carry `tier` and `jurisdiction`. New feeds are tagged explicitly; existing feeds
default to their authority-derived tier.

## The mapping expansion — OLIR-hub composition (no fabrication)

NIST CSF 2.0 is the crosswalk **hub**: NIST's OLIR program publishes third-party→CSF 2.0
informative references, and the CPRT CSF 2.0 element graphs (already committed) also carry
CSF 2.0→800-53 r5.2.0. Composing the two hops yields third-party→800-53 edges where **every
hop is an authority-published reference** — nothing is guessed.

`spine_loader.load_olir_hub_edges()` composes, from the committed CPRT artifact only, the
OLIR sets that carry a **distinct** control vocabulary and were not already consumed:

| Framework | OLIR set (hop 1) | composed edges |
|---|---|---|
| CIS Controls 8.1 | `CIS-Controls-8.1-to-CSF-v2.0` | ~410 |
| OWASP LLM Top 10 v2.0 | `OWASP-LLM-Top10-v2.0-to-CSF-v2.0` | ~1,166 |
| NIST SSDF v1.1 | `SSDF-Version-1.1-to-CSF-v2.0` | ~294 |

Hop 2 is always `Cybersecurity-Framework-v2.0-to-SP-800-53-Rev-5-2-0`. Each row stores both
OLIR set names (`source_ref_a`, `source_ref_b`), the bridging CSF 2.0 subcategory, and
`basis='olir_hub_composed'` (confidence 0.6, two-hop). CRI Profile v2.0 was **excluded** —
its native ids mirror the CSF structure, so composition would be degenerate.

**Containment.** These live in the dedicated `olir_hub_edges` table and are a query-surface /
on-demand tier — they never enter `framework_projection`, `overlap_matrix`, or
`master_mappings` (mirrors the STIG technology-tier containment). The precomputed matrix stays
120 pairs and the master tiers stay 7. Query: `dbz_query.py olir-hub --coverage | --framework
FW | --native ID`.

The direct CSF 2.0→800-53 and PCI/ISO/171r3/CCM/SCF↔CSF2 references were already ingested in
Phases 2/19/20; this phase does not duplicate them. The Privacy Framework→800-53 direct
crosswalk (in the `csf-pf-to-sp800-53r5` XLSX) is a named ingestion follow-up.

## Recursive crawl-seed / link-graph

`canonical-sources/crawl_seeds.json` + `tools/crawl_seed.py` provide deterministic, offline
candidate expansion of seed roots (`--list`), and `tools/crawl_seed.ps1` runs the
network-heavy live traversal locally (where the managed proxy blocks a host); its JSON is
merged back with `crawl_seed.py --import`. Resolvers: OLIR `.rip` detail-page id-range,
eCFR Versioner titles, Federal Register saved queries, EUR-Lex CELEX, GitHub OSCAL raw.
Nothing auto-ingests — every candidate is a review stub, and anticipatable signals route to
`anticipated_updates.json`.

## Verified machine-readable ingest endpoints (HTTP 200)

- `…/sp/800/53/r5/upd1/final/docs/csf-pf-to-sp800-53r5-mappings.xlsx` — CSF 2.0 & Privacy
  Framework → 800-53 r5.2.0 (the direct crown-jewel; PF portion staged).
- `…/sp/800/53/a/r5/final/docs/sp800-53ar5-assessment-procedures.xlsx` — 800-53A r5.
- `…/sp/800/171/r2/upd1/final/docs/csf-v1-0-to-sp800-171rev2-mapping.xlsx`.
- `ecfr.gov/api/versioner/v1/…`, `federalregister.gov/api/v1/…` (JSON APIs).
- ACSC `ism-oscal` GitHub raw (native OSCAL), `irs.gov/pub/irs-pdf/p1075.pdf`, BSI `dok/c5-en`.

## Verified broken / not-directly-fetchable (indexed, not claimed)

- OLIR **bulk** JSON API + `csf/download?olirids=all` → 404/500 (use the committed CPRT
  graphs + the `.rip` per-reference detail pages instead).
- FedRAMP OSCAL raw baseline paths → 404; `api.github.com` → 403 via the proxy (GSA repo is
  outside the session's GitHub-MCP scope) → **path-discovery-required**.
- CPRT `nudp` JSON REST endpoint retired (the `sp_800_53_5_1_1` path 404s) → 800-53 version
  oracle is the committed OSCAL catalog + CPRT project page.

## Feed-registry repairs (correctness)

Broken URLs repointed (nist-800-53 CPRT, iso-27001 OLIR xlsx, hitrust landing, ny-dfs-500
regulation), mitre-attack STIX moved off the deprecated `mitre/cti` to
`mitre-attack/attack-stix-data`, the 26 landing-less `poll_landing` feeds fixed (10 promoted
to a real landing, 16 config-note watchers → `poll_exempt`), the redundant `csa-aicm-v1.1`
stub aliased, and metadata contradictions reconciled (owasp-top10, owasp-asvs, nist-800-172,
ffiec-cat sunset 2025-08-31, uk-aisi → "AI Security Institute", ISO 42005:2025 published,
india-dpdp Rules 2025).

## Tier-2 staged catalogs (`source_manifest.json → staged_reference_sources`)

CJIS v6.0, IRS Pub 1075, BSI C5, CMS ARS, Canada ITSG-33, Japan ISMAP, Saudi NCA ECC —
registered with a `staged_ingestion` status and no fabricated file/sha. `mappable=true`
(IRS 1075, BSI C5, CMS ARS, ISMAP) carries an 800-53 lineage/crosswalk and is a named
ingestion follow-up; `mappable=false` is reference/index-only.

## Horizon items added

ITSG-33 Rev 5 (2026-03-31), ARC-AMPE (2026-03-04), Privacy Framework 1.1 (2026), SWIFT
CSCF v2026 (~Jul 2026), APRA CPS 230 (materialized 2025-07-01), Chile Ley 21.719 (Dec 2026),
EU CRA reporting (2026-09-11). ISO/IEC 42005:2025 marked materialized.

## Gates

`test_spine` (olir-hub counts / two-ref tracing / containment; crawl-seed determinism),
`validate_spine` check 12 (olir-hub source-tracing + containment), deterministic rebuild ×2,
`health_audit --scan` 100/100, `sync_check`, golden. Schema bumped to 3.11 (`olir_hub_edges`).
