---
name: audit-artifact-normalizer
description: normalize audit and compliance artifact bundles into review-ready manifests, extraction plans, and downstream handoff files. use when chatgpt needs to process mixed evidence packages and should work cleanly with local files, runtime-native tools, and optional docling-style integrations with or without separate credentials.
---

# Audit Artifact Normalizer

## Mission

Turn messy evidence bundles into a clean, reusable package that downstream skills can trust. Default to the **highest-quality path that does not require new credentials**.

## Access modes

Read `references/access-modes.md` first. Assume no OAuth and no API keys unless the user explicitly says otherwise.

## Best-fit tasks

- uploaded zip bundles of audit evidence
- mixed folders containing PDFs, screenshots, spreadsheets, notes, and transcripts
- pre-briefing evidence cleanup before compliance or account review
- front-door normalization before `document-intelligence`, `compliance-report-analyzer`, `briefing-generator-companion`, or `account-evidence-harvester`

## Core rules

- Inventory before reasoning.
- Prefer native runtime parsers and local scripts before hosted tools.
- Preserve provenance for every file, expansion, duplicate, and warning.
- Never invent extracted content when only a routing plan is available.
- Record the selected access mode in `normalized/access-mode.json`.

## Workflow

1. Run `scripts/plan_access_mode.py` to select the safest viable operating mode.
2. Run `scripts/init_bundle.py` to inventory files, expand zips, classify formats, and detect duplicates.
3. Run `scripts/plan_extraction.py` to create parser routing and downstream handoff suggestions.
4. Use the runtime's native PDF, office, spreadsheet, slide, connector, or web tooling when available.
5. Validate the package with `scripts/validate_bundle.py`.
6. Hand off to the best downstream skill based on file mix and requested output.

## Output contract

Produce by default:
- `normalized/access-mode.json`
- `normalized/package-manifest.json`
- `normalized/source-index.json`
- `normalized/warnings.json`
- `normalized/duplicate-report.json`
- `normalized/extraction-plan.json`
- `normalized/bundle-validation.json`
- `summary.md`

## Thoropass pairings

- `document-intelligence` for multi-format extraction and QA
- `compliance-report-analyzer` for supported audit frameworks
- `account-evidence-harvester` when account-linked evidence needs broader collection context
- `briefing-generator-companion` when the normalized package feeds a prep brief or follow-up

## Failure behavior

- If extraction cannot run yet, still emit the manifest, access-mode selection, and extraction plan.
- If a file type is unknown, preserve it in the bundle and mark it for manual review.
- If the user lacks credentials for optional parsers, continue with local/native paths rather than stopping.

## Bundled resources

- `scripts/plan_access_mode.py`
- `scripts/init_bundle.py`
- `scripts/plan_extraction.py`
- `scripts/validate_bundle.py`
- `references/access-modes.md`
- `references/bundle-schema.md`
- `references/handoff-patterns.md`
- `references/runtime-and-parser-notes.md`
