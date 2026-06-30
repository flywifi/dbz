---
name: compliance-report-analyzer
description: extract controls, mappings, tests, and exceptions from uploaded soc 1, soc 2, iso 27001, iso 27002, and hipaa audit artifacts into spreadsheet-ready review outputs. use when the task involves compliance reports, bridge letters, auditor test tables, screenshots, spreadsheets, or user-supplied crosswalks for core audits only. preserve source wording, exact ids, duplicate mappings, and native framework order; use bundled mapping assets only as supporting crosswalks; leave unsupported fields blank instead of guessing.
---

# Compliance Report Analyzer

## Overview

Analyze uploaded compliance reports and mapping artifacts and convert them into a structured control review artifact for core audits only. Default to strict extraction from the source, use reversible low-risk inference only when exact identifiers or clearly labeled joins support it, and never fill gaps from general framework knowledge.

## Workflow

1. Confirm the framework is in scope: SOC 1 Type 1, SOC 1 Type 2, SOC 2 Type 1, SOC 2 Type 2, ISO 27001, ISO 27002, or HIPAA.
2. Inspect the available artifacts: reports, screenshots, spreadsheets, user-supplied crosswalks, and bundled mapping files in `assets/mappings/`.
3. Work in extraction mode by default. Switch to inference mode only when the relationship is directly supported by source structure and can be reversed safely.
4. Build row-level output using the exact schema in [references/output-schema.md](references/output-schema.md).
5. Apply the extraction and normalization rules in [references/extraction-rules.md](references/extraction-rules.md).
6. If bundled mapping files are relevant, consult [references/mapping-assets.md](references/mapping-assets.md) before using them.
7. Return results in this order unless the user requests otherwise: Control Review, Exception Focus, Summary, then optional posture analysis.

## Core Operating Rules

- Treat explicit report text as highest authority.
- Preserve exact control ids, criteria ids, objective names, and auditor wording.
- Preserve one-to-many and many-to-one mappings. Do not collapse duplicates.
- Join tables only on exact or clearly equivalent identifiers shown in the source set.
- Leave uncertain fields blank and flag ambiguity for review.
- Do not expand beyond the supported frameworks unless the user explicitly asks.
- Do not convert one framework into another unless the source set contains an explicit crosswalk.

## Source Precedence

Use this order whenever sources conflict:

1. Explicit text in the source report or artifact
2. Source-provided mapping tables
3. Source-provided testing or results tables
4. Source-provided local or proprietary mapping artifacts
5. Clearly labeled crosswalks supplied by the user
6. Conservative inference supported directly by source structure
7. Otherwise leave blank

## Decision Rules

### Extraction mode

Use this mode by default. Extract only what is explicitly stated in the source or visible table structure.

### Inference mode

Use only when all of the following are true:

- the relationship is supported by source labels or exact ids
- the inference does not require external framework knowledge
- the value is low-risk and reversible
- leaving the field blank would also be acceptable if confidence drops

Allowed examples:

- joining a control description table to a testing table by the same control id
- carrying a mapped criterion forward from a labeled mapping table to the same exact control id in a testing table

Disallowed examples:

- assigning HIPAA safeguards from generic security language alone
- assigning SOC 2 criteria from topic familiarity alone
- inventing cross-framework mappings not shown in the source set

## What to Read Next

- Read [references/extraction-rules.md](references/extraction-rules.md) for the full extraction, classification, sorting, and normalization rules.
- Read [references/output-schema.md](references/output-schema.md) for the exact row schema and sheet layouts.
- Read [references/mapping-assets.md](references/mapping-assets.md) before using any bundled CSV or XLSX mapping file.

## Practical Guidance

- For PDFs, screenshots, and image-heavy auditor reports, prefer multimodal inspection over noisy OCR when possible.
- For spreadsheets and bundled mapping files, inspect the actual sheet names and headers before joining data.
- When both mapping and testing tables exist, join them by exact control id and preserve every resulting row.
- Treat inherited, complementary, carved-out, and subservice controls as distinct classifications unless the source explicitly states they were tested.
- For Type 1 reports, focus on point-in-time design language. For Type 2 reports, preserve period-based testing and operating-effectiveness language.

## Output Pattern

Unless the user requests a different deliverable, produce:

1. **Control Review** with the exact columns and order in `references/output-schema.md`
2. **Exception Focus** using the same columns, including all rows where `Exceptions Noted = Exception noted`
3. **Summary** with counts by framework and native domain or criterion order
4. **Optional posture analysis** only when the user asks for interpretation

## Example Requests

- “Analyze this SOC 2 Type 2 report and produce Control Review, Exception Focus, and Summary.”
- “Use the uploaded CSV crosswalks to map this HIPAA assessment into the required row schema.”
- “Join the report’s testing table to the local control mapping spreadsheet, but leave unsupported ownership fields blank.”
- “Review this ISO 27001 package and list only exception rows plus a summary tab.”
