---
name: changelog-query
description: >
  Query the GRC framework changelog for version transitions. Returns human-confirmed
  changelog entries with old/new version, change type, and summary.
  Use to determine if a framework has been updated since the last DB build.
  Do NOT use for live version monitoring (use framework-update-check).
  Do NOT use for feed registry status (use framework-registry-lookup).
atom: true
version: "1.0"
---

# changelog-query

Reads from the `changelog` table in grc.db (populated from framework_changelog.json).
Wraps `dbz_query.py changelog`.

## Input schema
```json
{
  "framework_id": "string? — optional filter by framework ID",
  "since": "string? — optional ISO date filter (returns entries after this date)",
  "change_type": "string? — optional filter: 'major_revision' | 'minor_update' | 'retired' | 'new_entry'"
}
```

## Output schema
```json
{
  "entries": [
    {
      "framework_id": "string",
      "change_type": "string — 'major_revision' | 'minor_update' | 'retired' | 'new_entry'",
      "old_version": "string",
      "new_version": "string",
      "changed_at": "string — ISO date",
      "summary": "string",
      "human_confirmed": "boolean"
    }
  ],
  "count": "integer"
}
```

## Do NOT use for
- Live version monitoring — use framework-update-check (polls crawl_seeds)
- Feed registry current_version — use framework-registry-lookup
- Announcements feed — different table (announcements, not changelog)

## Conflicting sources — minority-report policy
Changelog entries have `human_confirmed` flag. If a machine-detected version change
(from framework-update-check) conflicts with a human-confirmed changelog entry,
surface both. See canonical policy: `skills/shared/minority-report.md`.
