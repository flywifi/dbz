# MAINTAINER — framework-update-check

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`framework-update-check` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Both signal prongs (file-level `framework_monitor.py` + announcement `announcement_monitor.py`) must run before reporting a result — one prong alone is not sufficient.
- `human_review_required: true` in every output — both monitor signals are advisory, never definitive.
- Never claims a framework has definitively changed; uses "likely changed" or "change signal detected."
- Never triggers source file downloads or `source_manifest.json` updates — this atom is signal-only.
- The `change_type` vocabulary is fixed: major_revision, minor_update, draft_release, public_comment, new_framework, retired, informational.

## Known failure modes
- **False positives on informational announcements**: a blog post mentioning a framework is not a version change. Always check for `change_type: "major_revision"` or `"minor_update"` before setting `action_required`.
- **Scope creep**: being asked to download the updated file or re-run `build_db.py`. Refuse — those are human-confirmed pipeline steps.
- **Stale announcements_feed.json**: if the file hasn't been regenerated within 30 days, the signal is stale. Emit a warning in output.
- **CISA RSS deprecated (May 2025)**: CISA feeds use GitHub mirror (`cisagov/kev-data`) now — do not attempt to fetch deprecated `www.cisa.gov/sites/default/files/feeds/alerts.xml`.

## Fragile fallbacks that must not become defaults
- `announcement_days: 90` default — for NIST/CMMC cyclical processes use `--days 730` explicitly.
- File signal `confidence < 0.5` should not trigger `action_required`. Only emit action items when confidence ≥ 0.7 OR when an announcement change_type is major_revision/minor_update.

## Regression cases to preserve
1. Returns `human_review_required: true` in every response.
2. Returns `action_required` only when both signals agree OR when a high-confidence file signal exists.
3. Returns `change_type` from the fixed vocabulary — never a freeform string.
4. Preserves `human_reviewed: true` entries when merging with `announcements_feed.json`.
5. Reports `announcement_feed_age_days` so consumers can detect staleness.

## Approval-gated changes
- Changing the action_required threshold (confidence and change_type filters).
- Adding new announcement feeds to `feed_registry.json` without testing the URL.
- Modifying the `change_type` vocabulary used by `announcement_monitor.py`.
- Changing how file signals and announcement signals are combined into one verdict.

## Minority-report policy
When file signal and announcement signal disagree on whether a change occurred, emit
`minority_report.conflicts` with both signals. Example: file ETag unchanged but
announcement says "final rule published." See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Verify CISA feeds use GitHub mirror path (not deprecated RSS).
- [ ] Confirm `announcement_monitor.py WINDOW_DAYS_DEFAULT` is still 180 (not changed).
- [ ] Smoke test: `python3 skills/atoms/framework-update-check/scripts/update_check.py --dry-run --format json`
- [ ] Confirm `human_review_required: true` and `announcement_feed_age_days` in all output paths.
- [ ] Check that log file is written to `logs/announcement_monitor_YYYY-MM-DD.log` on live run.
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
