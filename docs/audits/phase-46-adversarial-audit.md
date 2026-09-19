# Phase-46 closing adversarial audit — 2026-09-19

**Scope.** The SCF 2026.2 ingest and everything it touched: the workbook/errata swap and
`source_manifest.json` re-pin, the framework-label bump with alias, the loader/voter
parametrization, the registry writes (`feed_registry.json`, `anticipated_updates.json`,
`framework_changelog.json` — all three regulatory-currency registries moved this phase),
and the phase-45 versioning repair. Written to satisfy the regulatory-phase closing gate
(`protocol-layer/quality-gates.md`) against this phase's own diff.

## Pass 1 — source integrity

- **The artifact.** `secure-controls-framework-scf-2026-2.xlsx` fetched twice from the
  declared source (`raw.githubusercontent.com/securecontrolsframework/...`), byte-identical
  both times (sha256 `9e0a4df4993726c9…`), pinned only after the second compare. Errata
  sha `5658560829db6149…`. Upstream renamed its file set at 2026.2 (kebab-case workbook,
  plain `errata.txt`, `Archived Versions/` folder) — recorded in the manifest, the feed
  notes, and the `standards_refresh.py` fetch recipe so the next release is fetchable.
- **The release itself** rests on the two-origin confirmation carried from phase 45
  (GitHub releases page: "2026.2", 08 Jul; securecontrolsframework.com verbatim on
  compensating controls) plus the errata's own announcement text, quoted in the
  `chg-scf-2026.1.1-to-2026.2` provenance block.
- **An upstream omission found and recorded:** the errata's "New Controls" list enumerates
  **65** ids; the measured id-set diff is **+66/−0** — `NET-06.9` is present in the
  workbook but missing from the errata. The changelog entry states the measured number and
  the discrepancy rather than repeating the errata's count.

## Pass 2 — claim support

Every load-bearing number, with its probe (scripts in the session scratchpad, outputs
reproduced in the phase plan and below):

| Claim | Probe | Result |
|---|---|---|
| SCF ids +66/−0 (1,468 → 1,534) | id-set diff, old workbook via `git show` | exact list printed; QTS domain = 34 of the 66 |
| 800-53 projection identical: 1,117 edges / 777 controls | full edge-set compare through the real loader logic + catalog filter | +0 −0; SAT-03.2 → AT-2(4),AT-2(5) and SAT-03.6 → AT-2(6) identical both sides |
| Fan-out witness 8,609 → 8,983 | both workbooks through the fanout logic with manifest columns | +374: 800-172 R3 +303, 800-171 r3 +62, CIS +9 |
| Voter pairs 15,843 → 15,906 (+625/−562) | `collect_scf` run on both workbooks | removals confined to the CIS pairings that also gained; voter rows 626 unchanged |
| Post-build: scf_direct 1,117 @ 'SCF 2026.2'; scf_composed_edges 8,983 | rebuilt grc.db | exact match; double-build digests identical |
| **confirmed 23,485 → 23,551 (+66)** | rebuilt confirmation layer | moved UP (witness is supports-only — the predicted direction); w_scf_composed pairs 36,604 → 36,982; `docs/BENCHMARK.md` restated in the same change, `count_truth` green |
| Full battery | test_spine, validate_spine (incl. check 20 re-derivability at 23,551), benchmark_oracles --check, scenarios, alias contract, sync_check | all green |

## Pass 3 — chain / mutation integrity

- All three registry writes went through `tools/registry_io.py` with `roundtrip_identical`
  asserted pre-save; `framework_vocab.json` (not a registry_io canonical) was edited by a
  script that asserts the same formatting roundtrip and **mechanically enumerates** the old
  label's occurrences, failing on any site beyond the two known ones.
- The label bump is alias-preserved: `SCF 2026.1` resolves via `framework_aliases`
  (vocab 1.11.0); the alias-contract test ran green.
