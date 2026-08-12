# Phase 36 — accuracy audit of the master cross-mapping table (READ-ONLY)

**Run 2026-08-10 against `b2d3796`.** Subject: `master_mappings`, 97,906 rows — the surface
`dbz_query master` answers from and the basis of the "shared audit work %" reported by
`dbz_query overlap`. **Nothing in the repository was modified**: tree clean, zero local commits,
nothing pushed. Findings carry a *proposed disposition*; none is applied.

**Why this audit existed.** The table's *structure* is well guarded — 14 checks in
`validate_spine.py` pass. Its *content* had never been measured beyond two framework pairs in
`docs/BENCHMARK.md` (~179 spine ids). This is the first measurement of whether the edges are
right.

---

## 1. What the table actually is

| Fact | Measured |
|---|---|
| Total rows | 97,906 |
| Rows touching `NIST 800-53` (spokes) | **90,497 (92.4%)** |
| True framework↔framework rows | 7,409 (7.6%) |
| Framework pairs with stored rows | **60 of 595 (10.1%)** |
| Rows depending on the HITRUST hub | **82,825 (84.6%)** |
| `unified_mappings` that is `transitive_via_hitrust` | 53,022 of 60,924 (87.0%) |
| Rows with no recorded anchor | 90,711 (92.7%) — incl. 55,214 of 55,214 `transitive_unified` |
| Rows carrying a minority report | 3,839 (3.9%) |
| `framework_projection.status` | `open` for all 135,513 rows (the confirm/refute ledger has never been used) |

The stratum partition was asserted **exhaustive and disjoint** before any sampling, and the
sample is seeded (`md5(20360810|key)`) so it is reproducible.

## 2. Findings

| id | Sev | Finding | Proposed disposition (NOT APPLIED) |
|---|---|---|---|
| F-1 | MED | `README.md` calls the master surface "any-to-any"; 60 of 595 pairs are stored. The architecture doc is accurate (it credits `master_mappings` **+** `overlap_matrix`). | Reword the README row to name both surfaces. |
| F-2 | MED | `master` returns a bare `0` for the 535 unstored pairs while `overlap` answers 6.8% for the same pair (GDPR × ISO). Same class as the `fedramp` silent-empty fixed in phase 35. | Return the structured data-gap response pointing at `overlap` (`_master_declared_gap` already exists). |
| F-3 | HIGH | Fan-out is predicted by provenance: hub 16.1–29.6 controls per native id vs 1.0–8.6 for every source that states its mappings. Per framework: NIST CSF 152.3, HIPAA 89.9, SOC 2 51.3. | — (mechanism, see F-9/F-10) |
| F-4 | HIGH | 84.6% of rows depend on one licensed artifact that cannot be independently re-derived here. No repo document states this concentration. | Disclose the concentration in README/architecture. |
| F-5 | LOW | `source_manifest.json` claims 1,684 CCM pairs; the artifact has 1,684 raw / **1,683 distinct** (duplicate `LOG-09 → AU-12(3)`). DB is correct. | Say "1,683 distinct (1,684 raw)". |
| F-6 | HIGH | **The hub block is structurally almost unauditable.** Of 8 candidate held-out comparisons only 1 clears the min-n gate — the whole 82,825-row block is checkable against an authority on **52 native ids**. Causes: label dialect (`NIST CSF` vs `NIST CSF 2.0`) and id dialect (ISO `10.1` vs `10.2 a.1`; 800-171 prose vs `3.1.10[a]`; CMMC `AC.L1-3.1.1(a.)` vs `AC.L1.3.1.1`). Also explains the 3.9% minority-report rate. | Per-framework id-form bridge using the existing `spine_normalize`. |
| F-7 | HIGH | **Prose sentences stored as control identifiers at the top tier.** `cmmc171` (`owner_direct`, conf **0.95**) stores 800-171 r2 `native_id` as assessment-objective sentences. 322 master rows have ids >60 chars; **81% of that framework's `owner_direct` rows**; **100% of page 1** of the obvious query. Same loader emits correct CMMC ids. | Put `3.1.10[a]` in `native_id`; move prose to a description column. |
| F-8 | MED | The composition's evidence is discarded: `anchor_count = 0` on 92.7% of rows including every transitive row. The data is recoverable (this audit rebuilt it in one query). | Persist the anchor set; the column exists. |
| F-9 | HIGH | **Adjudicated: 63.2% of hub edges are UNSUPPORTED** (n=38 decidable, 95% CI [47.9%, 78.5%]) vs 25.0% for authoritative controls; SUPPORTED 18.4% vs 66.7%. Two-proportion z = 2.32, p ≈ 0.02. | Re-tier or prune after F-10 is settled. |
| F-10 | **HIGH** | **The repo never defines what an edge claims.** Authors assert weak "relates to" links; the table stores them identically to strong "satisfies" links; `overlap` sells the result as *shared audit work*. Confidence encodes *how sure*, never *how strong*. Even NIST/CSA mappings contain edges unsupported under the strong reading (25%). | Define an edge semantic (`equivalent`/`supports`/`informs`), populate per source, count only strong classes toward shared-work %. |
| F-11 | HIGH | The customer-facing % rests on the hub tier even where stored rows do not: SOC 2's projection is **100%** hub-derived, HIPAA's 98%, ISO's 89% — and `overlap` computes from the projection, not from the consensus-tier stored rows. SOC 2 × ISO ships **54.2%**, never validated against that tier. | Validate/annotate the overlap basis; disclose single-source dependency inline. |

