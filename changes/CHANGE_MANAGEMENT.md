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
build artifacts hidden** (the CI condition), `sync_check.py`, the golden self-test, and
`benchmark_oracles.py --check` when the engine or mapping data changed. CI (`health` workflow)
must be green on the pushed sha before a phase is declared done.

## Rollback procedure
Known-good anchors live in `ledger/snapshots.json` (one per phase, `known_good: true` means the
full gate battery was green at that sha).

- Restore specific paths: `git checkout <sha> -- <paths>`, rebuild, run the gate battery.
- Roll a branch back: create a new branch from the anchor (`git branch rescue <sha>`), never
  force-push shared history.
- After any rollback, re-run the full gate battery and record the action in
  `changes/CHANGELOG.md`.
