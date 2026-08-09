# Changelog

Format follows Keep a Changelog conventions; one entry per shipped phase. Versioning policy:
`CHANGE_MANAGEMENT.md`.

## [0.5.1] — 2026-08-09 (phase 34 — remediation of the phase-33 audit findings)

Phase 33 was a read-only independent audit of the phase-32 series (8 commits / 37 files):
0 CRITICAL, 1 HIGH, 4 MED, 5 LOW. Every regulatory claim, pin, and count held; this release
fixes the defects it did find. Audit record: the phase-33 log; findings referenced by id.

### Fixed
- **B-1 (HIGH)** (`49aedce`) — master-surface CMMC alias resolution. `master --framework-a
  cmmc` returned 0 rows while 105 SOC 2 × NIST SP 800-171 r2 master pairs existed: the
  `framework_labels` authority maps an alias to ONE canonical, but CMMC's program reality
  spans two labels (Level 2 assesses against 800-171 r2 per the May-2024 class deviation).
  `_MASTER_FW_GROUPS` + `_master_fw_set()` fan the alias out across both labels in pair and
  control modes, rows keep their true labels, and the header names the fan-out and its
  basis. Scenario 11 pins the answer (measured 105, band ±15%) plus the presence of
  r2-labeled rows. The dead alias entries phase 32 added to the legacy `_resolve_fw` map
  (which serves only `unified_mappings`-backed commands) are removed.
- **C-1 / C-6 / C-2 (MED, LOW, LOW)** (`38b69f0`) — horizon record repairs: `au-iso-15408`'s
  empty provenance URL now cites the attempted portal hop (with `source_urls`/`detection`
  filled); `au-fedramp-class-a`'s baseline version reflects the opened pipeline instead of
  "pre-pipeline" on a materialized record; `au-eu-ai-act`'s artifact names the obligations
  milestone its closing verbatim proves, with the acts-side evidence recorded.
- **G-1 (MED)** (`cd1449c`) — the audit-harness gap that let the empty URL ship is now
  mechanized: `load_anticipated_updates()` hard-fails on a non-http provenance URL in every
  terminal state, and `regulatory-provenance.md` §2 states that DEAD_END exempts content
  matching, never the citation. Validation tightening only — schema stays 3.14.
- **F-2 (MED, pre-existing)** (`28ff354`) — the monthly `standards-watch` workflow failed on
  every fresh checkout (`FileNotFoundError` on the generated catalog) and, once past that,
  would have built a silently degraded database (no OSCAL cache → `oscal_structural`
  controls=None, 0 objectives). Both build products are now produced on the runner. The
  failure and the fix were reproduced locally under hidden artifacts first;
  `tools/ci_rehearsal.py --standards-watch` makes that second fresh-checkout mode testable.
- **C-4 / G-2 / B-2 / NOTE-D3 / F-1 / A1 / E2** (`74f022a`) — record-keeping: the deliberate
  drop of `chg-dfars-clause-renumbering-2026` is recorded with its provenance-floor reason;
  the phase-32 audit doc's coverage sentence is corrected (75 of 76 fetched) and carries the
  phase-33 follow-up; the secret-scan docstring enumerates all three allowlisted prefixes;
  the ODP baseline pins the extractor version proven to reproduce it; the runbook gains the
  learned phase-hygiene rules (message length, anchor ordering, recording scope drops) and
  the rehearsal's coverage limit; three stale date labels now match their commits.

## [0.5.0] — 2026-08-09 (phase 32 — CMMC + HIPAA regulatory absorption, provenance hardening)
### Added
- **32-0** (`1cf7aa3`) — `protocol-layer/regulatory-provenance.md`: claim provenance blocks
  (URL + retrieved_at + verbatim + support label), terminal-state vocabulary, citation-loop
  escape, mutation-check intake, an 11-item GRC domain-trap list, recall/injection rules, and
  a recorded non-adoption boundary (decomposed from the maintainer's research-provenance
  skill v1.5.2 — 7 pieces adopted, the rest skipped with reasons). `quality-gates.md` gains
  a permanent regulatory-phase closing gate (adversarial audit with mandatory adversary
  output + residual risk).
