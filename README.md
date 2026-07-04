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

# Build grc.db, then query the master mapping surface (any framework <-> any framework)
python cross-mapping/engine/build_db.py
python cross-mapping/engine/dbz_query.py master --framework-a "SOC 2" --framework-b "PCI DSS v4.0"
python cross-mapping/engine/dbz_query.py master --framework "HIPAA Security" --control "164.312(a)(2)(i)"
python cross-mapping/engine/dbz_query.py master --framework-a "SOC 2" --scope-fedramp moderate

# STIG application layer (per-product CCI evidence); on-demand product overlap
python cross-mapping/engine/dbz_query.py stig --list --filter RHEL
python cross-mapping/engine/dbz_query.py stig --cci CCI-000068
python cross-mapping/engine/dbz_query.py stig --coverage
python cross-mapping/engine/dbz_query.py overlap --framework-a "stig:RHEL_9" --framework-b "FedRAMP r5"

# CCI dictionary (5,137 definitions) + multi-source mapping corroboration
python cross-mapping/engine/dbz_query.py cci --coverage
python cross-mapping/engine/dbz_query.py cci --id CCI-000068 --definition
python cross-mapping/engine/dbz_query.py cci --corroboration CCI-000068
```

## Key files

- `cross-mapping/schema/enhanced_framework_schema.json` — canonical schema (v3.0)
- `canonical-sources/source_manifest.json` — per-source sheet/column/version map (the durable fix for column drift)
- `cross-mapping/engine/overlap_calculator.py` — framework overlap engine
- `cross-mapping/engine/er_overlap.py` — ER-crosswalk overlap adapter
- `skills/compliance-report-analyzer/` — extraction-first audit report analyzer

## Source data

31 authoritative spreadsheets in `canonical-sources/source_data/`. See `canonical-sources/source_manifest.json` for the exact sheet name, header row, and column roles for each file.
