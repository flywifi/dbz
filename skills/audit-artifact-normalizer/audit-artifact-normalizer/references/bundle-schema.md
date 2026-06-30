# Bundle Schema

The normalized bundle is the contract between this skill and downstream readers.

## package-manifest.json

Top-level fields:
- `bundle_version`
- `input_root`
- `created_at`
- `source_count`
- `archive_expansions`
- `files`

Each `files[]` item should include:
- `id`
- `relative_path`
- `absolute_path`
- `filename`
- `extension`
- `size_bytes`
- `mime_type`
- `sha256`
- `classification`
- `is_archive`
- `is_image_heavy`
- `sensitivity_hint`
- `account_hints`
- `framework_hints`
- `duplicate_of`
- `warnings`

## source-index.json

Purpose: compact index for downstream routing and UI summaries.

Required fields:
- `source_count`
- `classifications`
- `sources`

Each `sources[]` item should keep a subset of the manifest fields and exclude `absolute_path` when user-facing.

## warnings.json

Required fields:
- `warnings`

Each warning:
- `source_id`
- `severity` using `info`, `warning`, or `blocked`
- `code`
- `message`
- `suggested_fallback`

## duplicate-report.json

Required fields:
- `canonical_sources`
- `duplicate_groups`

Each duplicate group should be keyed by sha256 and list the canonical source plus suppressed duplicates.

## extraction-plan.json

Required fields per item:
- `source_id`
- `classification`
- `recommended_route`
- `scan_or_layout_risk`
- `recommended_downstream_skill`
- `notes`

## summary.md

Human-readable summary should cover:
1. input scope
2. main file families
3. duplicates and unsupported files
4. likely next skill
5. top risks or gaps
