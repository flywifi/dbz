---
name: framework-update-check
description: >
  Check one or more GRC frameworks for version updates using the framework monitor.
  Returns a news-feed record with change status, version signal, and action items for
  re-pinning source_manifest.json when a framework publishes a new version.
  Use this atom to seed the compliance update repository / news feed.
  Do NOT use for downloading or ingesting updated source files — that is a separate pipeline step.
---

# framework-update-check

Checks authoritative sources (landing pages, GitHub releases, RSS feeds) for GRC framework updates.
Produces structured records indicating whether a framework has likely updated since the last check,
and which `source_manifest.json` keys need to be re-pinned.

Frameworks monitored (defined in `canonical-sources/feed_registry.json`):
- NIST 800-53, 800-53B, 800-171, 800-172
- CMMC 2.0, FedRAMP (Rev5 + 20x)
- ISO/IEC 27001:2022
- HITRUST CSF v11.4
- DISA CCI List
- CSA CCM v4
- SOC 2, HIPAA Security Rule

## Input

```json
{
  "feed_ids": ["nist-800-53", "fedramp", "cmmc"],
  "registry_path": "canonical-sources/feed_registry.json",
  "out_path": "cross-mapping/output/framework_updates_feed.json"
}
```

## Output

```json
{
  "tool": "framework-update-check",
  "checked_at": "2026-06-30T12:00:00Z",
  "summary": {
    "total_checked": 3,
    "changed": 1,
    "unchanged": 2,
    "errors": 0
  },
  "changed": [
    {
      "feed_id": "fedramp",
      "label": "FedRAMP Program",
      "change_status": "changed",
      "update_notes": "Release tag changed: 'v3.0.0' → 'v3.1.0'",
      "release_url": "https://github.com/GSA/fedramp-automation/releases/tag/v3.1.0",
      "action_items": [
        {
          "action": "re-pin source_manifest.json",
          "manifest_key": "nist-800-53b-baselines",
          "reason": "FedRAMP baseline OSCAL may have updated parameter values"
        }
      ]
    }
  ],
  "human_review_required": true
}
```

## Do NOT use this atom for
- Downloading or replacing source files in canonical-sources/ (manual step after human review)
- Parsing the content of updated framework files (separate ingestion pipeline)
- Claiming a framework has definitely changed — use as a signal only

## Pipeline note
Calls `cross-mapping/engine/framework_monitor.py:run_monitor()`.
Output is written to `cross-mapping/output/framework_updates_feed.json` and compared to the
previous run to detect version signal changes.
`human_review_required: true` — monitor signals are advisory; a human must verify the actual
framework change and determine if source files need updating before re-running the catalog build.
