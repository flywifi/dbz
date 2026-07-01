# Cross-Mapping Architecture

How the GRC cross-mapping backend turns raw framework spreadsheets into a
validated, multi-scenario handoff contract — and how it stays current.

## Two cores + an update layer + a query DB

```
                    ┌─────────────────────────────────────────────────────┐
                    │              UPDATE LAYER (news feed)                 │
                    │  framework_crawler.py    (PDF/Excel discovery)        │
                    │  oscal_diff.py           (control-level diff)         │
                    │  framework_monitor.py    (version signals)            │
                    │  announcement_monitor.py (RSS/Atom announcement feeds)│
                    │      ▲ feed_registry.json (31 sources)                │
                    │      → announcements_feed.json (structured entries)   │
                    │      → framework_changelog.json (confirmed diffs)     │
                    └──────┼──────────────────────────────────────────────┘
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
   (324 ctrls + 872 enh)            (shared audit work %)
            │                              │
            └──────────────┬───────────────┘
                           ▼
                     build_db.py
              ┌─────────────────────┐
              │   grc.db (SQLite)   │  ← query layer; rebuilt after every catalog run
              │  15–20 MB, indexed  │
              └────────┬────────────┘
                       ▼
                 dbz_query.py  (CLI: reverse, forward, scope, overlap,
                                search, changelog, feeds, announcements)
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

The catalog is only as current as its sources. Four prongs keep it fresh; all
read `canonical-sources/feed_registry.json` (31 framework definitions):

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
   triggers a rebuild. With `--write-changelog`, appends confirmed diffs to
   `canonical-sources/framework_changelog.json`.

3. **`framework_monitor.py`** — lightweight version-signal poller (landing-page
   ETag/Last-Modified/content-fingerprint, GitHub releases, RSS). Emits action items
   for which `source_manifest.json` keys to re-pin.

4. **`announcement_monitor.py`** — **early-warning prong**. Scans RSS/Atom news
   feeds from standards bodies (NIST CSRC, ENISA, PCI SSC, FedRAMP, ICO, etc.)
   for major revisions, draft releases, and public comment periods. These announcements
   appear **weeks before** a new PDF/Excel file is published, so this prong fires
   first. Writes to `canonical-sources/announcements_feed.json`; preserves
   `human_reviewed: true` flags on existing entries.

**Nothing is auto-applied.** Every prong sets `human_review_required: true`; a human
verifies the change on the primary source, re-pins the manifest, and rebuilds.

### Change type vocabulary (announcement signals)
`major_revision · minor_update · draft_release · public_comment · new_framework · retired · informational`
Classified by regex scoring against title + summary text; threshold 0.15 confidence.

### Change intelligence
`feed_registry.json → monitoring_policy`: primary vs secondary confirmation,
confidence scoring (0.9 = primary + ≥2 signals, 0.7 = primary + 1 signal,
0.4 = discovery-only), 730-day recency window.

Each feed entry now includes `announcement_feeds` (list of RSS/Atom URLs),
`draft_status` (none | ipd | second_draft | final_public_draft),
`draft_landing_url`, and `public_comment_deadline`.

## Local SQLite database (`grc.db`) + query CLI

The 29 MB JSON catalog costs ~50k LLM tokens per query even for a simple lookup.
`build_db.py` normalizes the catalog into a local SQLite database that answers common
questions with **zero LLM tokens** — the LLM only handles interpretation, gap analysis,
and synthesis.

### Token savings

| Query | Before | After |
|---|---|---|
| Reverse lookup (ISO A.5.16 → NIST) | ~50k tokens | ~200 tokens |
| Forward mapping (AC-2 → all frameworks) | ~50k tokens | ~800 tokens |
| Scope filter (FedRAMP Moderate, AC family) | ~50k tokens | ~500 tokens |
| ER overlap (SOC 2 ↔ ISO 27001) | ~10k tokens | ~200 tokens |
| Keyword search | not feasible | ~1k tokens |
| Announcement check | not feasible | ~300 tokens |

### Key tables
`controls` · `enhancements` · `parameters` · `unified_mappings` (60k+ rows, indexed) ·
`er_controls` · `er_mappings` · `framework_registry` · `changelog` · `announcements` ·
`controls_fts` (FTS5 keyword search)

### Key views
`er_overlap_pairs` (pre-joined overlap matrix) · `baseline_controls` · `reverse_index`

### Query CLI (`dbz_query.py`)

```bash
# Reverse lookup: which NIST controls map to ISO A.5.16?
python3 cross-mapping/engine/dbz_query.py reverse \
    --framework "ISO/IEC 27001:2022" --control A.5.16

