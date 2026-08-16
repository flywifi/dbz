# dbz — GRC Cross-Mapping Engine

**Find where compliance frameworks overlap.** dbz shows how much audit work is shared across
SOC 2, ISO 27001, PCI DSS, HIPAA, HITRUST, FedRAMP, CMMC, NIST CSF, CSA CCM, and more — so you
can reuse the evidence you already have instead of starting each audit from scratch.

## The idea

Every framework is mapped onto one common yardstick: **NIST SP 800-53**. Because all of them are
measured against the same ruler, any framework can be compared to any other. Ask *"I'm already
SOC 2 — how much of PCI, ISO 27001, or FedRAMP do I already meet?"* and get a real answer with the
overlapping controls listed. It's **one unified map**, not a shelf of separate crosswalks.

## What it answers

- **Overlap between any two frameworks** — the shared-audit-work % plus the exact matching controls.
- **Reuse analysis** — which of your existing controls already satisfy a framework you don't hold yet.
- **FedRAMP scoping** — filter any comparison to the FedRAMP Low / Moderate / High baseline.
- **Implementation evidence** — per-product hardening (STIG) proof that a control is actually applied.

## What's inside

| Layer | What it gives you |
|---|---|
| **800-53 r5 spine** | The common yardstick — 324 controls + 872 enhancements every framework maps onto |
| **Master mapping surface** | 36 frameworks; **68 framework pairs stored** at control-id level (of 630 possible), each edge tagged by how it was established. Any-to-any comparison is answered on demand by the overlap engine + `overlap_matrix`, not by stored rows. |
| **Evidence concentration** | **82,587 of 97,668 master edges (84.6%) derive from one licensed artifact** (HITRUST CSF v11.4 Cross-Reference), composed through the hub rather than stated by a source; `unified_mappings` is 87% transitive-via-HITRUST. Tier and confidence are on every row. |
| **Overlap matrix** | 120 precomputed framework pairs (the 16 canonical frameworks) with shared-work % |
| **CCI dictionary** | 5,137 DISA control-correlation identifiers with definitions + multi-source corroboration |
| **STIG evidence** | 383 hardening benchmarks / 19,667 rules for per-product implementation proof |
| **FedRAMP 2026 (KSIs)** | FedRAMP's own 46 Key Security Indicators and their 373 published links to 800-53 |
| **Keep-current** | 161 official sources watched for changes, plus a horizon of 76 anticipated future revisions |

## How it works

**In plain terms:** dbz ingests the official published frameworks, normalizes each one onto the
800-53 spine, computes where they overlap, and stores it all in a single queryable database. Some
mappings come straight from the framework's own author, some from a neutral hub (NIST's CSF/OLIR
program), and some are inferred from broad agreement across independent sources — and every edge
carries a tag saying which, so you always know how strong a match is.

**Under the hood:** raw framework sources → the 800-53 projection spine → a `master_mappings`
surface + a precomputed `overlap_matrix`, all assembled deterministically into `grc.db` (SQLite,
~40 tables, schema 3.18) and queried with `dbz_query.py`. Full technical detail:
[`docs/cross-mapping-architecture.md`](docs/cross-mapping-architecture.md).

## Quick start

```bash
pip install -r requirements.txt

# Build the query database (deterministic; rebuild any time a source changes)
python cross-mapping/engine/build_db.py

# Compare any two frameworks — the headline query
python cross-mapping/engine/dbz_query.py overlap --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)"
python cross-mapping/engine/dbz_query.py master  --framework-a "SOC 2" --framework-b "PCI DSS v4.0"

# Which controls satisfy a specific requirement; scope a comparison to a FedRAMP baseline
python cross-mapping/engine/dbz_query.py master --framework "HIPAA Security" --control "164.312(a)(2)(i)"
python cross-mapping/engine/dbz_query.py master --framework-a "SOC 2" --scope-fedramp moderate

# Specialized surfaces
python cross-mapping/engine/dbz_query.py fedramp --coverage             # FedRAMP 2026 KSIs -> 800-53
python cross-mapping/engine/dbz_query.py cci     --coverage             # DISA CCI dictionary (5,137)
python cross-mapping/engine/dbz_query.py stig    --coverage             # per-product STIG evidence
python cross-mapping/engine/dbz_query.py horizon --upcoming 10          # anticipated framework revisions
```

