# Cross-Mapping Architecture

How the GRC cross-mapping backend turns raw framework spreadsheets into a
validated, multi-scenario handoff contract — and how it stays current.

## Two cores + an update layer

```
                    ┌─────────────────────────────────────────────┐
                    │              UPDATE LAYER (news feed)         │
                    │  framework_crawler.py   (PDF/Excel discovery) │
                    │  oscal_diff.py          (control-level diff)  │
                    │  framework_monitor.py   (version signals)     │
                    │      ▲ feed_registry.json (18 sources)        │
                    └──────┼──────────────────────────────────────┘
                           │ flags "re-pin source X"
        ┌──────────────────┴───────────────────┐
        │            source_manifest.json        │  ← every sheet/column/version pin
        └──────────────────┬───────────────────┘
            ┌──────────────┴──────────────┐
            ▼                             ▼
┌───────────────────────┐   ┌───────────────────────────┐
│  NIST 800-53 core     │   │   ER / commercial-audit core │
│  (federal/FedRAMP/CUI)│   │   (SOC/ISO/HIPAA/HITRUST)    │
│  generate_controls.py │   │   er_overlap.py              │
└───────────┬───────────┘   └─────────────┬───────────────┘
            ▼                              ▼
   handoff contract v1.1.0          ER overlap matrix
   (322 ctrls + 867 enh)            (shared audit work %)
            │                              │
            └──────────────┬───────────────┘
                           ▼
              build_reverse_index.py
              (bidirectional lookup)
```

## The handoff contract (schema v1.1.0)

Each control record is a **self-contained, multi-scenario handoff**. One record
serves five consumers without reshaping:

| Consumer | Fields it reads |
|---|---|
| Assessment / STIG | `mapped_ccis`, `parameters`, `text`, `discussion` |
| FedRAMP authorization | `baselines`, `compliance_scope.fedramp_levels` |
| Gap analysis | `unified_mappings`, `compliance_scope.mapped_frameworks` |
| Sales / CS overlap | `compliance_scope.framework_count`, `unified_mappings` |
| Audit / reporting | `mapped_ccis`, `unified_mappings`, per-framework lists |

`unified_mappings` is the **primary** field — every cross-framework relationship
in one typed list. Each record carries `framework`, `framework_version`,
`control_id`, `relationship_type`, `strength`, `direction`, and **`mapping_source`**
(provenance). The per-framework lists (`iso_27001_mappings`, `cmmc_mappings`,
`hitrust_mappings`) are retained for backward compatibility.

Formal schema: `cross-mapping/schema/handoff_contract_v1.1.0.schema.json`.
Validate with `validate_schema.py` (jsonschema) and `validate_catalog.py` (field rules).

### Relationship-type vocabulary
`Subset | Superset | Equal | Intersecting` (NIST OLIR STRM) · `mapped_to`
(simple reference) · `transitive_via_hitrust` (bridged inference — see below).

### CCI format
DISA CCIs use the exact `CCI-NNNNNN` form (6-digit zero-padded). Enforced by both
validators and the JSON Schema (`^CCI-\d{6}$`).

## Framework coverage

**Direct (authoritative) mappings** — one source file each:
- DISA CCI (via r4→r5 bridge), ISO/IEC 27001:2022 (OLIR STRM), CMMC 2.0 / 800-171,
  HITRUST CSF v11.4, **NIST CSF 2.0** (official concept crosswalk).

**Bridged via the HITRUST hub** (`relationship_type=transitive_via_hitrust`) —
HITRUST CSF v11.4 cross-references 64 authoritative sources, so we pivot
NIST → HITRUST → {framework} to deliver 19 international standards & legal
regulations **without a separate crosswalk for each**:

> EU GDPR · CCPA/CPRA · PCI DSS v4.0 · ISO/IEC 27002/27701/29100/29151/27799/23894 ·
> ISO 31000 · NIST AI RMF · NIST CSF · APEC CBPR · OECD Privacy · Singapore PDPA ·
> NY DFS 23 NYCRR 500 · Massachusetts 201 CMR 17 · Nevada NRS 603A · HIPAA Privacy.

Bridged mappings are **always labeled** so a transitive inference is never mistaken
for an authoritative direct mapping (the no-fabrication rule). Frameworks not in the
HITRUST hub (EU AI Act, NIS2, DORA, UK GDPR, ISO 42001) are monitored as standalone
feeds for now, bridged through ISO 23894 / NIST AI RMF where applicable.

## The update layer (news feed)

The catalog is only as current as its sources. Three prongs keep it fresh; all
read `canonical-sources/feed_registry.json` (18 framework definitions):

1. **`framework_crawler.py`** — the transverser. Politely crawls each framework's
   official download page, discovers downloadable standards artifacts
   (PDF/Excel/CSV/JSON), and reports NEW/CHANGED vs stored sha256/size/Last-Modified
   baselines (`crawl_baselines.json`). Respects robots.txt, honors
   `Retry-After`/`RateLimit-Reset`, backs off — never evades. Also fingerprints the
   known direct document URLs from the registry (so a robots-blocked SPA page doesn't
   blind us to the .xlsx it links). Modeled on the educator-tools standards-updater.

2. **`oscal_diff.py`** — the deepest prong. Fetches NIST's machine-readable OSCAL
   catalog (Range-windowed to survive proxy truncation of the ~10MB file) and diffs
   it **control-by-control** against our generated catalog. Answers "has NIST
   added/withdrawn/renamed a control since we built?" — the question that actually
   triggers a rebuild.

3. **`framework_monitor.py`** — lightweight version-signal poller (landing-page
   ETag/Last-Modified/content-fingerprint, GitHub releases, RSS). Emits action items
   for which `source_manifest.json` keys to re-pin.

**Nothing is auto-applied.** Every prong sets `human_review_required: true`; a human
verifies the change on the primary source, re-pins the manifest, and rebuilds.

### Change intelligence
`feed_registry.json → monitoring_policy`: primary vs secondary confirmation,
confidence scoring (0.9 = primary + ≥2 signals, 0.7 = primary + 1 signal,
0.4 = discovery-only), 730-day recency window.

## Reverse index (bidirectional handoff)

The catalog is NIST-anchored (NIST → others). `build_reverse_index.py` inverts
`unified_mappings` into `{framework → {target_control_id → [nist_controls]}}`, so a
customer migrating *into* NIST — or auditing a NIST system against ISO/PCI/GDPR —
can ask "which NIST controls satisfy ISO 27001 A.5.16?" and get `[AC-2, IA-2, IA-4,
IA-5, IA-8]`. 24 frameworks indexed.

## Build & verify

```bash
# Build
python cross-mapping/nist-catalog/ingestion/generate_controls.py        # all families
python cross-mapping/engine/build_reverse_index.py                       # reverse lookup

# Verify
python cross-mapping/nist-catalog/ingestion/validate_catalog.py          # field rules
python cross-mapping/nist-catalog/ingestion/validate_schema.py           # JSON Schema
python cross-mapping/tests/test_ac_fixture.py                            # fixtures

# Stay current (news feed)
python cross-mapping/engine/framework_crawler.py --crawl --update-baselines
python cross-mapping/engine/oscal_diff.py
python cross-mapping/engine/framework_monitor.py
```

## Atoms (`skills/atoms/`)

Single-operation skills following the educator-tools convention (`SKILL.md` +
`scripts/` + "Do NOT use for…" clause + `human_review_required`):
`compliance-crosswalk` · `gap-analysis` · `overlap-query` · `framework-update-check`.
