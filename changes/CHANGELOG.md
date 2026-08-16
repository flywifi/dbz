# Changelog

Format follows Keep a Changelog conventions; one entry per shipped phase. Versioning policy:
`CHANGE_MANAGEMENT.md`.

## [0.12.0] — 2026-08-16 (phase 44 — a retraction, three identifier defects, and a permanent planning standard)

MINOR: a new framework label, corrected data, two new gates. No schema bump, no query-surface
break.

### RETRACTION — phase-43 finding B-2 was wrong
- **Claimed:** 18 genuine CCI bridge gaps, two of them STIG-exercised. **True: zero gaps.** All
  231 `candidate` anchors are stale-identifier artifacts — **214** where DISA's own Rev-5
  reference points elsewhere and our bridge already follows it, **17** Appendix-J privacy
  enhancement ids with no Rev-5 reference at all.
- **The probe:** each candidate's claimed control compared against `disa_ccis.nist_rev5_refs`
  and our `cci_bridge` row. CCI-000297 claims `CM-2(1)`, DISA says **`CM-2`**; CCI-002364 claims
  `AC-12(1)`, DISA says **`AC-12(2)`**; CCI-002508–2512 claim `SC-34(3)`, DISA says **`SC-51`**.
- **Why it happened:** each pair was judged on whether the CCI's text matched the claimed
  control's *title* — it did, every time — without consulting the authority. **Text
  plausibility is not authority.**
- **No number moves with the retraction**: `candidate` anchors already produce `weak` framework
  rows, and no data was ever changed on B-2's strength. Finding B-3 (two transposed CCIs) is
  *strengthened* — DISA's references confirm the republications have them swapped.
- The worksheet is re-dispositioned in place with `authority_checked` on all 231; the loader
  docstring and validator label no longer call the class a "gain"; the anchor verdicts are now
  defined in `framework_vocab.json`.

### HIPAA citations now carry the label of the rule they cite
- 45 CFR Part 164 has three subparts and each is its own rule. `consensus_detector._canon`
  accepted any `164.xxx` and labelled all of it "HIPAA Security", putting **95 Privacy Rule and
  23 Breach Notification citations under the Security Rule** (118 master rows: SOC 2 47 · PCI 35
  · 800-53 25 · ISO 9 · 800-171 2).
- Routing added at `_row_pairs`, the single choke point all four voters pass through.
  `HIPAA Breach Notification` is a new label registered as deliberately distinct;
  `master_frameworks` moves **35 → 36** and the stored-pair space **60 of 595 → 68 of 630**.
- **A guard added at the same time suppressed 38 manufactured pairs** between subparts of one
  regulation, which splitting the label would otherwise have created. The count is printed at
  build time because it could not be measured before the fix existed.
- **Not fixed, and said so:** the consensus surface still stores `164.308` where the projection
  carries `164.308(a)(1)(ii)(A)`. `consensus_key` coarsens to that level deliberately, and
  re-granularising moves `w_consensus`, `master_mappings`, overlap and the scenario pins
  together.

### Two more identifier defects closed
- **SOC 2 category headings rejected:** `normalize_tsc_id` accepted a `.0` minor, so `P4.0` (a
  category) was treated as a criterion in **11 master rows and 173 consensus edges**. No
  published criterion has a zero minor. Master rows 97,668 → 97,657.
- **Framework-name vocabulary reconciled and gated:** 25 labels the build emits were undeclared
  in `framework_names.allowed` — including `HIPAA Security` itself — while `HIPAA Security Rule`
  was declared and used by nothing. New **validator check 21** fails on any emitted-but-
  undeclared label (declared-but-unused stays legal), proven red by removing a live label.

### The adversary re-draw, run rather than described
The phase-43 audit named its most-likely-wrong claim and the probe that would overturn it. Phase
44 ran it: an equal-allocation draw of **146 edges across 26 pairs** (79 reusing phase-43
verdicts, 67 newly adjudicated). **Unsupported holds — 20.5% vs 20.2%, z = 0.08** — so the
headline survives, and the tier remains statistically indistinguishable from the authoritative
stratum (z = −0.36) and far better than the hub (z = −5.14). **Supported does not hold: 49.6% →
39.0%**, the difference moving into `SCOPE_MISMATCH`, so that figure must always be quoted with
its allocation.

### The planning standard is now permanent
`protocol-layer/planning-standard.md` — the seven questions per workstream, a research record
where every number names its probe, **code executed read-only before it enters a plan**, and an
adversarial check that is run rather than described. Every rule cites the failure in this
repository that it prevents. Cited from `CLAUDE.md`, the quality gate and the recovery package;
a compact copy in the user-level conventions file governs plans in every repository.

### What did not change
No schema. The confirmation headline is unmoved at **23,485 of 180,413**. Moved digests:
`consensus_edges`, `master_mappings`, `framework_labels`, `framework_cci_confirmation`,
`scf_composed_edges`, `anticipated_updates`.

## [0.11.0] — 2026-08-16 (phase 43 — everything still open: measured, coded, and gated)

MINOR: new registered claims, a new validator check, new manifest keys, committed audit
evidence, and two adjudications. No breaking change, no schema bump, and **no mapping row was
mutated, promoted, re-tiered or deleted**.

### The consensus layer's biggest voter had no provenance
- `canonical-sources/crosswalk_80053_master.json` was committed on 2026-07-01 as material
  "staged for future ingestion", was never registered in `source_manifest.json`, and carries
  **no upstream URL, edition or retrieval date** — while voting in **4,071 of the 6,842
  strong/moderate consensus edges**. Dropping the voter would take strong+moderate 6,842 →
  3,537 and `strong` 910 → 148.
- Measured per column against the loaded projections: its PCI column is 1,348 of 1,351
  assertions already present from other sources (a restatement, so not an independent vote
  there), while SOC 2 TSC, HIPAA, 800-171r3 and ISO contribute **1,062 original mapping
  assertions that appear nowhere else in this repository**. Its SCF column is not read by the
  voter at all.