# Forward mapping: where does AC-2 map in ISO and CMMC?
python3 cross-mapping/engine/dbz_query.py forward \
    --control AC-2 --frameworks iso cmmc

# Scope filter: FedRAMP Moderate AC-family controls
python3 cross-mapping/engine/dbz_query.py scope \
    --fedramp moderate --family AC

# ER-level overlap
python3 cross-mapping/engine/dbz_query.py overlap \
    --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)"

# Keyword search (FTS5)
python3 cross-mapping/engine/dbz_query.py search \
    --keyword "multi-factor authentication" --scope moderate

# Recent announcements
python3 cross-mapping/engine/dbz_query.py announcements --days 30

# Framework changelog
python3 cross-mapping/engine/dbz_query.py changelog --framework nist-800-53
```

Output: `--format table` (default) · `--format json` · `--format csv`
DB auto-discovery: walks up from CWD for `cross-mapping/output/grc.db`; override with `--db PATH`.

### Rebuild trigger
`build_db.py` runs automatically as the final step of `generate_controls.py --all-families`,
keeping `grc.db` in sync with the JSON output. Runtime ~30 seconds; output ~15–20 MB.
`grc.db` is gitignored (build artifact).

## Reverse index (bidirectional handoff)

The catalog is NIST-anchored (NIST → others). The `reverse_index` view in `grc.db`
inverts `unified_mappings` so a customer migrating *into* NIST — or auditing a NIST
system against ISO/PCI/GDPR — can ask "which NIST controls satisfy ISO 27001 A.5.16?"
and get `[AC-2, IA-2, IA-4, IA-5, IA-8]`. The legacy `build_reverse_index.py` +
`reverse_index.json` remain for offline reference; live queries should use the DB.

## Build & verify

```bash
# Build catalog + DB
python3 cross-mapping/nist-catalog/ingestion/generate_controls.py       # all families
python3 cross-mapping/engine/build_db.py                                 # grc.db (auto-runs after generate)
python3 cross-mapping/engine/build_reverse_index.py                      # legacy reverse_index.json

# Verify
python3 cross-mapping/nist-catalog/ingestion/validate_catalog.py         # field rules
python3 cross-mapping/nist-catalog/ingestion/validate_schema.py          # JSON Schema
python3 cross-mapping/tests/test_ac_fixture.py                           # fixtures

# Verify DB row counts
python3 -c "
import sqlite3; c = sqlite3.connect('cross-mapping/output/grc.db')
print('controls:', c.execute('SELECT COUNT(*) FROM controls').fetchone()[0])
print('unified_mappings:', c.execute('SELECT COUNT(*) FROM unified_mappings').fetchone()[0])
print('er_mappings:', c.execute('SELECT COUNT(*) FROM er_mappings').fetchone()[0])
"

