---
name: framework-update-check
description: >
  Check one or more GRC frameworks for version updates by combining file-level version signals
  (framework_monitor.py) with RSS/Atom announcement feed signals (announcement_monitor.py).
  Returns a unified record with change status, recent announcements, changelog summary, and
  action items for re-pinning source_manifest.json. Detects major revisions, draft releases,
  and public comment periods weeks before a new PDF/Excel file is published.
  Do NOT use for downloading or ingesting updated source files — that is a separate pipeline step.
---

# framework-update-check

Combines two monitoring prongs into a unified update signal per framework:

1. **File signals** (`framework_monitor.py`) — version-signal poller (ETag, GitHub releases, RSS).
   Detects when an authoritative source document has likely changed.

2. **Announcement signals** (`announcement_monitor.py`) — RSS/Atom news feed scanner for
   standards-body blogs and news pages. Detects major revisions, draft releases, and public
   comment periods **weeks before** the corresponding PDF/Excel file is published.

Frameworks monitored are defined in `canonical-sources/feed_registry.json` (31 entries).

## Input

```json
{
  "feed_ids": ["nist-800-53", "fedramp", "cmmc"],
  "announcement_days": 90,
  "dry_run": false
}
```

## Output

```json
{
  "tool": "framework-update-check",
  "checked_at": "2026-06-30T12:00:00Z",
  "summary": {
    "total_checked": 3,
    "action_required": 1,
    "unchanged": 2,
    "errors": 0
  },
  "action_required": [
    {
      "feed_id": "fedramp",
      "label": "FedRAMP Program",
      "checked_at": "2026-06-30T12:00:00Z",
      "file_signals": {
        "changed": true,
        "confidence": 0.9,
        "update_notes": "Release tag changed: 'v3.0.0' → 'v3.1.0'",
        "version_signal": "v3.1.0"
      },
      "announcements": [
        {
          "title": "FedRAMP releases Rev 5 baseline update",
          "published_at": "2026-06-15T00:00:00Z",
          "url": "https://www.fedramp.gov/...",
          "change_type": "minor_update",
          "human_reviewed": false
        }
      ],
      "changelog_recent": [
        {
          "version_to": "5.1.0",
          "change_date": "2025-11-01",
          "controls_added": 2,
          "controls_withdrawn": 0,
          "human_confirmed": true
        }
      ],
      "action_items": ["nist-800-53b-baselines"],
      "human_review_required": true
    }
  ],
  "unchanged_ids": ["nist-800-53", "cmmc"],
  "human_review_required": true
}
```

### `change_type` vocabulary (announcement signals)

| Type | Trigger keywords |
|---|---|
| `major_revision` | "final rule", "revision", "Rev 6", "version 2" |
| `minor_update` | "errata", "correction", "update", "patch" |
| `draft_release` | "initial public draft", "IPD", "second draft", "RFC" |
| `public_comment` | "comment period", "public comment", "open for comment" |
| `new_framework` | "new standard", "introduces", "first edition" |
| `retired` | "withdrawn", "superseded", "retired" |
| `informational` | (default — no high-signal keyword matched) |

## Do NOT use this atom for
- Downloading or replacing source files in canonical-sources/ (manual step after human review)
- Parsing the content of updated framework files (separate ingestion pipeline)
- Claiming a framework has definitely changed — use as a signal only
- Making source_manifest.json changes without a human verifying the actual framework document

## Pipeline note
Script: `skills/atoms/framework-update-check/scripts/update_check.py`

```bash
# Check specific frameworks
python3 skills/atoms/framework-update-check/scripts/update_check.py \
    --feed nist-800-53 fedramp --days 90 --format summary

# Check all frameworks (dry run — don't write output files)
python3 skills/atoms/framework-update-check/scripts/update_check.py \
    --dry-run --format json
```

Calls:
- `cross-mapping/engine/framework_monitor.py:run_monitor()` — file-level version signals
- `cross-mapping/engine/announcement_monitor.py:run()` — RSS/Atom announcement signals

Writes side outputs (unless `--dry-run`):
- `cross-mapping/output/framework_updates_feed.json` — file signal feed
- `canonical-sources/announcements_feed.json` — announcement feed (merged, preserves `human_reviewed: true`)

`human_review_required: true` — both monitor signals and announcements are advisory; a human
must verify the actual framework change and determine if source files need updating before
re-running the catalog build.
