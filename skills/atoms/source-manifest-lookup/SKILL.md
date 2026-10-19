---
name: source-manifest-lookup
description: >
  Look up a canonical source's entry in source_manifest.json — by exact source key or by
  role — to learn its pinned file, version, sheet, column roles, and structure before
  parsing it. Use as the first step of artifact normalization or partitioning.
  Do NOT use for feed currency or version monitoring (use feed-poller).
  Do NOT use for the DB build manifest of row counts (use `dbz_query.py manifest`).
atom: true
version: "1.0"
---

# source-manifest-lookup

Read-only lookup into `canonical-sources/source_manifest.json`, the repository's single
authority for every source file's sheet, column, and version pin. Wraps
`tools/source_manifest_lookup.py`.

## Scope
- `--key <source id>` returns that one manifest entry (e.g. `scf-controls`).
- `--role <role>` returns every entry with that `role` (e.g. `scf_meta_framework`).

## Input schema
```json
{ "key": "string? — exact source id", "role": "string? — source role (exactly one of key/role)" }
```

## Output schema
```json
{ "manifest_entry": "object (key mode)", "manifest_entries": "array (role mode)",
  "count": "integer", "human_review_required": true }
```
An unknown key or role returns `{"error": ..., "human_review_required": true}` (role mode
also lists `known_roles`) and exits 1.

## Do NOT use for
- Feed currency or version monitoring — use feed-poller
- The DB build manifest (row counts, sha256) — use `dbz_query.py manifest`
- Writing or re-pinning the manifest — registry writes go through `tools/registry_io.py`

## Conflicting sources — minority-report policy
The manifest is the single pin of record, so this atom has no competing sources of its
own. If a caller finds the pinned `file`, `sheet`, or `version` disagreeing with the
artifact on disk, surface both and stop — never silently prefer either. See canonical
policy: `skills/shared/minority-report.md`.
