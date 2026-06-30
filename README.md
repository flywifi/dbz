# dbz — GRC Cross-Mapping Backend

Cross-framework compliance mapping engine for GRC, sales overlap analysis, and customer success reporting.

## Two mapping cores

| Core | Location | Scope |
|---|---|---|
| NIST 800-53 action-based catalog | `cross-mapping/nist-catalog/` | FedRAMP, 800-171/172, CUI, CCIs |
| ER / local-control crosswalk | `cross-mapping/core-audit/` | SOC 1/2, ISO 27001/2, HIPAA, HITRUST |

The **overlap engine** (`cross-mapping/engine/`) sits on top of both and computes "shared audit work %" for sales/CS use cases.

## Quick start

```bash
pip install -r requirements.txt

# ER-anchored overlap (fastest path — no build required)
python cross-mapping/engine/er_overlap.py

# NIST catalog build (single family)
python cross-mapping/nist-catalog/ingestion/generate_controls.py --family AC

# Validate output
python cross-mapping/tests/validate_catalog.py
```

## Key files

- `cross-mapping/schema/enhanced_framework_schema.json` — canonical schema (v3.0)
- `canonical-sources/source_manifest.json` — per-source sheet/column/version map (the durable fix for column drift)
- `cross-mapping/engine/overlap_calculator.py` — framework overlap engine
- `cross-mapping/engine/er_overlap.py` — ER-crosswalk overlap adapter
- `skills/compliance-report-analyzer/` — extraction-first audit report analyzer

## Source data

31 authoritative spreadsheets in `canonical-sources/source_data/`. See `canonical-sources/source_manifest.json` for the exact sheet name, header row, and column roles for each file.

## Development branch

`claude/grc-backend-enhancements-0yxff6` — never push directly to `main`.

See `CLAUDE.md` for full conventions.