- **Nothing was re-weighted.** The file is registered with the gap recorded, the sensitivity is
  reproducible via the new `cross-mapping/tests/consensus_sensitivity.py`, and the decision is
  left to a later deliberate change. Published in `docs/BENCHMARK.md`.

### Two vocabulary statements the engine contradicts — corrected, with no number changed
- `framework_vocab.json` claimed the confirmation witnesses were "independent by construction".
  They are not, at the anchor layer: acasehs r4/r5 and trackr are **derived republications of
  the same DISA list** (their own metadata says so), which is transcription fidelity, not
  independent authority. STIG usage is the one independent anchor witness and covers **541 of
  5,592** anchor rows against the DISA bridge's 5,361. **The 23,485 headline does not inherit
  this**: `confirmed` additionally requires a CCI-level witness — a second same-anchor publisher
  or a STIG rule — neither derived from DISA.
- The vocabulary defined `corroborated` as "exactly one agreement witness". **18,338 of 102,497
  corroborated rows carry two or more.** The definition now states the rule the engine
  implements.
- **`validate_spine` check 20** re-derives every stored verdict from that row's own witness
  columns: 180,413 of 180,413 match. Proven red against a tampered copy before acceptance.

### Manifest coverage was hand-kept and had drifted
- `build_db`'s `row_counts` was a literal 40-name tuple; the digest block beside it had been
  derived from `sqlite_master` since phase 31-2 precisely because "a hand-kept list is how
  coverage gaps arise". It had: `framework_cci_confirmation` (180,413) and `scf_composed_edges`
  (8,626) were missing since phases 38 and 40. Counts are now derived from the same source and
  exclusion list — 40 → **42 keys**, two additions, zero removals.
- With the manifest key finally present, the two headline figures are registered with
  `count_truth` (**15 claims**): `cci_confirmation_pairs` and `cci_confirmed_count`, both proven
  red against drifted docs. They cite `docs/BENCHMARK.md` only — STATE and CHANGELOG state these
  numbers inside historical phase records, and citing those would force a future legitimate
  change to rewrite history to satisfy a checker.
- Two stale per-framework figures corrected (CIS 1,399 → 1,400; CSA CCM 247 → 318), and the
  claim mechanism's real limit recorded in `doc_claims.json`: a claim asserts a doc states the
  value *somewhere*, not that every restatement agrees.

### The phase-36 audit evidence was one container-death from gone
- Its seeded frame, all **220 sample keys** and the 40-row worksheet lived only in a session
  scratchpad, while STATE parked an "independent re-label" item pointing at that file. All 220
  keys were verified to still resolve and are now committed under `docs/audits/data/` with a
  README. The worksheet ships with its verdict field **null**, as it always was — the 65
  verdicts exist only as prose in the phase-36 report, and an empty worksheet is the better
  starting point for an independent labeler anyway.

### Two adjudications, both deferred for six phases (`docs/audits/phase-43-adjudication.md`)
- **Consensus cross stratum**, seeded n=120 of 3,422: **49.6% supported, 30.3% scope-mismatch,
  20.2% unsupported** (CI [13.9, 28.3]). Against phase 36's reference points the tier is
  significantly better than the hub (63.2%, **z = −5.01**) and statistically indistinguishable
  from the authoritative stratum (25.0%, z = −0.39). Failures concentrate: **20 of 21
  HIPAA-side edges fail** because every HIPAA identifier in this stratum is a whole 45 CFR
  section; three edges carry `164.530`, a Privacy Rule section, under the label "HIPAA
  Security".
- **All 231 `candidate` CCI anchors**: **209 (90.5%) are stale Rev-4 Appendix-J privacy ids**
  (AR/TR/DM/IP/DI/SE/UL/AP) that do not exist in Rev 5 — not gains, despite the code calling
  the class "a gain to review". **18 are genuine bridge gaps** whose CCI text matches the
  claimed control verbatim, two of them STIG-exercised (`CCI-000297 → CM-2(1)`,
  `CCI-002364 → AC-12(1)`). **Two are transposed in the republications**: CCI-002231 and
  CCI-002331 each match the other's claimed control exactly.

### Registry truth
- Two closed FedRAMP records carried `trigger_signal`s naming a state **no FedRAMP page
  publishes** (phase 42 measured this); they now name the timeline entry an observer can check.
  The ARC-AMPE detection mismatch is recorded in the detection block itself, not only in notes.
- The GDPR second-publisher lead is **closed as refuted**: the two on-disk GDPR workbooks are
  keyed by a vendor's own control ids rather than 800-53, are provider-proprietary, and cannot
  serve. GDPR's zero stands and its cause is stated.

### What did not change
No schema, no query surface, no mapping data. The registry edit moved exactly one table digest
(`anticipated_updates`); every other digest is identical to the phase-42 close, and the build is
deterministic across a double rebuild of all 42 tables.

## [0.10.2] — 2026-08-16 (phase 42 — the tidy-up sweep: every missed item, closed with evidence)

PATCH: audit records, registry currency, and ledger hygiene. No schema change, no query-surface
change, no mapping data changed.

### The owed audit, and why it was late
- **`docs/audits/phase-35-adversarial-audit.md`** — the closing adversarial audit the
  regulatory-phase gate required when phase 35 shipped on 2026-08-10. It was never written and
  the omission surfaced only in this phase's missed-items sweep. **This was the second
  occurrence of the identical miss**: phase 34 shipped without its audit and was cited for it
  (finding 34-B, written by phase 35 — which then repeated it). The document says so in its
  first line. Its scope covers the phase-35 registry surface and this phase's own registry
  writes jointly, so the gate is satisfied once for both.
