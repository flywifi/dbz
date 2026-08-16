# Quality gates

The release gates every change must pass, and the deterministic scoring model for GRC analysis
output. Precedence statement: **integrity > completeness > convenience** — a smaller, honest
result always beats a fuller, unverifiable one.

## Release gates (source: `changes/CHANGE_MANAGEMENT.md` merge bar; `docs/standards-refresh-runbook.md`)

Every commit passes, in order:

1. Rebuild grc.db **twice, sequentially** → identical `table_digests` (determinism). Digest
   coverage is derived from `sqlite_master` at build time — every content table is digested
   automatically; the only exclusions, each with a reason in `build_db.py`, are SQLite
   internals, FTS5 shadow tables (their source table is digested), and `db_metadata`
   (carries a build timestamp).
2. `cross-mapping/tests/test_spine.py` — unit + containment invariants.
3. `cross-mapping/tests/validate_spine.py` — oracle reconciliation + tier gates.
4. `tools/health_audit.py --scan` and `--full` at 100/100 — run **with build artifacts hidden**
   (the CI condition; a local-only pass is not a pass). The sanctioned way to run this
   condition — and the whole CI step set — is `python3 tools/ci_rehearsal.py` (pre-push).
5. `tools/sync_check.py` — all drift invariants.
6. `skills/health-auditor/tests/run_golden.py` — golden self-test.
7. `cross-mapping/tests/benchmark_oracles.py --check` when engine or mapping data changed.
8. `cross-mapping/tests/run_scenarios.py` — ten pinned end-to-end scenarios (built grc.db).
9. `tools/output_validate.py --selftest` + `cross-mapping/engine/score_output.py --selftest`
   (pre-commit).
10. `tools/secret_scan.py` on the staged diff (pre-commit) — the CI backstop scans commits
    since the policy boundary sha (`changes/CHANGE_MANAGEMENT.md`).

The generated-artifact drift checks (metrics scoreboard, platform export) run inside
`sync_check` (invariants 12–14). CI (`health` workflow) must be green on the pushed sha before
a phase is declared done.

## Regulatory-phase closing gate

Any phase that changes regulatory-currency data — `feed_registry.json`,
`anticipated_updates.json`, `framework_changelog.json`, or regulatory claims in `docs/` —
closes with an adversarial-audit document under `docs/audits/` run against the phase's own
diff. The audit's four passes and the provenance rules it checks are defined in
`regulatory-provenance.md`. Two sections are mandatory and non-substitutable:

- **Adversary output:** the single claim most likely to be wrong, the specific evidence that
  would overturn it, and where that evidence would be found. A pass that cannot name one is
  treated as not run — "least weak" is still an ordering.
- **Residual risk:** which specific claims are most likely still wrong and why. Never an
  all-clear; a clean self-audit is evidence about the audit, not the data.

Obligations are tracked in `docs/audits/INDEX.md`; a phase that creates one adds its row in
the same change.

## Planning gate

A phase begins from a plan conforming to `planning-standard.md`: the seven questions answered
per workstream, every number carrying its probe, every code block already executed read-only
against the real data, and the adversarial check **run** rather than described. A plan whose
disconfirming probe was written but not executed is treated as not checked — the phase-43
finding retracted in phase 44 is the standing example.

## Critical non-overridables

- **A fabricated id is a critical failure.** No composite score, reviewer preference, or
  deadline overrides it (source: `CLAUDE.md` non-negotiables; `tools/output_validate.py` HIGH).
- A publication-hygiene leak (session link, personal email, provider-proprietary id) is equally
  non-overridable (source: `CLAUDE.md` publication hygiene; `tools/health_audit.py`).

## Deterministic output scoring (`cross-mapping/engine/score_output.py`)

Verdicts over analysis output are computed, not vibed. The scorer consumes
`tools/output_validate.py` findings plus optional judge sub-scores (0–5 per dimension).

**Hard-fail first:** any HIGH fabrication or leak finding → verdict **REJECTED** before any
composite arithmetic.

**Dimensions and weights** (must match the scorer header — machine-cross-checked by
`tools/count_truth.py` claim `scorer_weights`):

| Dimension | Weight |
|---|---|
| citation_integrity | 0.30 |
| mapping_accuracy | 0.25 |
| coverage | 0.15 |
| source_currency | 0.10 |
| scope_correctness | 0.10 |
| honesty_about_gaps | 0.10 |

**Named thresholds** (all booleans reported in the output):
`no_dimension_below_2` · `citation_integrity_at_least_4` · `composite_at_least_3_5`

**Verdict bands:** all three true → **APPROVED**; composite ≥ 3.5 with one other threshold
false → **CONDITIONAL** (human review required); otherwise → **REJECTED**.

Weights and bands change only via a scored PATCH entry in `changes/CHANGELOG.md`.
