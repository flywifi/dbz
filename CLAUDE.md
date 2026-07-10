# CLAUDE.md
Conventions for working in the GRC Cross-Mapping Backend (`dbz`) repository.

## What this repo is
A GRC compliance cross-mapping engine with two complementary cores:
1. **NIST 800-53 action-based catalog** — depth for federal/FedRAMP/CUI (assessment objectives, FedRAMP baselines, CCIs, 800-171/172).
2. **ER/local-control crosswalk** — commercial-audit side (SOC 1/2, ISO 27001/2, HIPAA, HITRUST, GDPR), real production data from `compliance-report-analyzer`.

The overlap engine sits on top of both and powers "shared audit work %" for sales/CS use cases.

## Layout

```
dbz/
├── cross-mapping/
│   ├── schema/          # enhanced_framework_schema.json (v3.0) — source of truth
│   ├── nist-catalog/    # rebuilt ingestion loaders + generated output
│   │   ├── ingestion/   # rewritten generate_controls_*.py
│   │   └── output/      # generated per-family JSON (build artifact)
│   ├── core-audit/      # ER/local-control crosswalk CSVs (SOC/ISO/HIPAA/HITRUST)
│   │   └── mappings/    # *.csv from compliance-report-analyzer
│   ├── engine/          # overlap_calculator.py + er_overlap.py + query API
│   ├── output/          # combined catalog build artifacts
│   └── tests/           # fixtures + validation scripts
│       └── fixtures/    # AC-family fixture data
├── canonical-sources/   # 31 authoritative source spreadsheets + CCM v4 (raw, versioned)
│   └── source_manifest.json  # per-file sheet/column/role/version map
├── overlap-data/        # HIPAA↔HITRUST, SOC2↔HITRUST, GDPR↔SOC2, 45 CFR citations
├── skills/              # Claude Agent Skills (compliance-report-analyzer + 5 evidence skills)
├── apps/                # legacy Tkinter analyzers (reference-only)
└── docs/                # architecture notes, research, source inventory
```

## Two data cores

### NIST catalog (`cross-mapping/nist-catalog/`)
- Source of truth: `canonical-sources/source_manifest.json` for every sheet/column/version pin.
- Loaders live in `ingestion/`; output in `output/`. **Never hardcode column names** — always read from `source_manifest.json`.
- Enhancement rows (`AC-2(1)`, `AC-2(2)`, …) are separate rows in the real catalog; group by base control id.
- CCI bridge: DISA CCI List Rev 5 → r4 IDs → r5 IDs via `sp800-53r4-to-r5-comparison-workbook.xlsx`.
- 800-53A assessment procedures are the backbone (all controls, not just AC-2).

### ER crosswalk (`cross-mapping/core-audit/`)
- Canonical data: `mappings/*.csv` — each `ER-N` row has positionally-aligned `Local Controls (Linked)` / `Framework (from Local Controls (Linked))`.
- Parsing logic: `cross-mapping/engine/er_overlap.py`.
- Combination crosswalks (e.g. `SOC 2 T2 & ISO 27001.csv`) are **overlap oracles** for validation.

## Branching & git
- Develop on the designated feature branch. **Never push to `main`.**
- Push with `git push -u origin <branch>`; retry network failures with backoff.
- Do not open a PR unless explicitly asked.

## Skills convention
Skills in `skills/` follow the `SKILL.md` + `references/` + `scripts/` convention used in educator-tools.
- `SKILL.md` must describe scope and include "Do NOT use for…" clause.
- Shared `plan_access_mode.py` (access mode hierarchy: `direct_integration > runtime_native > local_artifact > planning_only`).
- No external dependencies beyond stdlib + pandas/openpyxl (available via `requirements.txt`).

## Non-negotiables
- Never fabricate framework control IDs, citations, or crosswalk relationships. Leave uncertain fields blank.
- Source precedence: explicit report text > source-provided mappings > bundled crosswalks > blank.
- No real PII or customer data anywhere — placeholders only.
- Schema validation: generated catalog must validate against `cross-mapping/schema/enhanced_framework_schema.json`.

## Commit messages
Describe the change and reference the affected component (ingestion loader, overlap engine, ER crosswalk, skill). Update `docs/` at phase boundaries.

## Publication hygiene (non-negotiable)
- Commits, trailers, and repo files carry **no chat/session links, no internal notes, and no
  personal information** (no personal emails, no session identifiers). Commit messages carry
  **no trailers at all** — plain 1–2 sentence descriptions only.
- If a human author identity is ever required, use the account's GitHub noreply routing address
  (`<id>+<login>@users.noreply.github.com`) — never a real email.
- Provider-proprietary identifiers from production data exports (evidence-request / requirement
  ids) never appear in docs, reports, query output, or ledger citations — aggregate counts only.
  The data files themselves are the private canonical data and stay confined to their mapping
  directories.
- `tools/health_audit.py` enforces the file-side rules on every scan.