- **32-2** (`c1f5f3b`) — CMMC posture absorbed on origin evidence: six suspension-aware
  horizon records (Phase 2 suspended 2026-07-13; RFI closing 2026-08-14; task-force report
  window; Phases 3/4 frozen; 171r3 transition signal), `au-nist-800-172` closed as
  materialized, `dfars-cyber` rescheduled high-priority with a clause-accurate label, new
  `cmmc-32cfr-170` feed (feeds 160→161), two FR agency slugs fixed, suspension + ODP memo
  PDFs sha-pinned. DB schema 3.14: enum-enforced provenance columns on
  `anticipated_updates`; eCFR loader gains Part 170 + a heading-extraction fix.
  *Deliberate scope drop:* the planned `chg-dfars-clause-renumbering-2026` changelog entry
  was NOT written — the Feb-2026 class-deviation memos stayed bot-walled at acq.osd.mil, so
  under the provenance floor there was nothing citable to record. The renumbering is carried
  in the `dfars-cyber` feed label as deviation clauses (not CFR changes); the entry gets
  written when a DPCAP memo is read at origin.
- **32-3** (`1a8ca33`, allowlist fix `4af0bf9`) — CMMC ODP transition baseline frozen per
  the user gate (WAIT for the task-force outcome): diff-ready memo text extraction, full
  32 CFR 170 XML as of 2026-08-01, comparison procedure in `docs/cmmc-odp-baseline.md`.
- **32-4** (`075dc74`) — HIPAA horizon refresh: `au-hipaa` carries the OMB 202510 July-2027
  projection at low confidence/CONTESTED, the `hipaa` feed records the NPRM's full identity
  (90 FR 898, RIN 0945-AA22, docket HHS-OCR-2024-0020, 4,747 comments), and
  `docs/hipaa-security-rule-transition.md` enumerates the 18 proposed items with the repo
  trigger map. Announcement pipeline slug repairs (HHS/CISA/NYDFS), 11 false positives
  pruned, diverged analyzer xlsx resynced, sync invariant 15 (skill-asset hash guard).
- **32-1** (`670d9a2`) — Provenance backfill: all 68 legacy horizon records verified at
  their primary sources and stamped (56 WELL_SUPPORTED/ORIGIN; unreachable primaries
  recorded THIN/DEAD_END with the obstacle named). Ten drift repairs, including a
  two-year-stale IR 8477 watch, the OWASP LLM Top 10 2026 edition, the EU AI Act GPAI
  milestone, Bill C-27's lapse, and the passed CIRCIA final-rule window.
- **32-5/6** — docs/counts sync (this entry), VERSION 0.5.0, and the closing adversarial
  audit `docs/audits/phase-32-adversarial-audit.md` required by the new quality gate.
### Fixed
- Secret-scan allowlist (`4af0bf9`): verbatim regulatory-text paths (CFR JSON, pinned DoD
  documents) join the reasoned prefix allowlist after the 32 CFR 170 org-mailbox finding
  turned CI red on `c1f5f3b`/`1a8ca33`; green from `4af0bf9`.

## [0.4.1] — 2026-07-18 (phase 31 — 48-hour-audit remediation)
### Fixed
- **31-3** (`d8ac868`) — `tools/ci_rehearsal.py`: one-command local reproduction of the CI
  condition (artifact stash + verbatim health-workflow steps + guaranteed restoration +
  workflow drift warning); named in the merge bar as the mandated pre-push step. Closes the
  audit's FINDING-3 failure class (fresh-checkout divergence).
- **31-2** (`9764f7c`) — Determinism-digest coverage derived from `sqlite_master` (40 content
  tables, 22 newly covered, all verified deterministic; reasoned exclusions only; legacy
  digests byte-identical). Closes FINDING-2 and eliminates its hand-kept-list mechanism.
- **31-1** (`54141d5`) — Prefix-scoped, reasoned secret-scan allowlist for the
  output-validator fixture directory; selftest proves the allowlist is path-scoped, never
  pattern-weakening. Closes FINDING-1 (full-range scans now clean).

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