- Results of record: both pins re-fetched live and **byte-identical**
  (`fedramp-consolidated-rules.json` 567,435 B; the govinfo FR PDF 1,067,294 B); 18/18 HIPAA
  Federal-Register verbatims re-assert in the pinned extraction; the FedRAMP re-pin's
  guidance-only claim re-verified by structural recount (KSI 10 families / 46 indicators / 373
  control refs, FRR 17, CTL 14); conformance walk over all 76 records with 0 violations; trap
  sweep clean (its 2 grep hits are the phase-34 audit describing its own sweep); 0 frozen
  `au-cmmc-*` lines touched; commit hygiene clean across all 6 phase-35 commits.
- Adversary result: the pre-named claim — that the ITSG-33 withdrawal and ARC-AMPE downgrade
  chose cadences that would bury both records — is **refuted**; both return as `DUE_REVIEW` at
  2027-02-15. The nuance kept rather than dropped: a "quarterly" `no_fixed_date` record
  resurfaces at ~180 days, not ~90, because the monitor uses twice the poll cadence.
- **`docs/audits/INDEX.md`** — the corrective for a rule that failed twice unobserved: an
  obligation ledger for phases 32→42, with rows 34 and 35 permanently marked `satisfied-late`
  and the discovering phase named. Unfilled obligations appear as visible GAP rows. Honestly
  labelled procedural — no CI-evaluable hook exists without git-history heuristics — but both
  prior misses happened precisely because no list existed. A phase close-out checklist in
  `CHANGE_MANAGEMENT.md` puts the gate question first, and `quality-gates.md` now points at
  the ledger.

### The five elapsed horizon windows, resolved at origin
Each had a window in the past with `last_checked` predating its close; the monitor read clean
only because escalation grace had not caught up.
- `au-fedramp-ready-sunset` (2026-07-28) and `au-fedramp-rev5-bc-temp` (2026-08-10) — one read
  of the authority's own timeline serves both: it still carries each milestone verbatim and
  unamended after the date. Both close **materialized on elapsed, unamended schedule**, with
  the limit stated in the record: FedRAMP publishes no completion notice for timeline
  milestones (the certification-path page 404s, `/legacy` and `/20x` carry no state sentence,
  the marketplace is a JS shell), so this is an inference from schedule elapse, not a state
  confirmation.
- `au-cmmc-rfi` — the comment period closed 2026-08-14; the record closes on that elapse. The
  war.gov release answered **HTTP 403** on re-attempt, so no closure or extension statement
  could be read and the record says so; its due-date sourcing remains THIN. Tied forward to
  `au-cmmc-taskforce-report` (~2026-09-11), whose window this phase does not alter and which
  is the unfreeze event for the deferred ODP baseline work. Frozen CMMC records untouched.
- `au-disa-cci-quarterly` — public.cyber.mil answers HTTP 200 with the DoD Login Portal ADFS
  page, so the recorded SSO wall is **re-confirmed, not resolved**; the July window closed
  unobserved and rolls to 2026-10-31 on the record's own quarterly cadence — a re-date with
  basis, never a date claimed from an authority.
- `au-swift-cscf-2026` — swift.com does not respond from this environment (Wayback errored
  too); DEAD_END re-confirmed and the annual window rolls to July 2027 on the same basis.
  `current_version` stays CSCF v2025: no v2026 publication has been observed.
- `au-fedramp-class-bc` (2026-08-31) has **not** elapsed; it gained only a fresh observation
  and no window change.
- Resurfacing proven, not assumed: the rolled records return as OVERDUE at 2026-12-15 (DISA)
  and 2027-10-15 (SWIFT), i.e. past each record's own grace period.

### Ledger hygiene
- `40-close` pointed at `ac6e2f7`, the sha this session itself flagged `known_good: false`
  (red CI). Added `40-close-clean` → `ea03cf7` as the verified-green phase-40 restore point and
  cross-referenced it from the red entry; noted the true phase-41 close (`08bdd16`) on the
  `41-close` anchor, which names the gates commit. Additive only — no history rewritten. Every
  `known_good: false` entry now names its green alternative.

### What did not change
No mapping data, no schema, no query surface. The registry edit moved exactly one table digest
(`anticipated_updates`) — enumerated, not silent — and the build remains deterministic
(double-build identical across all 42 tables). Record count stays 76; `count_truth` 13 claims
green; benchmark metrics at or above pins.

## [0.10.1] — 2026-08-15 (phase 41 — the phase-40 failure classes, made structural)

### Incident record (researched with proofs; disconfirmed hypotheses listed so they are never re-chased)
- **Red CI at the phase-40 data commit**: the schema version moved in code while four docs
  restating it lagged; `count_truth` blocked in CI as designed. Layered causes: the push that
  shipped it skipped the prose-mandated rehearsal (nothing mechanical prevented that — no
  hook existed), and the 5-file manual bump ritual had opened the same drift window four
  times in one session before finally escaping.
- **False "CI not scheduled" reports**: the session proxy intercepts raw `curl` to
  `api.github.com` with a JSON error body, and the ad-hoc pollers' `.get('workflow_runs', [])`
  made a blocked API indistinguishable from zero runs. Compounded by GitHub's real 1–10 minute
  run-scheduling latency and by the proxy's behavior changing mid-session. Disconfirmed:
  rate limiting (auth-injected limit 15,000, unused) and head_sha filter semantics (the API
  was never reached). Live re-test during this phase: the REST path is blocked with HTTP 403
  even with the shell's bearer token — the GitHub MCP tools are the only working in-session
  path, and the new status reader reports exactly that instead of a false negative.

### Prevention shipped
- **`tools/hooks/pre-push`** runs the full CI rehearsal and refuses the push on failure;
  bypass (`DBZ_SKIP_REHEARSAL=1`) is deliberate and loud. Proven refusing the reproduced
  incident (schema drifted → push blocked) and passing a clean tree. Install is recovery step
  0 and a conventions rule; the rehearsal prints a reminder when the hook path is unset.
