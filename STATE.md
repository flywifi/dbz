# STATE — live status of the GRC cross-mapping engine

## What this repo is
A GRC compliance cross-mapping engine: every framework projected onto the NIST 800-53 r5 spine,
queried through one unified surface. Full picture: [README.md](README.md) and
[docs/cross-mapping-architecture.md](docs/cross-mapping-architecture.md).

## Live status
- **DB schema:** 3.15 (adds `edge_semantic` on `master_mappings` — what an edge CLAIMS; 3.14 added regulatory-provenance columns on `anticipated_updates`) (`grc.db`, deterministic build, double-build digest check)
- **Gate battery:** rebuild ×2 identical digests · `test_spine.py` · `validate_spine.py` ·
  `health_audit.py --scan/--full` 100/100 (including the artifacts-hidden CI condition) ·
  `sync_check.py` (15 invariants) · golden self-test · `benchmark_oracles.py --check` ·
  eleven-scenario battery (`run_scenarios.py`) · alias contract (`test_alias_contract.py`) ·
  pre-commit selftests (output validator, scorer, secret scan) — all green as of 2026-08-10 (incl. phase-35 alias correctness; rehearse CI pre-push with tools/ci_rehearsal.py). Authority list: `protocol-layer/quality-gates.md`.
- **CI:** `health` workflow green on every push; `standards-watch` (monthly) runs the drift
  check + a fresh-build oracle benchmark regression check.
- **Accuracy record:** see [docs/BENCHMARK.md](docs/BENCHMARK.md) (measured, pinned).
- **Doc numbers:** machine-checked against the data by `tools/count_truth.py`
  (registry: `canonical-sources/doc_claims.json`); drift blocks the health audit.

