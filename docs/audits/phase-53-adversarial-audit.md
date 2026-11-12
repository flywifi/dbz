# Phase-53 closing adversarial audit — 2026-11-12

**Scope.** Every regulatory-currency write of the phase:
- **Canonical data.** The SCF 2026.3 workbook replaces 2026.2; the new
  `canonical-sources/scf/scf-id-legacy-map-2026.3.json`.
- **`source_manifest.json`.** `scf-controls` re-pinned; new `scf-id-legacy-map`;
  `cprt-csf2-olir-graphs` gains `scf_id_space`; `scf-errata` kept as 2026.2 history.
- **`feed_registry.json`** feed `scf`; **`framework_changelog.json`** `chg-scf-2026.2-to-2026.3`;
  **`anticipated_updates.json`** `au-scf`.
- **`doc_claims.json`** (`schema_version.context_patterns`); **`fetch_schedule.json`** (`nvd-7d`).

It is written to satisfy the regulatory-phase closing gate (`protocol-layer/quality-gates.md`).

**Origin.** The user asked whether to move to the issuer's newer release and then asked for the
2026.3 ingest. Two decisions were the user's: commit the issuer's legacy-id map as a queryable
table with a command, and leave `crosswalk_80053_master.json` untouched while the oracle compares
through the map. The plan followed `protocol-layer/planning-standard.md`; the whole implementation
ran twice in a throwaway clone (one local commit per planned commit, the CI rehearsal after each,
six builds) before any write. Record: `docs/source-inventory.md` (Phase 53).

## Pass 1 — source integrity
- **The workbook is the issuer's release asset.** 5,378,907 B, sha256 `5a89bf2d3c106a9a…`, equal
  to the digest on the release-asset listing; the applier asserts it before copying.
- **The legacy map is the issuer's statement, not an inference.** It is the `Legacy SCF #` column
  of the pinned workbook. The workbook states the same map three times (main sheet, `Change
  Overview`, `READ THIS`): 1,534 pairs each, 23 deprecated merges, **0 contradictions**. No legacy
  id maps to two current ids. Any unparsed token stops the generator; there were none in 1,591 rows.
- **The generator is deterministic:** four generations, byte-identical (sha256 `1525dcda31347a0f…`).
- **The changelog quote is verbatim** from the release page as captured on 2026-11-07, and the
  issuer's own figures (1,457 renumbered, 99 moved, 80 new, 185 renamed, 204 wordsmithed, 23 merged
  into 22) equal the measured ones.

## Pass 2 — claim support
- **Every number in the registries and docs is computed by the stage that writes it** from the
  pre-ingest and post-ingest builds; none is typed.
- **The implementation reproduced the dry-run exactly:** the measurement script's output on the
  real builds has 0 lines differing from the rehearsal's.
- **`scf_id_space: "SCF 2026.2"` claims only what is measured:** all 186 SCF ids of NIST's set are
  2026.2 ids. It does not claim NIST mapped against 2026.2; the set states no version and was
  fetched before 2026.2 was released.

## Pass 3 — chain / mutation integrity
- **Commits:** `909b4f9` anchor, `27d37f0` NVD digest parser, `3de6eb8` schema-bump tool,
  `c29c75c` schema 3.20, `3d7bd57` the ingest, `4908877` registries and docs, then this close-out. Each
  was rehearsed package-free at commit time (20 steps, 21 from the bump-tool commit on).
- **Registries** were written only through `tools/registry_io.py`; all round-trip identical.
- **Schema commit is data-neutral:** pre-phase build → schema-3.20 build, 1 table digest differs
  (the new, empty `scf_id_history`).
- **Ingest:** 8 table digests differ (`consensus_edges`, `framework_cci_confirmation`,
  `framework_labels`, `framework_projection`, `master_mappings`, `overlap_matrix`,
  `scf_composed_edges`, `scf_id_history`). **Registries commit:** 2 (`anticipated_updates`,
  `framework_registry`).
- **Rollback rehearsed** (in the clone): undoing the ingest and registries commits leaves the tree
  equal to the schema-3.20 commit and the rebuilt database with 0 digests differing. Recipe:
  CHANGELOG 0.18.0.

## Pass 4 — adversary, run
1. **"Re-pin and relabel is enough, as in phase 46."** Built: validation red, 51 stray ids, SCF's
   confirmed rows 63 → 16. **Overturned.**
2. **"The translation loses nothing."** 451 of 451 pairs translated, 0 dropped, 186 → 186 distinct
   ids, SCF's confirmed rows 64. **Holds.**
3. **"The oracle stays meaningful through the map."** Raw ids 47.0 %, through the map 98.2 % of
   765. **Holds, with a limit:** it reads the projection only and shows 98.2 % on the untranslated
   build too, so it cannot see the OLIR mis-join. Check 8j exists for that.
4. **"The new assertions are live."** `test_spine` against the untranslated database: red, naming
   the strays; green on the translated one. Repeated in the real tree. **Holds.**
5. **"The id-space guard fails closed."** The artifact declared in a foreign id space: 0
   translated, 451 dropped and counted. **Holds.**
6. **"Nothing outside SCF is downgraded."** Row-by-row over 172,651 non-SCF pairs: 73 verdict
   changes, all upward; CIS's 40 through the consensus voter, the other 33 through the fan-out
   witness. **Holds.**
7. **"The schema-bump fix leaves history alone."** Shipped tool: abort, nothing written. Patched:
   selftest 5/5 on the `e4a1d3f` fixture; the real bump left STATE's four historical mentions.
   **Holds.**
8. **"657 ids were reused"** (the research figure). Reconciled on the generated map: 700.
   **Overturned** before any write.

## Residual risk
- **A user holding a 2026.2 id** can still query under the alias label and reach another control.
  The vocabulary note, the overlap-query skill and `scf-legacy` say so; the release makes this
  unavoidable.
- **NIST's reference vintage is unknown.** If it was mapped against a release in which an id meant
  something else, that error predates this phase (the id join on 2026.2 made the same assumption).
- **The next SCF renumbering** needs its own crosswalk; until one is registered the guard drops
  NIST's pairs and `test_spine` goes red, by design.
- **Not ingested:** STRM files, Focal Documents, the Risk and Threat catalogs; other SCF documents
  on disk stay at 2026.2 / 2026.1.
- **The master crosswalk's SCF column stays 2026.2-era** (user decision).