- **`tools/bump_schema.py`** bumps the code constant and every doc `doc_claims.json` cites,
  all-or-nothing with ambiguity refusal, finishing with the checker it exists to satisfy.
  Proven: incident reproduced red, tool green across 5 files, refusal leaves nothing written.
- **`tools/ci_status.py`** — error / empty / data as distinct exit codes; the captured proxy
  payload is pinned in a selftest wired into CI and the rehearsal mirror; `--wait` prints the
  scheduling-latency expectation up front; sha filtering is client-side by full-sha prefix.
- **Drift invariant 16** fails if the hook is deleted, non-executable, or edited to skip the
  rehearsal (proven red against a defanged hook). Conventions gain a session-mechanics
  section; the invariant count restatements move 15 → 16.

### What did not change
No data, no schema (3.18 stands), no query surface. `grc.db` content is untouched by this
phase; the build was not re-run because nothing feeding it changed.

## [0.10.0] — 2026-08-14 (phase 40 — the SCF fan-out witness)

Phase 39 closed calling the single-publisher ceilings "data acquisition, not code." One unchecked
assumption made that premature: the SCF workbook on disk carries 45 framework mapping columns, and
only the 800-53 column had ever been loaded.

### Added
- **`scf_composed_edges`** (schema **3.18**) — 8,626 edges from SCF→X columns composed with
  SCF→800-53, column roles pinned in `source_manifest.json` (`structure.fanout_columns`), every
  token gated by an existing normalizer (unparseable tokens dropped AND counted: SOC 2's 788
  are `-POF` points-of-focus, correctly rejected). New normalizers: `normalize_gdpr_article`
  ('Article 24.2' → '24(2)'), `normalize_172_id` ('3.1.2e' → '03.01.02E', version-caveated in
  the manifest note).
- **`w_scf_composed`** — supports-only witness (the X→800-53 composition is ours, not SCF's;
  same honesty rule as `w_olir_composed`), matched per anchor. Results: **SOC 2 0→69 confirmed**
  (SCF + STIG + confirmed anchor; spot-check: A1.1 availability → SC-5 denial-of-service CCIs),
  **800-172 r3 0→5**, GDPR 96→303 corroborated, CCM 318, overall confirmed 23,339→**23,485**.
- One more F-6 instance fixed en route: projection SOC 2 natives carry an `AICPA 2017 ` prefix
  the SCF side lacks; `corroboration_key` gained a SOC 2 branch through `normalize_tsc_id`.

### Honest ceiling that remains
GDPR stays 0 confirmed: the SCF witness is control-granularity and GDPR has no CCI-level witness
anywhere, so `corroborated` (303) is its ceiling until a second publisher maps it to 800-53.

## [0.9.0] — 2026-08-13 (phase 39 — confirmation-layer remediation and correction)

Remediates why 286,642 of phase 38's pairs were unconfirmed — and corrects phase 38's own
headline in the process.

### Corrected
- **Phase 38's 53,046 confirmed was overcounted.** Its publisher witness was anchor-blind:
  two publishers of a control were credited to every CCI the control could reach. Publishers now
  count **per anchor control** (both must have placed the coarse control on the same 800-53
  control the CCI hangs under). **The number of record is 23,339 confirmed** of 180,413 pairs.
  Recorded here and in `docs/BENCHMARK.md`, never smoothed over.

### Fixed
- **FedRAMP graded as a foreign framework** — 252,917 of the 286,642 reachable rows (88%). It is
  now derived from the owner's own `baseline_low/moderate/high` flags per the master surface's
  documented design: 2,777 authoritative rows (302 confirmed via STIG exercise, 1,840
  corroborated), witness `w_baseline_authoritative`.
- **Publisher counting defeated by the F-6 id-dialect class** — exact-`native_id` keying meant
  CMMC's two publishers never met (0 multi-publisher natives exact vs 17 via
  `spine_normalize.corroboration_key`; ISO 4 vs 23). Counting now joins through the coarse key
  (witness join only; stored ids untouched). CMMC gains its first confirmed rows (55).

### Added
- **`w_olir_composed`** — NIST-published X↔CSF-2.0 OLIR pairs composed with NIST's own
  CSF-2.0→800-53 mapping, matched per anchor. Control granularity: supports, never carries.
  CSA CCM 0→247 confirmed, NIST SP 800-171 r3 0→99, SCF 0→63; reachable overall
  286,642→27,145.
- **Gate extensions (check 19)**, both proven red against tampered data: FedRAMP rows must carry
  the baseline witness; control-granularity witnesses (consensus/baseline/olir) still cannot
  carry a confirmation alone. Confirmed floor re-pinned at 18,000 (measured 23,339).

### Honest ceilings (stated, not patched)
`weak` (28,898) is an anchor-layer fact needing new anchor witnesses; GDPR / SOC 2 / 800-172 r3
stay at 0 confirmed until a second mapping publisher exists; STIG coverage of 539 CCIs is
verified complete. All three are data-acquisition items, not code.

## [0.8.0] — 2026-08-13 (phase 38 — the framework→CCI confirmation layer)

Delivers the repository's stated objective: converge every framework onto **confirmed CCI
mappings** rather than reachable ones.

### Added
- **`framework_cci_confirmation`** (schema **3.16**) — one row per (framework, native_id,
  cci_id) with independent witness counts and a derived verdict. **478,610 pairs:
  53,046 confirmed · 81,933 corroborated · 286,642 reachable · 56,989 weak.**
  Before this, frameworks reached CCIs only by transitive join (framework → r5 sub-part →
  `cci_bridge`), which asserts a path exists but never that anyone checked it. The convergence
  machinery already existed one layer down (`cci_mapping_corroboration`, 4,285 confirmed
  CCI→800-53 anchors); nothing had ever combined it with the framework layer.
