# feed-poller — Maintainer Notes

## Non-Negotiables

- Never fabricate version strings or change detection results — `latest_detected` must come from the live check or be `null` if unreachable
- `changed` must be a strict equality check between `current_version` and `latest_detected`; never guess
- `human_review_required` must always be `true`
- For `draft_status: "retired"` entries, return the entry data with `changed: false` — retired frameworks do not change

## Known Failure Modes

- Unknown framework_id: not present in feed_registry — return `{error: "framework not found in feed_registry"}`
- Network failure during poll: return `latest_detected: null`, `changed: false`, and include `_note: "poll failed; result may be stale"`
- `github_release` strategy requires GitHub API access; rate-limited without a token in high-volume use
- `rss_feed` entries may have stale `current_version` if announcement_monitor.py has not been run recently

## Regression Cases

See `evals/evals.json`:
- pass-01: known stable framework returns `changed: false` with valid version string
- fail-01: unknown framework_id returns error, not fabricated version data
- edge-01: retired framework returns `changed: false` with `draft_status: "retired"`
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
