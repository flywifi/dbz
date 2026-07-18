# Changelog

Format follows Keep a Changelog conventions; one entry per shipped phase. Versioning policy:
`CHANGE_MANAGEMENT.md`.

## [0.4.0] — 2026-07-18 (phase 30 — hardening)
### Fixed
- **docs-sync sweep** (`861bb09`) — internal documentation brought fully in sync with the
  phase 28–30 additions: README doc table, runbook/quality-gates/STATE/merge-bar gate-battery
  descriptions, sync_check docstring (14 invariants), skill MAINTAINER post-step notes, and
  atom input schemas for the new evidence-state/overlay flags (export regenerated).
### Added
- **30-5** (`d2a5a99`) — Staged-diff secret scan + CI backstop with a recorded policy boundary;
  fail-closed data-at-rest placement rules; URL provenance promoted to blocking;
  `docs/persona-audit.md` (three-persona UX gap audit).
- **30-4** (`c3192c8`) — Crawl-seed citation graph: `parent_source_id` on every candidate,
  `--accept` review stubs in `crawl_candidates.json`, `--prune-report` with blocked-is-not-gone
  protection.
- **30-1/2/3** (`5eaa48f`) — `tools/metrics.py` -> generated `docs/METRICS.md` (sync invariant
  13); ten-scenario pinned end-to-end battery in the standards-watch build; single-writer
  `tools/registry_io.py` (invariant 14) + `tools/registry_currency.py` sha baselines.

## [0.3.0] — 2026-07-18 (phase 29)
### Added
- **29-4** (`8ef71f2`) — Evidence-state ladder on `master_mappings` (schema **3.13**): derived
  corroboration state per edge (`oracle_confirmed` / `cross_validated` / `columns_aligned` /
  `asserted_by_source`), `--evidence-state` filter, validate_spine check 14. MINOR (additive
  schema bump); containment invariants unchanged.
- **29-3** (`d5200d9`) — `protocol-layer/` (evidence standards, conflict protocol, quality
  gates, failure recovery — each rule cited to where it already lived) +
  `cross-mapping/engine/score_output.py` deterministic hard-fail-first verdicts; scorer weights
  machine-cross-checked between doc and code.
- **29-2** (`ea917cd`) — `implementation/gpt/api/` generated OpenAI-function schemas for the six
  core operations + `tools/export_openai.py`; drift-guarded (sync_check invariant 12); scope
  recorded as contracts-not-hosted-service.
- **29-1** (`ae0f772`) — Context overlays (`canonical-sources/overlays/` + resolver +
  `--overlay` on master/overlap/scope/search) with always-disclosed suppression counts.

## [0.2.0] — 2026-07-17
### Added
- **28-2** (`2be8088`) — Machine-checked doc numbers (`tools/count_truth.py` +
  `canonical-sources/doc_claims.json`; drift blocks the health audit) and URL-host provenance
  for code literals (warning severity, `tools/url-allowlist.json`). The first run caught a
  stale master-surface framework count (23 → 35) in README and the architecture doc.
- **28-1** (`4c81aa8`) — Measured accuracy benchmark against the production oracle crosswalks
  (`cross-mapping/tests/benchmark_oracles.py`, `docs/BENCHMARK.md`): ER-level P/R/F1 plus
  spine-level oracle coverage / corroboration rate, measure-then-pin regression thresholds,
  and a fresh-build CI check in the standards-watch workflow.
- **28-5** (`650aa66`) — Deterministic output validator (`tools/output_validate.py`):
  id-reality vs the catalog, unsourced-number and overconfident-tier checks, reused leak
  patterns; fixture selftest in pre-commit; advisory post-step notes in the analyzer and
  orchestrator skills.
- **28-4** (`70e807e`) — `fetchkit` shared fetch layer (per-host rate governing, circuit
  breaker, conditional-GET + sha cache, always-labeled Wayback fallback) adopted by the
  framework monitor and the standards-refresh fetch stage; offline unit tests.
- **28-3** (`b6a9f84`) — This changelog, `STATE.md` (live status + phase ledger + recovery package),
  `changes/CHANGE_MANAGEMENT.md` (versioning + merge bar + rollback), and
  `ledger/snapshots.json` (known-good rollback anchors). `VERSION` 0.1.0 → 0.2.0.

## [0.1.x] — 2026-07-03 … 2026-07-14 (phases 19–27)
- **27** (`1007fd8`, `8e06bb8`) — README/architecture rewritten around the unified graph;
  health-audit build-artifact reference exemption fixed the failing CI check.
- **26** (`f27f088`) — FedRAMP Consolidated Rules 2026 as a contained confirmation layer:
  complete canonical dataset + 11 schemas + narrative corpus; 46 KSIs with FedRAMP's own 373
  KSI→800-53 edges; version-transition framing (spine unchanged).
- **25** (`4f9fff1`, `651ad4c`) — Source universe audit + tiered broadening; OLIR-hub composed
  edges (1,870); verification corrections from an adversarial review.
- **24** (`005b745`) — Horizon scanning: 70 anticipated-revision records, no fabricated dates.
- **23** (`6aeac84`) — Standards-currency refresh: monitor repair, 800-53 r5.2.0 re-pin.
- **22** (`98eea12`) — Full DISA CCI dictionary (5,137) with multi-source corroboration.
- **21** (`e6449ab`) — STIG application layer: 383 benchmarks / 19,667 rules as CCI evidence.
- **20** (`eabfc21`) — SCF + CCM projected onto the spine (owner_stated tier).
- **19** (`d8c0d15`) — Master mapping database: private-sector audits merged into one
  any-to-any surface with the 7-tier provenance vocabulary.
- Phases 1–18: catalog ingestion, ER overlap engine, spine normalization, CCI/ODP bridge,
  consensus detection, publication hygiene, health auditor + golden sets (see `docs/`).