**No fabrication anywhere it could be checked.** Independent re-derivation from the pinned
artifacts (each with a tamper test that had to catch a planted edge, and did):

| Provenance | Source | DB | Agree | Fabrication | Loss |
|---|---|---|---|---|---|
| `ccm_oscal` | 1,683 | 1,683 | 1,683 | 0 | 0 |
| `direct_olir` | 562 | 562 | 562 | 0 | 0 |
| `direct_csf2` | 737 | 737 | 737 | 0 | 0 |

Transcription is clean, so the accuracy problems found are attributable to **method**, not to
the loaders.

**Disconfirmed hypothesis (recorded because it kills the cheapest fix).** The audit predicted
promiscuous policy anchors (`xx-1`, `PM-*`, `SR-*`) would drive the fan-out. Reconstructed over
all 53,022 transitive rows: top-10 anchors 7.4%, top-50 21.3%, generic anchors 13.9%, busiest
anchor 1.3%. The distribution is **flat** — pruning a promiscuity blacklist would remove almost
nothing. The real mechanism is broad sparse composition (bipartite density 0.026–0.151: each
NIST CSF subcategory relates to ~15% of the entire 800-53 catalog).

## 3. Adversary pass (mandatory)

**The conclusion most likely to be wrong is F-9's 63.2%**, and the strongest case against it is
not that the edges are fine — it is that **the question is malformed**, which is F-10. Every
"unsupported" verdict presumes an edge means *"doing X contributes to satisfying Y"*. If the
sources only ever meant *"X and Y concern related subject matter"*, then most of my 24
unsupported calls are category errors, and the defect is the repo's silent promotion of weak
links into a shared-work percentage rather than the links themselves. Evidence that would
overturn the number: a definition — from HITRUST's own cross-reference documentation — stating
the intended strength of its mappings. I did not obtain it (the artifact is licensed and its
methodology statement was not in scope), so **F-9 should be read as conditional on the strong
semantic, and F-10 as the finding that survives either way.**

What *cannot* be explained away by semantics: `Singapore PDPA §1(2)` — a commencement clause —
mapped to a sensor-capability control. No definition of "relates to" makes that edge meaningful.
Edges of that kind are a floor under F-9, not the whole of it.

**Second-order risk:** the audit's own reader was wrong three times before it was right (wrong
CCM file; id-padding mismatches; and diffing CSF against the concept-crosswalk xlsx when the
loader reads the CPRT OLIR graphs — which nearly shipped as a CRITICAL fabrication finding). The
rule adopted mid-audit — *derive the artifact from the loader's declared source, never from a
manifest id that looks related* — arrived after those errors, so earlier passes had less
protection than later ones.

## 4. Residual risk (not an all-clear)

1. **Author-as-labeler.** I built this pipeline and labeled its edges. The blind protocol was
   only partial — provenance was visible during labeling. The seeded sample keys are recorded;
   an independent re-label is the check that would settle F-9.
2. **65 of 220 sampled edges adjudicated.** `cross_consensus` (3,422 rows) and
   `cross_production` (1,340) are **unmeasured** — and since the flagship stored pairs are
   consensus-tier, that is the highest-value remaining work.
3. **One authority comparison in the entire hub block** (52 native ids). F-6 means the block
   cannot currently be validated at scale by any mechanical means.
4. **The licensed HITRUST artifact cannot be independently re-derived** in this environment, so
   its derivation was checked, never its content.
5. **No sensitivity model** converts edge-level support into a corrected overlap percentage;
   the band in F-11 is illustrative, not a correction.
