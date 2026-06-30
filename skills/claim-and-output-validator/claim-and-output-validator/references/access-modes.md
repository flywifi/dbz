# Access Modes

Default assumption: **no OAuth and no API keys**.

## Preferred order
1. **local artifact mode** — rule-based validation of copy, JSON, YAML, and operator-provided material.
2. **runtime-native mode** — validate outputs produced inside the current runtime or connector-backed workflow.
3. **direct integration mode** — export recurring failures into Promptfoo or other external evaluation systems when credentials and infrastructure exist.
4. **planning-only mode** — emit validation profiles and repair guidance when the draft or schema is not yet available.

## Guidance
- This skill should remain useful even in a fully offline environment.
- Deterministic checks are the default contract; vendor-backed evals are optional escalation paths.
