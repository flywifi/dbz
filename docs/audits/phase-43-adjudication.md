# Phase-43 adjudication audit — 2026-08-16

**Scope.** Two adjudications the repository had deferred, plus this phase's own regulatory
registry writes (the WS-5 trigger and detection corrections in `anticipated_updates.json`),
audited jointly so the regulatory-phase closing gate is satisfied once for phase 43.

1. **The consensus cross stratum** — 3,422 edges, unadjudicated since phase 36 recorded it as
   residual risk #2, and the tier the customer-facing overlap numbers rest on.
2. **The 231 `candidate` CCI anchors** — edges the republications assert and our DISA bridge
   lacks, which `spine_loader.build_cci_corroboration` calls "a gain to review, never
   auto-promoted" and which nobody had reviewed in 21 phases.

**Nothing was promoted, re-tiered or deleted.** Both adjudications record verdicts beside the
data; every recommendation is for a later, separately approved change.

---

## Part 1 — The consensus cross stratum (n=120, seeded)

**Frame.** `docs/audits/data/phase-43-consensus-frame.json`; seed **20430816**; edges ranked by
`md5(seed|fw_a|native_a|fw_b|native_b)` — the phase-36 rule, so the two audits are comparable.
Allocation is proportional across the 19 framework pairs present (largest remainder, minimum 1),
120 of 3,422. Worksheet with per-edge verdicts and reasoning:
`docs/audits/data/phase-43-consensus-worksheet.json`.

**Evidence available per edge.** Voter recovery succeeded on **120/120** (reversing
`_CONSENSUS_TO_CANON` and joining `consensus_edges` exactly). Shared 800-53 anchors had to be
reconstructed — `shared_anchors` is NULL on consensus master rows and `consensus_edges.shared_atoms`
is populated only for `strong` — and reconstruction reaches only part of the stratum:
exact `native_id` 22.2%, `consensus_key` 52.9%, `corroboration_key` **64.4%** (the key used).
**64 of the 120 sampled edges carry reconstructable anchor evidence and 56 do not**, so every
rate below is also reported split by that.

### Results

| Verdict | n | Rate (of 119 decidable) | 95% CI |
|---|---|---|---|
| `SUPPORTED` | 59 | **49.6%** | [40.8, 58.4] |
| `SCOPE_MISMATCH` | 36 | 30.3% | [22.7, 39.0] |
| `UNSUPPORTED` | 24 | **20.2%** | [13.9, 28.3] |
| `UNDECIDABLE` | 1 | — | — |

**The comparison is the deliverable.** Phase 36 found the hub tier **63.2% unsupported**
(n=38) and its authoritative control stratum **25.0%** (n=12). Against those:

- consensus vs hub: **z = −5.01** — the consensus tier is significantly better founded.
- consensus vs authoritative: **z = −0.39** — statistically indistinguishable.

So the tier the flagship pairs sit on behaves like the authoritative stratum, not like the hub.
That is the opposite of what a reader might have extrapolated from phase 36's headline, and it
is the single most useful thing this audit establishes.

### Where the failures concentrate

| Cut | n | SUPPORTED | SCOPE_MISMATCH | UNSUPPORTED |
|---|---|---|---|---|
| with reconstructable anchors | 63 | 58.7% | 23.8% | 17.5% |
| without | 56 | 39.3% | 37.5% | 23.2% |
| consensus tier `strong` | 14 | 64.3% | — | 7.1% |
| consensus tier `moderate` | 105 | 47.6% | — | 21.9% |
| **HIPAA-side edges** | **21** | **4.8% (1)** | **61.9% (13)** | **33.3% (7)** |
| all non-HIPAA edges | 98 | 59.2% | 23.5% | 17.3% |

**Finding A-1 (HIGH) — every HIPAA native in this stratum is a whole CFR section.** The
distinct HIPAA ids sampled are `164.306`, `164.308`, `164.310`, `164.312`, `164.314`,
`164.316`, `164.530` — sections, never standards or implementation specifications. 164.308
alone contains roughly twenty implementation specifications. An edge to "HIPAA Security
164.308" therefore asserts a section-level association by construction, which is why 20 of 21
HIPAA edges failed: 13 `SCOPE_MISMATCH` and 7 `UNSUPPORTED`. Excluding them lifts the stratum
to 59.2% supported and 17.3% unsupported. This is a granularity defect in the consensus inputs,
not a judgment call about the individual pairs.

**Finding A-2 (MED) — three edges carry a Privacy Rule section under the label "HIPAA
Security".** `164.530` is 45 CFR Subpart E (Privacy Rule administrative requirements —
sanctions, complaints, mitigation), not Subpart C. Sampled edges 23, 30 and 36 pair it with
ISO 10.1, PCI 12.1.3 and SOC 2 P5.2 respectively. Two of the three are unsupported on their
merits regardless; the label error is the durable defect.

