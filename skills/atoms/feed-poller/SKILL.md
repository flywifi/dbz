# feed-poller

Poll a single framework monitoring entry from `feed_registry.json` and detect whether a version change has occurred since the last recorded version.

## Scope

Calls `framework_monitor.py` for a single `framework_id` and returns:
- Current version as recorded in feed_registry
- Latest version detected via the entry's `check_strategy` (github_release, poll_landing, or rss_feed)
- Whether the detected version differs from the recorded version
- The version signal type used to detect the change

Use to check if a specific compliance framework has released a new version without running a full registry sweep.

## Input Schema

```json
{
  "framework_id": "string — e.g. nist-800-53, hitrust, csa-ccm"
}
```

## Output Schema

```json
{
  "framework_id": "string",
  "label": "string",
  "current_version": "string",
  "latest_detected": "string or null",
  "check_strategy": "string — github_release | poll_landing | rss_feed",
  "version_signal": "string",
  "changed": "boolean",
  "draft_status": "string — none | draft | retired",
  "human_review_required": true
}
```

## Do NOT use for

- Sweeping all frameworks at once (use `framework_monitor.py --all` directly)
- Frameworks with `draft_status: "retired"` where change detection is not meaningful
- Making decisions about whether to upgrade a framework (that requires human review of release notes)

## References

- `framework_monitor.py` — version polling engine
- `canonical-sources/feed_registry.json` — framework monitoring registry (98 entries)
- `minority-report.md` — non-negotiable fabrication rules
