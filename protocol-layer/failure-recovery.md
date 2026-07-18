# Failure recovery

What to do when monitors fail, sources vanish, or a shipped change must be undone. Formalizes
existing machinery; each rule cites its home.

## Monitor failure classes (source: `tools/standards_refresh.py`, `docs/standards-refresh-runbook.md`)

Each feed classifies per run: `current | registry_stale | artifact_stale | licensed_pinned |
metadata_only | on_demand | check_failed`. Network failures degrade to `check_failed` with exit
0 — the drift report is the deliverable; CI surfaces failures via the standards-drift issue.
A feed unchecked for >90 days is a health-audit warning (`check_feed_staleness`).

## Fetch failure ladder (source: `cross-mapping/engine/fetchkit.py`)

1. Per-host pacing + conditional GET (most repeat checks are 304s).
2. Circuit breaker: 4 consecutive 403/429/503 → 15-minute cooldown — back off, never hammer.
3. Hard failure → **labeled** Wayback snapshot (`source="wayback"` + `snapshot_ts`). The label
   is mandatory downstream; an archive copy never updates currency fields, and currency polls
   run live-only. A fetch-blocked source is **blocked, not gone** — do not prune or mark a
   source removed because this environment cannot reach it.

## Rollback (source: `ledger/snapshots.json`, `changes/CHANGE_MANAGEMENT.md`)

- Known-good anchors: one sha per shipped phase, `known_good=true` = gate battery was green.
- Restore paths: `git checkout <sha> -- <paths>`, rebuild, re-run the full gate battery.
- Never force-push shared history; record every rollback in `changes/CHANGELOG.md`.

## Data-corruption guard (source: `changes/CHANGE_MANAGEMENT.md`, build determinism)

`grc.db` is a build artifact — never hand-edited, always regenerable from canonical sources.
Concurrent `build_db.py` runs race and corrupt the DB: build **sequentially only**. A digest
mismatch between two sequential builds is a stop-the-line failure.
