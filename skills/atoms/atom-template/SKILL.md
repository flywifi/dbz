---
name: __ATOM_NAME__
description: "REPLACE — what this atom does and exactly when to invoke it. Single-operation: one input schema → one output schema. Be specific. Add a 'Do NOT use for…' clause to prevent misuse."
atom: true
version: "1.0"
---

# __ATOM_NAME__

## What this atom does
REPLACE with a one-sentence description of the single operation performed.

## Input schema
```json
{
  "REPLACE_FIELD": "type — description"
}
```

## Output schema
```json
{
  "REPLACE_FIELD": "type — description",
  "human_review_required": true
}
```

## Do NOT use for
- REPLACE — list tasks that should go to a different atom or the full skill
- Chained lookups requiring multiple DB queries — compose atoms in a workflow.json instead

## Behavior
1. Validate required input fields; return error with field name if missing.
2. Execute the single operation against grc.db or the relevant engine module.
3. Return structured output with `human_review_required: true` on any compliance-facing result.

## Output: always emit human_review_required
Any result used for compliance, regulatory, or customer-facing decisions must include
`human_review_required: true`. Results used for pure DB lookup may omit it if they are
intermediate inputs to a workflow step that will add the flag at completion.

## Non-fabrication rule
Never fabricate control IDs, framework citations, crosswalk relationships, or CVE data.
Leave uncertain fields blank or omit them. Source precedence: explicit DB data > crosswalk >
source_manifest > blank.