**Finding A-3 (LOW) — one SOC 2 native is a category heading, not a criterion.** Edge 99 pairs
PCI 9.4.7 with "SOC 2 P4.0". P4.0 is the privacy category label; the criteria are P4.1–P4.3,
and the real counterpart here is P4.3.

**Finding A-4 (MED) — reconstructed anchors are noisy for ISO clause ids.** Edge 47 (ISO 10.1
× 800-171 3.12.1) reconstructs to `AC-17`, `AC-24`, `AC-3(3)` — remote-access controls that
have nothing to do with either side. Anchor evidence should be read as corroboration when it
agrees, never as proof, and several ISO management-clause reconstructions resolve to generic
policy controls (`AC-1`, `AT-1`, `PM-1`) that would "support" almost any pair.

### Representative verdicts
- **Supported and unambiguous:** ISO A.8.24 × PCI 3.7.1 (cryptography ↔ key generation);
  800-171 3.4.6 × PCI 2.2.4 (least functionality ↔ disable unnecessary services); CIS 18.2 ×
  PCI 11.4.3 (external penetration testing); CSF ID.RA-07 × SOC 2 CC8.1 (change risk ↔ change
  management).
- **Scope mismatch:** CIS 6.2 (revoke access) × HIPAA 164.308 — the counterpart is one
  implementation specification, 164.308(a)(3)(ii)(C), inside a section of about twenty.
- **Unsupported:** ISO 7.2 *competence* × SOC 2 CC1.3 *structures and reporting lines* (the
  competence criterion is CC1.4); 164.316(b)(2)(i) *retain documentation six years* × SOC 2
  P4.2 *retain personal information* — a keyword collision on "retention" with different
  objects; PCI 6.1.2 *roles for Requirement 6* × SOC 2 CC1.1 *integrity and ethical values*.

---

## Part 2 — The 231 `candidate` CCI anchors (complete, not sampled)

> ### RETRACTION (phase 44, 2026-08-16) — finding B-2 below is WRONG
>
> **What this section claimed:** 18 genuine bridge gaps, two of them STIG-exercised and
> "the highest-value items in the whole candidate set".
>
> **What is true:** there are **zero** bridge gaps. All 231 candidates are stale-identifier
> artifacts — **214** where DISA's own Rev-5 reference points somewhere other than the
> republication's claim *and our bridge already follows DISA*, and **17** Appendix-J privacy
> enhancement CCIs with no Rev-5 reference at all.
>
> **The probe that overturned it:** comparing each candidate's claimed control against
> `disa_ccis.nist_rev5_refs` (the pinned DISA XML) and against our `cci_bridge` row. Worked
> examples: CCI-000297 — republication claims `CM-2(1)`, DISA's Rev-5 reference is **`CM-2`**,
> our bridge anchors `CM-2` sub-part `CM-2 b.2`. CCI-002364 — claims `AC-12(1)`, DISA says
> **`AC-12(2)`**, ours anchors `AC-12(2)`. CCI-002508–2512 — claim `SC-34(3)`, DISA says
> **`SC-51`**, ours anchors `SC-51`. The two "STIG-exercised gaps" are therefore not gaps:
> both CCIs are anchored, just not where the republication says.
>
> **Why the error happened:** each pair was judged by whether the CCI's text matched the claimed
> control's *title*. It did — `CM-2(1)` is "Baseline Configuration | Reviews and Updates" and
> the CCI text is about reviewing and updating baselines. What was never checked is whether the
> **authority** placed it there. Text plausibility is not authority; that rule is now
> `protocol-layer/planning-standard.md` §5.
>
> **Also of note:** this document's own residual risk #4 named the disconfirming probe and did
> not run it. Running it is now §4 of the planning standard.
>
> Findings B-1 and B-3 are restated below with corrected numbers. The worksheet
> (`docs/audits/data/phase-43-candidate-anchors.json`) has been re-dispositioned in place, with
> `authority_checked: true` on every row. No data was ever changed on the strength of B-2.

All 231 were adjudicated; worksheet at `docs/audits/data/phase-43-candidate-anchors.json`.

**Corrected dispositions (phase 44):**

| Disposition | n | Meaning |
|---|---|---|
| `STALE_R4_REFERENCE` | **214 (92.6%)** | DISA's own Rev-5 reference points elsewhere and our bridge follows it; the republication cites a pre-Rev-5 id |
| `UNBRIDGED_APPENDIX_J` | **17 (7.4%)** | Appendix-J privacy *enhancement* id with no Rev-5 reference at all — definition-only by design |
| genuine bridge gaps | **0** | — |

*Superseded phase-43 dispositions, kept for the record: `STALE_R4_APPENDIX_J` 209 ·
`BRIDGE_GAP` 18 · `TRANSPOSED` 2 · `MISMATCH` 1 · `GRANULARITY` 1.*