- **Witnesses, independent by construction** (`cross-mapping/engine/cci_confirm.py`):
  a second mapping publisher on the same anchor · the CCI's own anchor being multi-witness
  confirmed · a STIG rule actually exercising the CCI · another framework agreeing via
  consensus · sub-part precision. The consensus witness matches at control granularity, so it
  may support a confirmation but never carry one alone.
- **`dbz_query cci --framework <fw> [--verdict ...]`** — per-framework verdict breakdown and
  per-CCI witness lists. Output states plainly that `reachable` is not a mapping.
- **`validate_spine` check 19** — verdict vocabulary exact, derivation total, every `confirmed`
  row has a confirmed CCI anchor plus a CCI-level witness plus a traceable witness list, and a
  confirmed-count floor pinned at 40,000 (measured 53,046). Proven to fail two ways against
  corrupted data before acceptance.

### Notes
- Frameworks with one publisher and no STIG-exercised CCIs cap at `corroborated` — CSA CCM,
  GDPR, CMMC 2.0 and FedRAMP r5 report 0 confirmed. That is the honest ceiling of their present
  evidence (phase-36 finding F-4), not a defect, and it is visible rather than implied.
- A label-dialect bug was caught during development: consensus writes `CIS v8` / `SOC 2 (TSC)`
  while the projection writes `CIS CSC v8.0` / `SOC 2`, so the consensus witness silently never
  fired. Fixed by routing through the master surface's own canonical map — the same F-6 class
  phase 37 addressed.

## [0.7.0] — 2026-08-13 (phase 37 — remediation of the phase-36 accuracy audit)

Closes all eleven findings (F-1 … F-11) from `docs/audits/phase-36-master-accuracy-audit.md`,
plus one found during remediation (F-12). Per the approved plan: **no master or projection row
was deleted and no tier was re-rated** — the hub block is annotated, not pruned.

### Fixed
- **F-7 (HIGH) — prose stored as control identifiers** (`49047ee`). `cmmc171` wrote the 800-171A
  assessment-objective *sentence* into `native_id` at the top confidence tier (0.95); 100% of
  page 1 of the obvious 800-171 query showed sentences where ids belong. The crosswalk has no
  800-171 id column, but the CMMC practice id encodes the same objective, so
  `normalize_171_objective_id()` derives `AC.L1-3.1.1(a.)` → `3.1.1[a]` — the exact form the
  HITRUST hub already used. Shared native ids between authority and hub went **0 → 313**, which
  also created the second hub-vs-authority comparison now recorded in `docs/BENCHMARK.md`.
  Prose stays recoverable: every row carries `source_file`/`source_sheet`/`source_row`.
- **F-2 (MED) — bare-zero answers** (`6bb93f0`). A resolvable pair with no stored rows returned
  `0 master mapping(s)` while `overlap` answered 6.8% for the same pair. It now returns a
  structured gap with measured stored-pair coverage and a pointer to `overlap`. A filter that
  empties a *stored* pair reports that distinctly — claiming "not stored" would be false.
- **F-8 (MED) — discarded composition evidence** (`53e0bd3`). Cross-framework edges now carry
  the shared 800-53 anchors both sides project onto: **117 → 1,379 rows**. Spoke edges are
  deliberately excluded — there the control is an endpoint, not a shared pivot.
- **F-1 / F-4 / F-5** (`146ec31`). The README no longer calls the surface "any-to-any" (60 of
  595 pairs are stored); README and architecture doc now disclose that 84.6% of edges derive
  from one licensed artifact; the CCM manifest entries say 1,683 distinct pairs, not 1,684
  (the source repeats `LOG-09 → AU-12(3)`).
- **F-6 (HIGH) — the hub block was almost unauditable** (`8153945`). Authority and hub wrote
  incompatible id dialects, so 82,825 hub rows could be checked on 52 native ids.
  `corroboration_key()` collapses both sides to a shared granularity for comparison only —
  never overwriting stored ids. Frameworks clearing the 20-shared-id bar: **1 → 3**.
- **F-12 (LOW, found during remediation)** — 18 HITRUST control stems appear under 2+ title
  variants ("User Auth. for Ext. Connections" vs the full title), fragmenting 242 rows. The
  coarse key collapses them for corroboration.

### Added
- **F-10 (HIGH, keystone) — the edge-semantic model** (`8576485`). Schema **3.15** adds
  `edge_semantic` to `master_mappings`: `equivalent` / `supports` / `co_referenced` / `informs`,
  derived mechanically with no per-edge judgment, vocabulary in `framework_vocab.json`. Exposed
  in `master` output and as `--semantic`. **12.6% of edges are source-stated shared work; 82.6%
  are hub co-references.** A correction landed mid-phase: authority is read from the *tier*, not
  `relationship_basis`, because NIST's own OLIR exports arrive as `derived_cardinality` and were
  being demoted to `informs` (that fix moved the figure from 9.5% to 12.6%).
- **F-11 / F-9 (HIGH) — two labeled overlap metrics** (`82e2567`). The shipped percentage keeps
  its value but is renamed **co-reference** (topical association). A new **shared work %** counts
  only source-stated edges. SOC 2 × ISO: co-reference **54.2%** (unchanged), shared work **0.0%**
  — SOC 2's projection is 100% hub-derived, so no source states shared work for that pair, and
  the output says so explicitly rather than hiding the zero. ISO × CSF 2.0 shows 46.8%. Overlap
  also now discloses per side how much of a footprint is single-source.
- **Regression gates** (`bb47665`), each **proven red against corrupted data** before acceptance:
  identifier hygiene (F-7), semantic totality + the co-membership conflation guard (F-10),
  anchor retention (F-8), auditability floor (F-6). Plus scenario 12 pinning both overlap
  metrics.

