# Access Modes

Default assumption: **no OAuth and no API keys**.

## Preferred order
1. **local artifact mode** — local folders, uploaded corpora, and exported document sets.
2. **runtime-native mode** — built-in document readers, connectors, or local container execution.
3. **direct integration mode** — Unstructured local installs, self-hosted endpoints, or other explicit processing infrastructure.
4. **planning-only mode** — define chunking, tagging, and retrieval contracts without pretending partitioning already happened.

## Guidance
- Unstructured's open-source library can run locally for many formats; do not assume a hosted API is required.
- When a hosted partition endpoint is unavailable, process locally or emit a partition plan and chunk schema.
- Preserve local file paths and source ids so later reruns can attach richer parsing without changing downstream ids.
