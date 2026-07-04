# CCI dictionary + mapping corroboration

DISA **Control Correlation Identifiers (CCIs)** are the atomic bridge between NIST 800-53 and
the technical requirement language STIGs test. This layer holds the *complete* CCI dictionary
(numbers + definitions + status) and a multi-source **corroboration** of every CCI↔800-53 edge.

## The three tables

- **`disa_ccis`** — the full CCI dictionary. **One row per CCI in the DISA CCI List XML
  (5,137)**, each with its `definition`, `status` (draft / deprecated), `type`, `publishdate`,
  the raw Rev-4 indices (`nist_rev4_refs`), the raw Rev-5 indices (`nist_r5_index`), the resolved
  r5 control set (`nist_rev5_refs`, control-level), and `legacy_refs` (Rev-3 + 800-53A indices for
  the CCIs that carry only legacy references). Definitions are **never gated on mappability** — a
  CCI that maps to no current r5 control is still a full dictionary row.
- **`cci_bridge`** — the resolved CCI → r5 control / sub-part edges, `basis`-stamped and never
  fabricated. Precedence: `r5_native` (3,838) → `r4_identity` (526) → `appj_absorption` (441,
  control-level) → `legacy_r3_identity` (556, control-level). The last recovers legacy-Rev-3-only
  CCIs — including the 13 that STIG rules cite — to their **base r5 control** where that control
  survives into r5; Rev-3 enhancement/sub-part numbering is not stable into r5, so only the base
  control identity is asserted (never a guessed sub-part). ~36 CCIs have no r5 successor and stay
  definition-only (reported, never dropped).
- **`cci_mapping_corroboration`** — one row per (CCI, r5_control) edge, recording which witnesses
  assert it: `disa_bridge`, `acasehs_r5`, `acasehs_r4`, `trackr_rmf`, and `stig_usage`. Verdict:
  `confirmed` (our bridge + ≥1 republication agree) / `disa_only` (our bridge alone) /
  `candidate` (a republication asserts an edge our bridge lacks — a gain to review, **never
  auto-promoted** into `cci_bridge`).

## What corroboration does — and does not — prove

`acasehs/STIG-Control-CCI` and `cyber.trackr.live/api/cci` are **derived republications of the
same DISA CCI list**. Their agreement therefore verifies **transcription/parse fidelity** and
surfaces **candidate mapping gaps** — it is *not* independent semantic authority, and never
overrides the DISA XML. The one genuinely independent witness is **`stig_usage`**: application
evidence that a CCI is operationally exercised by ≥1 STIG rule. Divergences (a republication
mapping a CCI to a different control) follow the minority-report policy: the DISA XML wins as
primary and the dissent is recorded.

## Sources (seeds)

| Source | Role | What it carries |
|---|---|---|
| DISA `U_CCI_List.zip` → `U_CCI_List.xml` (v2025-01-23) | **primary / ground truth** | numbers, definitions, status, Rev-4/Rev-5 refs (sub-item Index), 800-53A AP refs |
| `acasehs/STIG-Control-CCI` (`rev4cci.json` / `rev5cci.json`) | corroboration (derived) | revision-split control↔CCI + definitions |
| `cyber.trackr.live/api/cci` | corroboration (derived) | definitions + control-level `rmf` + `ap_acronym` + `family` |

Corroboration artifacts are refreshed by `tools/cci_harvest.py` (`--acasehs`, `--trackr --enrich`)
into `canonical-sources/source_data/cci/` (deterministic, sha-pinned). Currency is checked by
`standards_refresh.py --check` (CCI-list version + trackr enumeration size) and re-snapshotted by
`--fetch`.

## Querying

```bash
python3 cross-mapping/engine/dbz_query.py cci --coverage
python3 cross-mapping/engine/dbz_query.py cci --id CCI-000068 --definition
python3 cross-mapping/engine/dbz_query.py cci --corroboration CCI-000068
python3 cross-mapping/engine/dbz_query.py cci --control AC-17
```

## Gates

`validate_spine.py` check 10: the dictionary count equals the source XML `cci_item` count (no
silent drops), every row has a definition, every bridge edge carries a known basis, control-level
bases carry no guessed sub-part, and corroboration verdicts are exhaustive. `test_spine.py` pins
the basis vocabulary, dictionary completeness, and the small definition-only residue. Build is
deterministic (`disa_ccis` + `cci_mapping_corroboration` in `table_digests`).