### Not done (deliberate, per the approved plan)
- **No pruning and no re-tiering** of the 82,825 hub rows. F-9's 63.2% is conditional on a
  semantic that this phase only just defined, and deleting licensed-source data on a 65-edge
  self-labeled sample would be indefensible.
- **The consensus stratum (3,422 rows) remains unadjudicated** — phase 36 labeled 65 of 220
  sampled edges. Since the flagship stored pairs are consensus-tier, this is the highest-value
  next audit.
- **No independent re-label** of F-9's sample; the author-as-labeler limit stands.

## [0.6.0] — 2026-08-10 (phase 35 — alias-resolution correctness, the missing phase-34 audit, carried-over regulatory items)

Phase 34 closed the phase-33 findings as written, but B-1 was written as an instance and the
class was never swept. Phase 35 swept it, and the class was worse than the original finding.

### Fixed
- **Alias resolution — one authority, no accidental substring matches** (`ae99dd7`). dbz had
  three query-time resolvers with three hand-maintained alias dictionaries, each ending in a
  "first substring match wins" fallback over a SQL-ordered list. Measured consequences:
  `master --framework-a csf` answered **HITRUST CSF** (because that label sorts before
  "NIST CSF") while `overlap` answered **NIST CSF 2.0** — one word, two frameworks, one
  session; `fedramp` resolved to a label with zero master rows (a silent empty answer);
  `nist-csf` errored as unknown on master while working elsewhere. New
  `cross-mapping/engine/framework_alias.py` is the single authority: the registry decides,
  declared-ambiguous terms raise with their candidates instead of guessing, family groups fan
  out only where an external instrument makes two labels one thing, and the substring fallback
  collects every match and rejects cross-family hits. `framework_vocab.json` → 1.2.0 with
  `ambiguous`, `data_gaps` and `family_groups` blocks (the CMMC group moves out of code).
  **Breaking for one input:** bare `csf` now errors and lists its three candidates.
- **Sibling disclosure** (`c84f509`) — a scoped answer is no longer mistaken for the whole
  family: `iso` names the ISO/IEC 27001 and 27002 labels it did not cover with measured row
  counts, plus a `sibling_labels` JSON key. Matching is by standard number, so unrelated ISO
  standards are not swept in. Version-ambiguous labels are still never merged.
- **FedRAMP consolidated rules re-harvested** (`55ffa93`) at 2026.07.14.01, closing drift the
  horizon record had carried since July. Diffed before re-pinning: guidance-only revision, KSI
  families/indicators/control references byte-for-byte unchanged, so no pinned count moved.
- **The two five-month-overdue horizon records resolved** (`1b7b8f3`) by chasing both at their
  authorities. ITSG-33 still serves the December 2014 Rev-4-based annex, so the unfounded
  March window is withdrawn; the ARC-AMPE watch is downgraded to THIN after its own detection
  URL proved to track the CMS ARS baseline. No date replaced by a guess.
### Added
- **Alias contract test** (`ae99dd7`) — `cross-mapping/tests/test_alias_contract.py` asserts
  agreement, non-emptiness, explicitness and declared ambiguity across all three resolvers,
  and pins the four historical regressions by input string. Proven red on the pre-fix code
  (15 failures) before the fix landed. Wired into `ci_rehearsal` and `standards-watch`.
- **HIPAA NPRM regulatory-text verbatims** (`3399a48`) — all 18 proposed items now quote
  90 FR 898 itself, closing the follow-up two phases could not reach. hhs.gov refuses this
  environment; govinfo serves the Federal Register original, pinned by sha and extracted with
  pdfminer.six 20260107. Each quote is labelled regulatory text or preamble and was
  mechanically asserted present in the pinned document before being written.
- **Phase-34 adversarial audit** (`7737b26`) — `docs/audits/phase-34-adversarial-audit.md`,
  required by the regulatory-phase gate and missing when phase 34 closed. It records both the
  omission and that phase 34's own changelog entry read as a class fix when only the CMMC
  instance was closed.

## [0.5.1] — 2026-08-09 (phase 34 — remediation of the phase-33 audit findings)

Phase 33 was a read-only independent audit of the phase-32 series (8 commits / 37 files):
0 CRITICAL, 1 HIGH, 4 MED, 5 LOW. Every regulatory claim, pin, and count held; this release
fixes the defects it did find. Audit record: the phase-33 log; findings referenced by id.

### Fixed
- **B-1 (HIGH)** (`49aedce`) — master-surface CMMC alias resolution. `master --framework-a
  cmmc` returned 0 rows while 105 SOC 2 × NIST SP 800-171 r2 master pairs existed: the
  `framework_labels` authority maps an alias to ONE canonical, but CMMC's program reality
  spans two labels (Level 2 assesses against 800-171 r2 per the May-2024 class deviation).
  `_MASTER_FW_GROUPS` + `_master_fw_set()` fan the alias out across both labels in pair and
  control modes, rows keep their true labels, and the header names the fan-out and its
  basis. Scenario 11 pins the answer (measured 105, band ±15%) plus the presence of
  r2-labeled rows. The dead alias entries phase 32 added to the legacy `_resolve_fw` map
  (which serves only `unified_mappings`-backed commands) are removed.
- **C-1 / C-6 / C-2 (MED, LOW, LOW)** (`38b69f0`) — horizon record repairs: `au-iso-15408`'s
  empty provenance URL now cites the attempted portal hop (with `source_urls`/`detection`
  filled); `au-fedramp-class-a`'s baseline version reflects the opened pipeline instead of
  "pre-pipeline" on a materialized record; `au-eu-ai-act`'s artifact names the obligations
  milestone its closing verbatim proves, with the acts-side evidence recorded.
- **G-1 (MED)** (`cd1449c`) — the audit-harness gap that let the empty URL ship is now
  mechanized: `load_anticipated_updates()` hard-fails on a non-http provenance URL in every
  terminal state, and `regulatory-provenance.md` §2 states that DEAD_END exempts content
  matching, never the citation. Validation tightening only — schema stays 3.14.
