# Changelog

Format follows Keep a Changelog conventions; one entry per shipped phase. Versioning policy:
`CHANGE_MANAGEMENT.md`.

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
- **28-3** — This changelog, `STATE.md` (live status + phase ledger + recovery package),
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
