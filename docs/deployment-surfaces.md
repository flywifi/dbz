# Deployment surfaces

dbz is one engine reachable three ways. This doc explains the trade-offs and the hygiene
boundary that applies to all of them.

## The three surfaces

1. **Claude Code, in-repo (full capability).** Clone the repo, build `grc.db`, and every
   `dbz_query.py` subcommand and every skill/atom is available. This is the reference surface —
   nothing is lost.

2. **GPT / Gemini via function schemas (contract only).** `tools/export_openai.py` generates
   OpenAI-function schemas (`implementation/gpt/api/`) for the six core operations
   (overlap, master-crosswalk, compliance-crosswalk, gap-analysis, control-search, cfr-lookup).
   A ChatGPT Action or Gemini function can call these — **but the operator must host
   `dbz_query.py` behind their own endpoint.** dbz ships the tool contract, not the server. The
   schemas are generated and drift-guarded (`export_openai.py --check`, sync_check invariant 12),
   so they never fall out of sync with the atom registry.

3. **claude.ai skills (packaged atoms).** The atoms bundle for the hosted skills surface.

## Hygiene boundary (applies everywhere)

The canonical mapping CSVs carry provider-proprietary identifiers (evidence-request /
requirement ids). Those files stay confined to their mapping directories and their contents
never appear in query output — only aggregate counts do (enforced by `tools/health_audit.py`
publication-hygiene patterns).

When output flows through an external surface (an Action response, a generated report), run it
through `tools/output_validate.py` first: it re-applies the leak patterns and additionally
checks that every cited control/CCI id is real and that confidence language matches the mapping
tier. Any HIGH finding means human review before the output leaves the operator's boundary.

## Regenerating the export

```bash
python3 tools/export_openai.py           # rewrite implementation/gpt/api/
python3 tools/export_openai.py --check    # verify committed output matches the registry
```

The `--check` form is wired into `tools/sync_check.py` (invariant 12) so a stale export fails
the drift guard.