## Phase ledger
| # | Phase | Commit | Date | Outcome |
|---|---|---|---|---|
| 19 | Master mapping database | `d8c0d15` | 2026-07-03 | Private-sector audits merged into one master surface (60 stored pairs; any-to-any answered on demand by overlap) |
| 20 | SCF + CCM spine projection | `eabfc21` | 2026-07-04 | Meta-frameworks join via owner_stated tier |
| 21 | STIG application layer | `e6449ab` | 2026-07-04 | 383 benchmarks / 19,667 rules as CCI application evidence |
| 22 | Full CCI dictionary | `98eea12` | 2026-07-04 | All 5,137 DISA CCIs + multi-source corroboration |
| 23 | Standards-currency refresh | `6aeac84` | 2026-07-06 | Monitor repair + 800-53 r5.2.0 re-pin |
| 24 | Horizon scanning | `005b745` | 2026-07-07 | Anticipated-updates tracker (future revisions, no fabricated dates) |
| 25 | Source audit + broadening | `4f9fff1`, `651ad4c` | 2026-07-07/10 | Source universe tiered + OLIR-hub composed edges; verification corrections |
| 26 | FedRAMP Consolidated Rules 2026 | `f27f088` | 2026-07-10 | KSI confirmation layer, complete canonical dataset, version-transition framing |
| 27 | Unified README + CI fix | `1007fd8`, `8e06bb8` | 2026-07-14 | Docs rewritten around the unified graph; build-artifact reference exemption clears CI |
| 28-1 | Oracle accuracy benchmark | `4c81aa8` | 2026-07-17 | Measured P/R vs production oracles, pinned regression thresholds, BENCHMARK.md |
| 28-2 | Count-truth + URL provenance | `2be8088` | 2026-07-17 | Doc numbers machine-checked (caught stale framework count); URL hosts registry-declared |
| 28-3 | Durable state + rollback | `b6a9f84` | 2026-07-17 | STATE/CHANGELOG/CHANGE_MANAGEMENT + known-good snapshot anchors; VERSION 0.2.0 |
| 28-4 | fetchkit shared fetch layer | `70e807e` | 2026-07-17 | Rate governor + conditional-GET cache + labeled Wayback fallback; monitors adopted |
| 28-5 | Output validator | `650aa66` | 2026-07-17 | Mechanical fabrication/unsourced/tier/leak gate for analysis deliverables |
| 29-1 | Context overlays | `ae0f772` | 2026-07-17 | Industry/jurisdiction/client presentation profiles + --overlay with disclosed suppression |
| 29-2 | Multi-platform export | `ea917cd` | 2026-07-17 | Generated OpenAI-function schemas for the 6 core operations, drift-guarded (sync invariant 12) |
| 29-3 | Protocol layer + scorer | `d5200d9` | 2026-07-18 | Four authority protocols (cited to existing rules) + hard-fail-first deterministic verdicts |
| 29-4 | Evidence-state ladder | `8ef71f2` | 2026-07-18 | Schema 3.13: derived corroboration state on every master edge + --evidence-state filter + check 14 |
| 30-1/2/3 | Metrics + scenarios + registry IO | `5eaa48f` | 2026-07-18 | Generated scoreboard; ten pinned e2e scenarios in CI; single-writer registries + sha baselines |
| 30-4 | Crawl citation graph | `c3192c8` | 2026-07-18 | Candidate provenance, --accept review stubs, blocked-is-not-gone pruning |
| 30-5 | Hygiene extras | `d2a5a99` | 2026-07-18 | Secret scan + CI backstop, data-at-rest rules, URL provenance blocking, persona audit |
| 31-1 | Secret-scan fixture allowlist | `54141d5` | 2026-07-18 | Full-range scans clean; allowlist path-scoped and selftest-proven |
| 31-2 | Digest coverage by derivation | `9764f7c` | 2026-07-18 | All 40 content tables in the determinism gate, exclusions reasoned |
| 31-3 | CI rehearsal harness | `d8ac868` | 2026-07-18 | One command mirrors CI locally with guaranteed artifact restoration |
| 32-0 | Regulatory-provenance protocol | `1cf7aa3` | 2026-08-08 | Claim provenance blocks, terminal states, loop escape, mutation check, GRC trap list, closing-audit gate |
| 32-2 | CMMC absorption | `c1f5f3b` | 2026-08-08 | Six suspension-aware horizon records (Phase 2 suspended 2026-07-13, RFI, task force), dfars-cyber rescheduled, 32 CFR 170 feed + eCFR part, schema 3.14 |
| 32-3 | ODP baseline freeze | `1a8ca33`, `4af0bf9` | 2026-08-08 | 2025 ODP memo + full 32 CFR 170 text pinned offline with a diff procedure; load deferred per user gate pending the reform review |
| 32-4 | HIPAA refresh | `075dc74` | 2026-08-08 | au-hipaa → July-2027/CONTESTED, NPRM identity + 18-item transition doc, FR slug repairs, 11 false positives pruned, sync invariant 15 |
| 32-1 | Horizon provenance backfill | `670d9a2` | 2026-08-09 | All 76 records origin-verified or honestly degraded; ten drift repairs; unreachable primaries recorded THIN/DEAD_END |
| 32-5 | Docs, counts, VERSION 0.5.0 | `e9725fe` | 2026-08-09 | Currency rows, horizon-scanning provenance section, runbook update, changelog + anchors |
| 32-6 | Closing adversarial audit | see `changes/CHANGELOG.md` | 2026-08-09 | `docs/audits/phase-32-adversarial-audit.md`: 75 of 76 URLs re-fetched (one empty, later repaired), pins re-hashed, 3 findings fixed, adversary output + residual risk |
| 33 | Independent 24-hour change audit (read-only) | `b7e0369` (audited head) | 2026-08-09 | 7 passes over the phase-32 series: 0 CRITICAL / 1 HIGH / 4 MED / 5 LOW; no repo changes made |
| 34 | Audit remediation | `49aedce`, `38b69f0`, `cd1449c`, `74f022a`, `28ff354` | 2026-08-09 | CMMC alias fan-out + scenario 11, three record repairs, build-time URL validation, standards-watch fresh-checkout fix + rehearsal mode, record-keeping closures |
| 35 | Alias correctness + carried-over regulatory items | `ae99dd7`, `c84f509`, `7737b26`, `55ffa93`, `3399a48`, `1b7b8f3` | 2026-08-10 | One alias authority + contract test (the csf/fedramp/nist-csf class), sibling disclosure, the phase-34 audit, FedRAMP re-pin, 18 HIPAA verbatims, two overdue records resolved |

Phases 1–18 built the foundations (catalog ingestion, ER engine, spine normalization, CCI/ODP
bridge, consensus detection, publication hygiene, health auditor); their commits precede
`d8c0d15` in `git log` and their outcomes are documented throughout `docs/`.

## Next planned work
- Candidate UX backlog from `docs/persona-audit.md`: a gap-list convenience on overlap, a
  validated brief output format, inline voter breakdown on consensus edges. Ongoing:
  standards-currency refresh cadence per `docs/standards-refresh-runbook.md`.

## Recovery package (fresh clone → working state)
1. Read `CLAUDE.md` (conventions) + this file (state) + `changes/CHANGELOG.md` (history).
2. `pip install -r requirements.txt`, then `python3 cross-mapping/engine/build_db.py`.
3. Run the gate battery (see Live status above; commands in
   `docs/standards-refresh-runbook.md`).
4. Rollback anchors: `ledger/snapshots.json` (known-good shas per phase); procedure in
   `changes/CHANGE_MANAGEMENT.md`.
