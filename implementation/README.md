# implementation/ — deployment surfaces

dbz's query power is exposed through three surfaces. This directory holds the generated
artifacts for the non-Claude-Code surfaces.

## Surfaces

| Surface | Capability | What it needs |
|---|---|---|
| **Claude Code (in-repo)** | Full — every `dbz_query.py` subcommand, all skills/atoms | clone + `pip install -r requirements.txt` |
| **GPT / Gemini (function schemas)** | The six core operations as OpenAI-function schemas | the operator hosts `dbz_query.py` behind their own Action/function endpoint — dbz ships the **contract**, not the server |
| **claude.ai skills** | Packaged atoms | the atom bundle |

## Generated artifacts (`gpt/api/`)

- `gpt/api/tools.json` — combined OpenAI-function schema for the six exported operations.
- `gpt/api/skills/<atom>.json` — one function schema per operation.

These are **generated** from `skills/atoms/atoms.json` by `tools/export_openai.py`. Do not edit
them by hand — edit the atom's `input_schema` / `export` block and regenerate:

```bash
python3 tools/export_openai.py          # regenerate
python3 tools/export_openai.py --check   # drift guard (also runs as sync_check invariant 12)
```

### Why JSON, not YAML

The generator emits JSON, not YAML: `pyyaml` is outside dbz's dependency policy
(stdlib + pandas/openpyxl only, per `CLAUDE.md`). JSON is a valid subset of YAML, so any
OpenAI-function consumer that accepts YAML accepts these files unchanged.

## Recorded scope decision

This ships **schemas + docs, not a hosted HTTP service.** Serving `dbz_query.py` behind an HTTP
endpoint is a separate future decision. The schemas describe the tool contract; the operator
supplies the runtime.

## Hygiene rule

Any API-shaped output produced through these schemas must pass `tools/output_validate.py` before
it leaves the operator's boundary — provider-proprietary identifiers (evidence-request /
requirement ids) never leave the repo. See `docs/deployment-surfaces.md`.
