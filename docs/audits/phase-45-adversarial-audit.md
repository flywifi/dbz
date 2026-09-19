# Phase-45 closing adversarial audit — 2026-09-19

**Scope.** The phase-45 seed-source currency sweep and its writes: the
`anticipated_updates.json` batch (10 record updates + 1 new record, 76 → 77), the FedRAMP
consolidated-rules re-pin (2026.07.14.01 → 2026.09.13.02) with its three metadata surfaces
(this phase makes the first writes to `feed_registry.json` since the closing gate has
existed), the drift-classifier fix in `tools/standards_refresh.py`, and the elapsed-open
horizon lens. Written to satisfy the regulatory-phase closing gate
(`protocol-layer/quality-gates.md`) against this phase's own diff.

**The headline finding is about the auditor, not the data:** the monthly drift check's
"no drift" verdicts for August *and* September were structurally vacuous. The classifier
copied each feed's **stored** `artifact_status` into its classification
(`standards_refresh.py`, `cls = status`), so `registry_stale` was unreachable no matter what
happened upstream. SCF 2026.2 shipped 2026-07-08 — two days *after* the scf feed's
`last_verified 2026-07-06` — and sat behind a "current" echo for ten weeks. The August
sweep's "no drift" conclusion is hereby retroactively downgraded from evidence to noise for
every feed row (the August *horizon* and *byte-comparison* checks were real and stand).

---

## Pass 1 — source integrity

Every date and version this phase wrote traces to an origin fetched this phase:

- **CRA Art. 14** — EUR-Lex `eli/reg/2024/2847/oj`, verbatim "incidents having an impact on
  the security of products with digital elements, which should apply from 11 September 2026"
  re-confirmed unamended 2026-09-19 (sweep artifact `eurlex-cra.txt`). Statutory elapse →
  `materialized`.
- **FedRAMP Class B&C** — fedramp.gov timeline, all 8 milestones verbatim-unchanged incl.
  "August 31, 2026 FedRAMP 20x Class B & C pipeline opens" (`fedramp-timeline.txt`). The
  phase-42 convention (an unamended timeline past its date closes as occurred) is cited in
  the record.
- **CMMC task force** — the 2026-09-11 window (a *derived* date: 2026-07-13 + 60 days,
  derivation recorded in the original record) elapsed with **no public outcome**. war.gov
  remains a 403 bot-wall. The only signal is secondary (DefenseScoop, 2026-09-09: DoW CIO
  Davies, "over 1,100 responses", "over 10,000 pages", no timeline) — recorded **THIN**,
  and the record reopened as `no_fixed_date` rather than deriving a successor date. The ODP
  baseline and the CMMC suspension records stay frozen; the unfreeze condition (a published
  outcome) has not occurred.
- **PCI DSS** — origin blog post
  `blog.pcisecuritystandards.org/request-for-comments-pci-data-security-standard-pci-dss-v4.0.1`
  (2026-06-03), verbatim "PCI SSC is beginning the next iteration of PCI DSS…". ORIGIN.
- **HITRUST v11.9** — origin blog post
  `hitrustalliance.net/blog/market-feedback-supports-hitrust-updates-for-ai-accelerated-vulnerability-risk`
  (2026-07-31), verbatim "…refining the proposed updates for inclusion in HITRUST CSF v11.9
  later this year". ORIGIN; window 2026-10-01..2026-12-31 is the announcement's own "later
  this year", not a derived date.
- **SCF 2026.2** — two independent origins: the GitHub releases page (release "2026.2",
  08 Jul) and securecontrolsframework.com (verbatim "With the 2026.2 release, numerous
  controls now include a list of compensating controls"). The atom feed and the releases
  HTML both 403 scripted fetches — recorded in the new `au-scf` record so the next reader
  does not re-chase them.
- **FedRAMP rules 2026.09.13.02** — fetched from the declared source
  (`raw.githubusercontent.com/FedRAMP/rules/main/fedramp-consolidated-rules.json`) twice
  in the same day — once for the sweep diff, again at pin time — byte-identical
  (sha256 `64915d88e72353c9…` both times) before pinning.
- Walls degraded honestly, never promoted: parl.ca 403 (new), bcn.cl JS shell — obstacle
  text recorded, no status invented, the Chile Dec-2026 window kept rather than extended.

## Pass 2 — claim support

The load-bearing numeric claims of this phase, each with its probe:

| Claim | Probe | Result |
|---|---|---|
| FedRAMP re-pin adds/removes **zero** entities | entity-id diff over KSI/FRR/CTL/FRD (`ws2_diff_final.py`) | 190 → 190; +0 −0 ~159 |
| KSI 10 families / 46 indicators / 373 control refs unchanged | recount in both files | identical; post-build `fedramp_ksi` 46 rows / `fedramp_ksi_controls` 373 rows |
| Loader-visible delta = 1 rule statement | field trace vs `spine_loader.load_fedramp_rules` consumption set | only `CCM-OCR-AVL.statement` ("(if applicable):") is loader-visible; `terms`/`timeframe_*`/`reference_url`/`updated` are not consumed |
| No normative-field changes | extraction over `force`/`controls`/`affects` on all 159 changed entities | NONE |
| Registry 76 → 77, README restated | `count_truth.py --check` after the edit | green, 15/15 claims with build present |
| Elapsed-but-open windows = 3 before the batch, 0 after | `elapsed_open()` lens vs the sweep's independent enumeration | exact agreement (fedramp-class-bc 19d, cra-reporting 8d, cmmc-taskforce 8d); 0 at HEAD |
| Double-build determinism after re-pin | two sequential builds, `table_digests` compare | identical |

Two *policy-relevant* upstream shifts ride in loader-invisible metadata and are therefore
documented rather than silently re-pinned: the Rev5 continuity grace default moved
**2027-01-01 → 2027-07-01** (`FRR/CPO info .rev5.effective.date.grace.default`) and
**Class A was dropped** from the CSF (`FRR/CPO .rev5.subsets`) and CCL (`FRR/FRC .subsets`)
applicability classes. These are this auditor's readings of the JSON paths cited — FedRAMP
published no prose announcement we could find; a reader can re-derive both from the pinned
file in one `jq` expression.

## Pass 3 — chain / mutation integrity

- All registry writes went through `tools/registry_io.py`; `roundtrip_identical` was
  asserted **before** every save (formatting noise = zero; the diffs are semantic only).
- Provenance blocks carry `support` ∈ {WELL_SUPPORTED, THIN} honestly: the CMMC reopening
  is THIN (one secondary); everything else in this batch is origin-verified.
- The GRC domain traps (`regulatory-provenance.md` §5) were swept: no CMMC version
  invention (the task-force record says "review in progress", not an outcome); the
  suspension-vs-rescission distinction is restated in the reopened record; no 800-171
  r2/r3 conflation entered any note.
- Mutation check on the two closures: the closing verbatims are the same sentences the
  records were opened on (CRA: the Art. 14 application date; FedRAMP: the timeline
  milestone), re-fetched — not recalled, not paraphrased.

## Pass 4 — adversary output (mandatory)

**The single claim most likely to be wrong:** *"the FedRAMP 2026.09.13.02 re-pin is
guidance/metadata-only."* The evidence that would overturn it: a semantic obligation change
hiding in the 159 `terms`-only entity diffs or in FRR text classified as metadata. Where it
would be found: a line-by-line read of the FRR statements in both pins (the structural probe
compared values, not meanings). What was done about it: the normative fields
(`force`/`controls`/`affects`) were extracted and compared — none changed — and the three
`timeframe_*` additions were checked against their statements' prose (each encodes a
duration already stated verbatim). The residual (meaning drift inside unchanged-id,
changed-`terms` rows) is named below rather than dismissed.

