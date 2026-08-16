# Change management

## Versioning policy (`VERSION`)
- **MAJOR** — a breaking change to `cross-mapping/schema/enhanced_framework_schema.json`, to a
  grc.db table contract that `dbz_query.py` outputs depend on, or to the query output shape
  itself (fields removed/renamed).
- **MINOR** — a new framework, loader, table, atom, feed tier, or query surface; additive
  schema-version bumps (e.g. a new derived column).
- **PATCH** — source re-pins, data refreshes, doc fixes, threshold re-pins.

`VERSION` 0.1.0 → 0.2.0 records the MINOR accumulation of phases 19–27 (master surface, STIG,
CCI, horizon, OLIR-hub, FedRAMP KSI layers) plus the phase-28 verification tooling.

## Merge bar
Every commit passes the full gate battery: double build with identical table digests,
`test_spine.py`, `validate_spine.py`, `health_audit.py --scan` and `--full` at 100/100 **with
build artifacts hidden** (the CI condition), `sync_check.py` (14 invariants, including the
export/scoreboard/registry-writer drift checks), the golden self-test, the pre-commit selftests
(`output_validate.py --selftest`, `score_output.py --selftest`, staged-diff `secret_scan.py`),
and — when the engine or mapping data changed — `benchmark_oracles.py --check` plus the
ten-scenario battery (`cross-mapping/tests/run_scenarios.py`). Before every push, rehearse the
CI condition with `python3 tools/ci_rehearsal.py` (mirrors health.yml with build artifacts
hidden; guaranteed restoration). The authoritative release-gate list lives in
`protocol-layer/quality-gates.md`. CI (`health` workflow) must be green on the pushed sha
before a phase is declared done.

## Phase close-out checklist (added phase 42 — both prior misses were archaeology-discovered)
Run at every phase close, in this order; the first item is the one that was missed twice:
1. **Audit gate:** did this phase touch `feed_registry.json`, `anticipated_updates.json`,
   `framework_changelog.json`, or regulatory claims in `docs/`? If yes, the closing
   adversarial-audit doc must exist under `docs/audits/` and its row must be added to
   `docs/audits/INDEX.md` in the same change.
2. Schema bumps only via `tools/bump_schema.py` (never by hand).
3. `changes/CHANGELOG.md` entry + `STATE.md` phase row.
4. Ledger anchor in `ledger/snapshots.json` at a **green** sha (cut the pre-phase anchor
   before the first data-touching commit).
5. `tools/metrics.py` regen + `tools/count_truth.py` green.
6. Push through the installed pre-push hook (rehearsal runs mechanically).
7. CI verdict read via the GitHub MCP tools or `tools/ci_status.py` — never raw curl.

## Secret-scan policy boundary
`policy_boundary_sha: c3192c8` — the CI secret-scan backstop
(`tools/secret_scan.py --range c3192c8..HEAD` in `health.yml`) scans every commit AFTER this
sha. History at or before the boundary was reviewed when the policy landed and is not
re-litigated on every run; the pre-commit hook scans every staged diff going forward.

## Rollback procedure
Known-good anchors live in `ledger/snapshots.json` (one per phase, `known_good: true` means the
full gate battery was green at that sha).

- Restore specific paths: `git checkout <sha> -- <paths>`, rebuild, run the gate battery.
- Roll a branch back: create a new branch from the anchor (`git branch rescue <sha>`), never
  force-push shared history.
- After any rollback, re-run the full gate battery and record the action in
  `changes/CHANGELOG.md`.