**Finding B-1 (HIGH, corrected in phase 44) — the `candidate` class is *entirely* stale
identifiers, not gains — 231 of 231, not 209.** Of those, 209 target ids in the Appendix-J
privacy families: `AR` 68, `TR` 32, `DM` 31,
`IP` 25, `DI` 23, `SE` 12, `UL` 10, `AP` 8. Appendix J was withdrawn in Rev 5 and absorbed into
the PT/PM families, which our DISA bridge already handles through its `appj_absorption` basis
(441 anchors). The republications simply retain the pre-Rev-5 ids. The code's comment — "a gain
to review, never auto-promoted" — is right to refuse promotion but describes the class
optimistically: nine in ten candidates are not gains at all. **Recommended (not applied):
classify these separately from genuine candidates so the count stops implying 231 reviewable
gains.**

**Finding B-2 — RETRACTED IN FULL (see the retraction block at the head of this Part). The
text below is preserved verbatim as the record of the error, and must not be acted on.**

~~**Finding B-2 (MED) — 18 genuine bridge gaps, two of them STIG-exercised.**~~ Where the target
does exist in Rev 5, the CCI text matches it verbatim in 18 cases: `CM-2(1)` ×4 (baseline
review/update and its two ODP halves), `SC-34(3)` ×5 (hardware write-protect), `SC-42(3)` ×2,
`SA-22(1)` ×2, and one each of `PE-13(3)`, `AU-5(3)`, `AC-12(1)`, `MP-7(1)`, `SC-37(1)`. Two
are STIG-exercised — **CCI-000297 → CM-2(1)** and **CCI-002364 → AC-12(1)** — meaning a real
STIG rule tests a CCI our bridge does not anchor. Those two are the highest-value items in the
whole candidate set and the natural first change of a future phase.

**Finding B-3 (MED) — two CCIs are transposed in the republications. STRENGTHENED in phase 44:
the transposition is now corroborated against the primary source — DISA's Rev-5 references say
`CCI-002231 → AC-6(7)` and `CCI-002331 → AC-19(5)`, and our bridge follows exactly that, so the
swap is unambiguously an error in the republished data rather than a reading of the titles.**
- `CCI-002231` reads *"reassign or remove privileges … to reflect organizational mission and
  business needs"* — that is **AC-6(7) Review of User Privileges** — but is claimed against
  **AC-19(5) Full Device or Container-based Encryption**.
- `CCI-002331` reads *"employ full-device encryption or container encryption … on mobile
  devices"* — that is **AC-19(5)** — but is claimed against **AC-6(7)**.

Each CCI's text is an exact match for the *other's* claimed control. Our bridge is right to
carry neither. This is a defect in the republished data, worth reporting upstream and worth
remembering the next time a republication is treated as a witness.

---

## Adversary output (mandatory)

**The claim most likely to be wrong: that the consensus tier's 20.2% unsupported rate is a
property of the tier rather than of my sampling frame.** The stratum is dominated by a few
framework pairs — PCI×SOC 2 alone is 762 of 3,422 rows — and proportional allocation therefore
put 27 of 120 sampled edges on that single pair. PCI and SOC 2 are also the two frameworks
whose control texts I can judge most confidently, so the sample may be easiest precisely where
it is densest. The overturning evidence would be an equal-allocation re-draw (n per pair rather
than proportional) scoring materially worse on the thin pairs; the seed and stratum SQL are
committed so that re-draw is a single command. A second, cheaper check: the HIPAA cut already
shows what a hard pair does to the rate — 20 of 21 failing — and HIPAA is only 17.5% of this
sample while it is a much larger share of the customer-facing pairs.

**Runner-up:** that `SCOPE_MISMATCH` at 30.3% is a mapping defect at all. Every mapping author
publishes at some granularity, and a section-level HIPAA id may be exactly what the source
intended to assert. The verdict says the pair does not support *shared audit work* at the
granularity the identifiers claim — it does not say the source was wrong.

## Residual risk (never an all-clear)

1. **Author-as-labeler.** I built this pipeline and I labelled both sets. Mitigations applied:
   the seed and all keys are committed so an independent re-label is possible; tier and
   confidence were not shown while judging; the phase-36 strata provide external comparison
   points that behaved as predicted. Not eliminated.
2. **Half the consensus sample had no reconstructable anchor evidence** (56 of 120) and scores
   materially worse (39.3% supported vs 58.7%). Some of that gap is genuine and some is my
   reduced ability to judge without anchors; the split is published rather than blended, but it
   is not resolved.
3. **One edge is `UNDECIDABLE`** (PCI A3.1.4, a designated-entities appendix requirement whose
   text I could not state reliably). It is excluded from the rates, not pushed into a verdict.
4. **The candidate adjudication rests on identifier semantics**, not on re-reading DISA's own
   list: I verified that 209 targets are absent from the Rev-5 catalogue and that their families
   are Appendix-J, but I did not re-derive Appendix-J's absorption mapping from the pinned
   workbook. A future phase that acts on B-2 should re-verify the 18 gaps against the DISA
   source before adding any edge.
5. **`strong`-tier edges are only 14 of the sample**, so the strong/moderate difference (64.3%
   vs 47.6% supported) is suggestive and under-powered — do not quote it as established.