**Second candidate:** the four working-note errors this phase's own research produced and
then caught (planning-standard §7 — corrections louder than claims):
1. "New FRD-MAY term added" — **false**; FRD-MAY exists in neither pin. Artifact of a
   positional array diff whose indices shifted.
2. "257 changed + 57 added leaves" — same artifact; the entity-level truth is 159/0/0.
3. "au-pci-dss cv 'v4.1' is stale" — **false**; the stored cv was already the correct
   v4.0.1.
4. "au-owasp-llm-top10 needs a currency update" — it was already `materialized`; only the
   detection URL migrates.
The mechanism in all four: reading an intermediate diff or a remembered note as if it were
the record. Each was overturned by re-probing the primary artifact before the plan was
written.

**Third candidate:** the classifier fix itself. Its disconfirming probe ran and **found a
real bug in the prototype** — plain substring matching would let live tag `2026.1` satisfy
pin `2026.1.1`, hiding exactly the drift class the fix exists to catch. Fixed with a
boundary-guarded match (the `count_truth._patterns_for` idiom) and re-proven; the case is
pinned forever in `--selftest-release-check` (6/6, including the red fixture that replays
the SCF incident verbatim and the fail-closed 403 case). The first full `--check` with the
fix live (2026-09-19, in-session) behaved exactly as designed: the 19 `github_release`
feeds degraded to `check_failed` with `HTTPError:403` reasons (the session proxy blocks
`api.github.com`; CI authenticates with `GITHUB_TOKEN`) instead of echoing "current" —
`check_failed` rose 1 → 22 in the summary, which is the honest picture this environment
can see. The elapsed-open lens's red proof ran against the pre-phase registry pulled from
git (`1e69a7d`): exactly the three known-elapsed windows fire (19d/8d/8d past, every one
`grace_state: watching`), the 2026-08-30 negative control is empty, and the post-batch
registry reads 0.

## The SCF 2026.2 ingest — scoping only (deliberately not done here)

SCF is load-bearing: `scf_direct` contributes 1,117 edges, the SCF fan-out witness covers
8,626, and SCF is the largest consensus voter (−5,378 on removal, phase-43 measurements).
2026.2 adds a Quantum Security domain, per-control compensating-controls lists, and an STRM
refresh across ~252 framework columns. An ingest is therefore a dedicated phase that must,
in order: re-run the 2026.2 xlsx through `standards_refresh.py --gate`'s projection
regeneration, measure the scf_direct edge delta and the consensus voter re-tally *before*
accepting them, and re-run the oracle benchmark. Until then the feed registry says, in one
row, both truths: registry currency 2026.2, on-disk artifact 2026.1.1.

## Residual risk (never an all-clear)

- The CMMC task-force status rests on one secondary source; war.gov's bot wall means the
  primary remains unread. If DoW published an outcome somewhere we did not look, the frozen
  ODP baseline is stale and this phase would not know.
- The 159 `terms` diffs were classified structurally. A semantic shift expressed as a
  changed defined-term reference would not move the DB but could change how a reader
  interprets an FRR rule.
- The Rev5-grace and Class-A findings are JSON readings without a FedRAMP prose
  announcement; if FedRAMP later publishes a correction, the manifest note — not the pinned
  data — is what needs the edit.
- The classifier fix covers the 19 `github_release` feeds; the other 142 rows are now
  *labeled* `stored_status_only` instead of silently echoing, which is honesty, not
  detection. The labeled gap is the next tooling target, not a solved problem.
- The live `registry_stale` path has fired only in fixtures and in the read-only prototype;
  its first authenticated end-to-end firing will be the next monthly `standards-watch` run.