- The sheet and path hardcodings (spine_loader, consensus_detector) are gone — both now
  resolve via `config.source_path`/`sheet_name` from the manifest pin, which is the
  CLAUDE.md rule this repo already had; the next SCF release is a manifest re-pin, not a
  code hunt.
- GRC domain traps swept: no confusion of SCF's acceptance-authority model (its crosswalks
  remain SCF/CAP-scope acceptance rules, bundled-crosswalk tier for other frameworks); the
  witness stays supports-only, never a publisher.

## Pass 4 — adversary output (mandatory)

**The single claim most likely to be wrong:** *"SCF 2026.2 changes the 800-53 mappings"* —
my own working expectation, apparently supported by the errata's explicit "Updated Mapping —
NIST 800-53 R5: SAT-03.2, SAT-03.6." The evidence that would confirm it: any edge-set
difference through the loader. The probe ran **before** the plan was written: +0/−0 across
all 1,117 edges, and the two named rows compared individually — identical. The claim is
**disconfirmed**; whatever SCF revised there does not survive normalization to our edge
level. Recorded (planning-standard §6) so no future session re-chases it.

**Second candidate:** the −562 removed voter pairs as a symptom of needle mis-resolution
among ~75 renamed columns. Disconfirming probe: the per-framework-pair delta shows removals
confined to the CIS v8 pairings that simultaneously gained (+625) — a token refresh inside
one column, not a column swap — and all 10 resolved columns were printed and verified
(HIPAA → `US\nHIPAA Administrative Simplification\n2013`, GDPR → `EMEA\nEU\nGDPR\n2016`).

**Third candidate:** the versioning repair being cosmetic. It is gated now: the
`version_current` count_truth claim was proven **red on the live 0.12.0-vs-0.12.1 drift**
(the real phase-45 miss as the fixture) before `VERSION` was repaired, and fires on any
future divergence between `VERSION` and the latest changelog heading.

## The rollback rehearsal (transcript of record)

Recipe anchor: `46-pre` = `26720f6`. Executed in a scratch worktree at HEAD (`b4a6dab`),
2026-09-19: checkout of the eleven 2026.1.1-era paths + `git rm` of the two 2026.2 files,
full regeneration (`generate_controls.py` → OSCAL cache → `build_db.py`), then the
assertion:

```
gen rc=0
oscal rc=0
build rc=0
ROLLBACK REHEARSAL OK: scf_direct=1117 scf_composed_edges=8609 confirmed=23485 label='SCF 2026.1'
```

The rolled-back tree reproduces the pre-ingest state **exactly**, including the confirmed
headline returning to 23,485. Worktree removed after the assertion. The recipe is printed
verbatim in the `[0.13.0]` changelog entry.

## Phase-45 versioning miss (correction of record)

Phase 45 closed without cutting its snapshot anchors and without moving `VERSION` —
checklist items that exist precisely because earlier phases missed them. Found by this
phase's pre-flight probes, repaired at `26720f6` (retroactive 45-pre/45-close anchors at
CI-green shas, VERSION 0.12.1), and made mechanical (`version_current`). Stated here and in
the changelog, louder than the original claim of a clean close.

## Residual risk (never an all-clear)

- The confirmed +66 was verified directional and re-derivable (check 20), but the
  per-verdict flips were not individually adjudicated — they inherit the confirmation
  rules' trust in the SCF witness columns, whose CIS/800-171/800-172 tokens changed most.
- The Focal Documents sheet (new in 2026.2) is unread by any loader; if SCF relocated
  load-bearing content into it, our probes would not see that. All 12 pinned fanout
  columns, `SCF #`, and the 800-53 R5 column were verified still on the main sheet.
- Maturity-model and compensating-controls criteria are deliberately not ingested.
- The rollback rehearsal proves path-level restoration at this HEAD; after future phases
  touch the same files, the recipe's file list must be re-derived, not replayed blindly.
- BENCHMARK.md's historical per-framework table still shows the phase-43-era "SCF 2026.1
  63" row — deliberately untouched (it records a past measurement), which a reader could
  misread as current until the next benchmark refresh re-states it.