- **F-2 (MED, pre-existing)** (`28ff354`) — the monthly `standards-watch` workflow failed on
  every fresh checkout (`FileNotFoundError` on the generated catalog) and, once past that,
  would have built a silently degraded database (no OSCAL cache → `oscal_structural`
  controls=None, 0 objectives). Both build products are now produced on the runner. The
  failure and the fix were reproduced locally under hidden artifacts first;
  `tools/ci_rehearsal.py --standards-watch` makes that second fresh-checkout mode testable.
- **C-4 / G-2 / B-2 / NOTE-D3 / F-1 / A1 / E2** (`74f022a`) — record-keeping: the deliberate
  drop of `chg-dfars-clause-renumbering-2026` is recorded with its provenance-floor reason;
  the phase-32 audit doc's coverage sentence is corrected (75 of 76 fetched) and carries the
  phase-33 follow-up; the secret-scan docstring enumerates all three allowlisted prefixes;
  the ODP baseline pins the extractor version proven to reproduce it; the runbook gains the
  learned phase-hygiene rules (message length, anchor ordering, recording scope drops) and
  the rehearsal's coverage limit; three stale date labels now match their commits.

## [0.5.0] — 2026-08-09 (phase 32 — CMMC + HIPAA regulatory absorption, provenance hardening)
### Added
- **32-0** (`1cf7aa3`) — `protocol-layer/regulatory-provenance.md`: claim provenance blocks
  (URL + retrieved_at + verbatim + support label), terminal-state vocabulary, citation-loop
  escape, mutation-check intake, an 11-item GRC domain-trap list, recall/injection rules, and
  a recorded non-adoption boundary (decomposed from the maintainer's research-provenance
  skill v1.5.2 — 7 pieces adopted, the rest skipped with reasons). `quality-gates.md` gains
  a permanent regulatory-phase closing gate (adversarial audit with mandatory adversary
  output + residual risk).
- **32-2** (`c1f5f3b`) — CMMC posture absorbed on origin evidence: six suspension-aware
  horizon records (Phase 2 suspended 2026-07-13; RFI closing 2026-08-14; task-force report
  window; Phases 3/4 frozen; 171r3 transition signal), `au-nist-800-172` closed as
  materialized, `dfars-cyber` rescheduled high-priority with a clause-accurate label, new
  `cmmc-32cfr-170` feed (feeds 160→161), two FR agency slugs fixed, suspension + ODP memo
  PDFs sha-pinned. DB schema 3.14: enum-enforced provenance columns on
  `anticipated_updates`; eCFR loader gains Part 170 + a heading-extraction fix.
  *Deliberate scope drop:* the planned `chg-dfars-clause-renumbering-2026` changelog entry
  was NOT written — the Feb-2026 class-deviation memos stayed bot-walled at acq.osd.mil, so
  under the provenance floor there was nothing citable to record. The renumbering is carried
  in the `dfars-cyber` feed label as deviation clauses (not CFR changes); the entry gets
  written when a DPCAP memo is read at origin.
- **32-3** (`1a8ca33`, allowlist fix `4af0bf9`) — CMMC ODP transition baseline frozen per
  the user gate (WAIT for the task-force outcome): diff-ready memo text extraction, full
  32 CFR 170 XML as of 2026-08-01, comparison procedure in `docs/cmmc-odp-baseline.md`.
- **32-4** (`075dc74`) — HIPAA horizon refresh: `au-hipaa` carries the OMB 202510 July-2027
  projection at low confidence/CONTESTED, the `hipaa` feed records the NPRM's full identity
  (90 FR 898, RIN 0945-AA22, docket HHS-OCR-2024-0020, 4,747 comments), and
  `docs/hipaa-security-rule-transition.md` enumerates the 18 proposed items with the repo
  trigger map. Announcement pipeline slug repairs (HHS/CISA/NYDFS), 11 false positives
  pruned, diverged analyzer xlsx resynced, sync invariant 15 (skill-asset hash guard).
- **32-1** (`670d9a2`) — Provenance backfill: all 68 legacy horizon records verified at
  their primary sources and stamped (56 WELL_SUPPORTED/ORIGIN; unreachable primaries
  recorded THIN/DEAD_END with the obstacle named). Ten drift repairs, including a
  two-year-stale IR 8477 watch, the OWASP LLM Top 10 2026 edition, the EU AI Act GPAI
  milestone, Bill C-27's lapse, and the passed CIRCIA final-rule window.
- **32-5/6** — docs/counts sync (this entry), VERSION 0.5.0, and the closing adversarial
  audit `docs/audits/phase-32-adversarial-audit.md` required by the new quality gate.
### Fixed
- Secret-scan allowlist (`4af0bf9`): verbatim regulatory-text paths (CFR JSON, pinned DoD
  documents) join the reasoned prefix allowlist after the 32 CFR 170 org-mailbox finding
  turned CI red on `c1f5f3b`/`1a8ca33`; green from `4af0bf9`.

## [0.4.1] — 2026-07-18 (phase 31 — 48-hour-audit remediation)
### Fixed
- **31-3** (`d8ac868`) — `tools/ci_rehearsal.py`: one-command local reproduction of the CI
  condition (artifact stash + verbatim health-workflow steps + guaranteed restoration +
  workflow drift warning); named in the merge bar as the mandated pre-push step. Closes the
  audit's FINDING-3 failure class (fresh-checkout divergence).
- **31-2** (`9764f7c`) — Determinism-digest coverage derived from `sqlite_master` (40 content
  tables, 22 newly covered, all verified deterministic; reasoned exclusions only; legacy
  digests byte-identical). Closes FINDING-2 and eliminates its hand-kept-list mechanism.
