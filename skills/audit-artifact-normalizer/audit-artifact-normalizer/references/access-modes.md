# Access Modes

Default assumption: **no OAuth and no API keys**. Do not block the task just because hosted parsing credentials are missing.

## Preferred order
1. **local artifact mode** — uploaded files, folders, zip bundles, screenshots, and exports.
2. **runtime-native mode** — built-in PDF, DOCX, spreadsheet, slide, connector, or web tools already available in the runtime.
3. **direct integration mode** — Docling or other self-hosted parsing stacks when the operator actually has access.
4. **planning-only mode** — emit the bundle manifest, parser routing plan, and downstream handoff contract when the artifacts are not yet available.

## What changes by mode
- In local artifact mode, build the bundle manifest immediately and route each file to the safest local/native parser.
- In runtime-native mode, prefer the runtime's own PDF, spreadsheet, docx, slide, and connector paths before any external parser.
- In direct integration mode, use Docling for broad multi-format normalization or for higher-fidelity document conversion, especially when local execution or a self-hosted endpoint is available.
- In planning-only mode, create the normalized package skeleton, extraction plan, and handoff notes without inventing extracted content.

## Non-negotiable behavior
- Never require hosted parsing just because the upstream tool supports it.
- Preserve a manifest and lineage even when extraction is deferred.
- Be explicit about which files still need manual review or a later rerun.