# Stay current (news feed)
python3 cross-mapping/engine/framework_crawler.py --crawl --update-baselines
python3 cross-mapping/engine/oscal_diff.py --write-changelog
python3 cross-mapping/engine/framework_monitor.py
python3 cross-mapping/engine/announcement_monitor.py
```

## Feature flags (opt-in integrations)

Anything that needs OAuth, an API key, or other per-user setup is gated behind a
feature flag and **disabled by default**, so the core pipeline runs for everyone
with zero configuration. Registry: `canonical-sources/feature_flags.json`;
loader: `cross-mapping/engine/feature_flags.py`.

A flag is only **effective** when it is both *enabled* (config or env override
`DBZ_FF_<ID>=1`) and *provisioned* (its required credentials are present). Code
checks `flags.effective(id)` and degrades gracefully otherwise — uses bundled data,
reports a gap, or notes what's missing. Nothing hard-fails for lack of a key.

```bash
python3 cross-mapping/engine/feature_flags.py --list             # status of all flags
python3 cross-mapping/engine/feature_flags.py --enable cloud_render
```

| Flag | Gates | Default-off fallback |
|---|---|---|
| `github_authenticated` | GitHub token for monitor release checks | unauthenticated public API |
| `cloud_render` | JS-page rendering for the crawler | report js_required for manual review |
| `nist_cprt_api` | NIST CPRT structured API | bundled spreadsheets / OSCAL |
| `mcp_elicit`, `mcp_google_drive` | OAuth MCP servers | local files / skip step |
| `connector_thoropass / vanta / drata / aws_audit_manager` | live GRC platform tenants | bundled sample crosswalk CSVs |

This is also where the **Elicit / Google Drive MCP servers** live: they require
interactive OAuth that can't run headless, so they stay off until a user authorizes
them in an interactive `claude mcp` / `/mcp` session or via claude.ai connector settings.

## Atoms (`skills/atoms/`)

Single-operation skills following the educator-tools convention (`SKILL.md` +
`scripts/` + "Do NOT use for…" clause + `human_review_required`).

| Atom | Script | DB method | Fallback |
|---|---|---|---|
| `compliance-crosswalk` | `crosswalk.py` | `SELECT` from `controls` + `unified_mappings` | JSON catalog load |
| `gap-analysis` | `gap_analysis.py` | LEFT JOIN `controls` ↔ `unified_mappings` | — |
| `overlap-query` | `overlap_query.py` | `er_overlap_pairs` view + `er_mappings` | — |
| `framework-update-check` | `update_check.py` | `framework_monitor` + `announcement_monitor` | — |

All atom scripts auto-discover `grc.db` by walking up from CWD.
`compliance-crosswalk` falls back to direct JSON loading if the DB is not yet built.

## Multi-agent orchestration bucket (`skills/multi-agent-orchestrator/`)

A reusable, drift-resistant way to run many sub-agents on one large task —
decompose → fan out → validate → consolidate → recurse → stop. It generalizes the
hand-run fan-out patterns (e.g. reading many sources and merging the findings) into a
disciplined capability. The engine stays domain-agnostic; the bucket is generic
orchestration machinery.

**The load-bearing rule:** the manager reads *envelopes*, never raw sub-agent
transcripts. Every sub-agent is forced to return the same shape
(`skills/shared/orchestration-envelope.schema.json`), so consolidation is mechanical and
the manager's context never fills with raw output.

```
task ──▶ task-decompose ──▶ [ wave: fan-out, one agent per scope,        ]
                            [ each FORCED to return the envelope schema  ]
                                     │
                                     ▼
                         envelope-validate  (anti-drift gate — malformed = hard stop)
                                     │
                                     ▼
                         findings-consolidate  (deterministic merge: dedup by key,
                                     │           conflicts preserved, confidence floored,
                                     │           coverage honest)
                                     ▼
                         frontier-expand  (dedup residual_frontier vs seen → next wave,
                                     │      or signal saturation)
                                     ▼
                         loop-until-dry ──▶ consolidated result (human_review_required: true)
```

| Contract (canonical, drift-guarded) | Purpose |
|---|---|
| `skills/shared/orchestration-envelope.schema.json` | the fixed agent return shape |
| `skills/shared/frontier-model.md` | recursion + stop conditions (loop-until-dry, depth/size caps) |
| `skills/shared/consolidation.md` | deterministic merge rules (LLM judges, script computes) |

| Atom | Role |
|---|---|
| `task-decompose` | task → mode + non-overlapping first-wave scopes + stop conditions |
| `envelope-validate` | structural gate; a bad envelope never enters consolidation |
| `findings-consolidate` | deterministic merge (`scripts/consolidate.py`) — same envelopes → byte-identical output |
| `frontier-expand` | dedup residual leads vs `seen`; produce next wave or signal saturation |

**Modes** are routed by task class (`references/routing.md`): quick and deep-technical
lookups → `read-fanout` (read-only); canonical/seed edits → `mutate` (one git worktree
per agent, `depth_cap 1`); web/MCP reach → `external` (flag-gated). The default engine is
the Workflow tool driven directly; the declarative `workflow.json` compiles to a Workflow
run only when the `orchestration_hybrid_mode` flag is effective and a trigger holds
(named/recurring workflow, deterministic replay, or agent count over the size cap).

`tools/sync_check.py` guards the bucket with 4 invariants (6–9) alongside the 5 atom
invariants.