- **31-1** (`54141d5`) — Prefix-scoped, reasoned secret-scan allowlist for the
  output-validator fixture directory; selftest proves the allowlist is path-scoped, never
  pattern-weakening. Closes FINDING-1 (full-range scans now clean).

## [0.4.0] — 2026-07-18 (phase 30 — hardening)
### Fixed
- **docs-sync sweep** (`861bb09`) — internal documentation brought fully in sync with the
  phase 28–30 additions: README doc table, runbook/quality-gates/STATE/merge-bar gate-battery
  descriptions, sync_check docstring (14 invariants), skill MAINTAINER post-step notes, and
  atom input schemas for the new evidence-state/overlay flags (export regenerated).
### Added
- **30-5** (`d2a5a99`) — Staged-diff secret scan + CI backstop with a recorded policy boundary;
  fail-closed data-at-rest placement rules; URL provenance promoted to blocking;
  `docs/persona-audit.md` (three-persona UX gap audit).
- **30-4** (`c3192c8`) — Crawl-seed citation graph: `parent_source_id` on every candidate,
  `--accept` review stubs in `crawl_candidates.json`, `--prune-report` with blocked-is-not-gone
  protection.
- **30-1/2/3** (`5eaa48f`) — `tools/metrics.py` -> generated `docs/METRICS.md` (sync invariant
  13); ten-scenario pinned end-to-end battery in the standards-watch build; single-writer
  `tools/registry_io.py` (invariant 14) + `tools/registry_currency.py` sha baselines.

## [0.3.0] — 2026-07-18 (phase 29)
### Added
- **29-4** (`8ef71f2`) — Evidence-state ladder on `master_mappings` (schema **3.13**): derived
  corroboration state per edge (`oracle_confirmed` / `cross_validated` / `columns_aligned` /
  `asserted_by_source`), `--evidence-state` filter, validate_spine check 14. MINOR (additive
  schema bump); containment invariants unchanged.
- **29-3** (`d5200d9`) — `protocol-layer/` (evidence standards, conflict protocol, quality
  gates, failure recovery — each rule cited to where it already lived) +
  `cross-mapping/engine/score_output.py` deterministic hard-fail-first verdicts; scorer weights
  machine-cross-checked between doc and code.
- **29-2** (`ea917cd`) — `implementation/gpt/api/` generated OpenAI-function schemas for the six
  core operations + `tools/export_openai.py`; drift-guarded (sync_check invariant 12); scope
  recorded as contracts-not-hosted-service.
- **29-1** (`ae0f772`) — Context overlays (`canonical-sources/overlays/` + resolver +
  `--overlay` on master/overlap/scope/search) with always-disclosed suppression counts.

## [0.2.0] — 2026-07-17
### Added
- **28-2** (`2be8088`) — Machine-checked doc numbers (`tools/count_truth.py` +
  `canonical-sources/doc_claims.json`; drift blocks the health audit) and URL-host provenance
  for code literals (warning severity, `tools/url-allowlist.json`). The first run caught a
  stale master-surface framework count (23 → 35) in README and the architecture doc.
- **28-1** (`4c81aa8`) — Measured accuracy benchmark against the production oracle crosswalks
  (`cross-mapping/tests/benchmark_oracles.py`, `docs/BENCHMARK.md`): ER-level P/R/F1 plus
  spine-level oracle coverage / corroboration rate, measure-then-pin regression thresholds,
  and a fresh-build CI check in the standards-watch workflow.
- **28-5** (`650aa66`) — Deterministic output validator (`tools/output_validate.py`):
  id-reality vs the catalog, unsourced-number and overconfident-tier checks, reused leak
  patterns; fixture selftest in pre-commit; advisory post-step notes in the analyzer and
  orchestrator skills.
- **28-4** (`70e807e`) — `fetchkit` shared fetch layer (per-host rate governing, circuit
  breaker, conditional-GET + sha cache, always-labeled Wayback fallback) adopted by the
  framework monitor and the standards-refresh fetch stage; offline unit tests.
- **28-3** (`b6a9f84`) — This changelog, `STATE.md` (live status + phase ledger + recovery package),
  `changes/CHANGE_MANAGEMENT.md` (versioning + merge bar + rollback), and
  `ledger/snapshots.json` (known-good rollback anchors). `VERSION` 0.1.0 → 0.2.0.

## [0.1.x] — 2026-07-03 … 2026-07-14 (phases 19–27)
- **27** (`1007fd8`, `8e06bb8`) — README/architecture rewritten around the unified graph;
  health-audit build-artifact reference exemption fixed the failing CI check.
- **26** (`f27f088`) — FedRAMP Consolidated Rules 2026 as a contained confirmation layer:
  complete canonical dataset + 11 schemas + narrative corpus; 46 KSIs with FedRAMP's own 373
  KSI→800-53 edges; version-transition framing (spine unchanged).
- **25** (`4f9fff1`, `651ad4c`) — Source universe audit + tiered broadening; OLIR-hub composed
  edges (1,870); verification corrections from an adversarial review.
- **24** (`005b745`) — Horizon scanning: 70 anticipated-revision records, no fabricated dates.
- **23** (`6aeac84`) — Standards-currency refresh: monitor repair, 800-53 r5.2.0 re-pin.
- **22** (`98eea12`) — Full DISA CCI dictionary (5,137) with multi-source corroboration.
- **21** (`e6449ab`) — STIG application layer: 383 benchmarks / 19,667 rules as CCI evidence.
- **20** (`eabfc21`) — SCF + CCM projected onto the spine (owner_stated tier).
- **19** (`d8c0d15`) — Master mapping database: private-sector audits merged into one
  any-to-any surface with the 7-tier provenance vocabulary.
- Phases 1–18: catalog ingestion, ER overlap engine, spine normalization, CCI/ODP bridge,
  consensus detection, publication hygiene, health auditor + golden sets (see `docs/`).