`dbz_query.py` also exposes `reverse`, `forward`, `scope`, `consensus`, `olir-hub`, `feeds`,
`changelog`, and more — run `dbz_query.py -h` for the full surface. Add `--overlay` (on `master`,
`overlap`, `scope`, `search`) to tailor any answer to an industry / jurisdiction / client context
— a presentation filter that always discloses what it suppressed. See [`docs/overlays.md`](docs/overlays.md).

## Staying current

dbz watches **161 official sources** (`canonical-sources/feed_registry.json`) for version changes
and keeps a **horizon** of 76 anticipated future revisions (`canonical-sources/anticipated_updates.json`)
so a scheduled change — a new FedRAMP rule, an ISO amendment — is flagged before it lands, never
missed. See [`docs/standards-refresh-runbook.md`](docs/standards-refresh-runbook.md).

## Guarantees

- **Deterministic** — the same sources always build the same database (verified by a double-build check).
- **Never fabricated** — every mapping traces to a named authoritative source; uncertain links are
  left blank or flagged, not guessed.
- **Clean** — no real customer data, PII, or internal notes anywhere in the repo.

## Layout

```
cross-mapping/
  engine/        build_db.py (assembles grc.db) + dbz_query.py (the query surface) + loaders
  nist-catalog/  800-53 catalog ingestion + validation
  core-audit/    commercial-audit (SOC/ISO/HIPAA/HITRUST) crosswalk inputs
  schema/        enhanced_framework_schema.json (catalog schema v3.0)
  tests/         test_spine.py + validate_spine.py (correctness + no-fabrication gates)
canonical-sources/  source data, source_manifest.json (per-source column pins), feeds, horizon
skills/          Claude Agent Skills (compliance report analysis + evidence tooling)
docs/            architecture and subsystem documentation (below)
```

## Documentation

| Doc | Covers |
|---|---|
| [`cross-mapping-architecture.md`](docs/cross-mapping-architecture.md) | how sources become the unified database, end to end |
| [`BENCHMARK.md`](docs/BENCHMARK.md) | measured accuracy vs the production oracle crosswalks (pinned) |
| [`METRICS.md`](docs/METRICS.md) | the regenerable scoreboard (contents, tiers, evidence states, honesty ledger) |
| [`overlays.md`](docs/overlays.md) | context overlays: industry/jurisdiction/client presentation profiles |
| [`deployment-surfaces.md`](docs/deployment-surfaces.md) | the three ways to consume dbz + the shared hygiene boundary |
| [`persona-audit.md`](docs/persona-audit.md) | dated three-persona review of query output (UX backlog feed) |
| [`overlap-spine.md`](docs/overlap-spine.md) | the 800-53 projection spine + the overlap engine |
| [`consensus-detection.md`](docs/consensus-detection.md) | the provenance tiers and cross-source agreement model (evidence-state ladder: `protocol-layer/evidence-standards.md`) |
| [`cci-enrichment.md`](docs/cci-enrichment.md) | the CCI dictionary, bridge, and corroboration layer |
| [`fedramp-modernization.md`](docs/fedramp-modernization.md) | FedRAMP Consolidated Rules 2026 + the KSI layer |
| [`source-audit-phase25.md`](docs/source-audit-phase25.md) | the source universe, tiering, and OLIR-hub composition |
| [`horizon-scanning.md`](docs/horizon-scanning.md) | how anticipated future revisions are tracked |
| [`standards-refresh-runbook.md`](docs/standards-refresh-runbook.md) | keeping sources current |
| [`source-inventory.md`](docs/source-inventory.md) | the full catalogue of ingested and watched sources |
