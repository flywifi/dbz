# Phase-44 audit — 2026-08-16

**Scope.** This phase's own regulatory-registry writes (none beyond the vocabulary — see the
note below), the adversary re-draw the phase-43 audit called for, and the retraction of
phase-43 finding B-2. Written to satisfy the regulatory-phase closing gate jointly for the
phase-44 changes.

*Registry note:* phase 44 did not touch `anticipated_updates.json`, `feed_registry.json` or
`framework_changelog.json`. It changed `framework_vocab.json` (framework labels and the anchor
verdict vocabulary), which is a controlled vocabulary rather than a regulatory-currency
registry. The gate is satisfied here regardless, because the phase makes claims about a
regulation's structure (45 CFR Part 164's three subparts) that a reader is entitled to check.

---

## Part 1 — The retraction of phase-43 finding B-2

Fully documented in `phase-43-adjudication.md`, whose Part 2 now opens with the retraction.
Summarised here because a reader of this document should not have to find it elsewhere:

- **Claimed:** 18 genuine CCI bridge gaps, two of them STIG-exercised and "the highest-value
  items in the whole candidate set".
- **True:** zero gaps. **214** of the 231 candidates are pre-Rev-5 identifiers where DISA's own
  Rev-5 reference points elsewhere and our bridge already follows it; **17** are Appendix-J
  privacy enhancement CCIs with no Rev-5 reference at all.
- **Probe:** each candidate's claimed control compared against `disa_ccis.nist_rev5_refs` (the
  pinned DISA XML) and against our `cci_bridge` row. Examples: CCI-000297 claims `CM-2(1)`,
  DISA says `CM-2`, ours anchors `CM-2 b.2`; CCI-002364 claims `AC-12(1)`, DISA says
  `AC-12(2)`; CCI-002508–2512 claim `SC-34(3)`, DISA says `SC-51`.
- **Mechanism of the error:** each pair was judged on whether the CCI's text matched the claimed
  control's *title*, which it did in every case. The authority was never consulted. This is now
  §5 of `protocol-layer/planning-standard.md`: *text plausibility is not authority*.
- **Finding B-3 survives and is strengthened:** DISA's own references confirm CCI-002231 →
  `AC-6(7)` and CCI-002331 → `AC-19(5)`, so the republications' swap is a data error in those
  sources, not a reading of titles.

No data was ever changed on the strength of B-2, and no headline number moves with its
retraction — `candidate` anchors already produce `weak` framework rows.

---

## Part 2 — The adversary re-draw (the phase-43 audit's own named test)

The phase-43 audit named its most-likely-wrong claim: that the 20.2% unsupported rate is a
property of the consensus tier rather than of **proportional allocation**, which put 27 of 120
sampled edges on PCI × SOC 2 — the pair whose control texts are easiest to judge. It named the
overturning evidence (an equal-allocation re-draw) and committed the seed and stratum SQL so the
re-draw would be one command. **Phase 44 ran it.**

**Method.** Same seed (20430816), same `md5(seed|fw_a|native_a|fw_b|native_b)` ranking, equal
allocation of up to 6 edges per framework pair: **146 edges across 26 pairs** (the proportional
draw covered 19 pairs; the phase-44 HIPAA subpart split created the rest). **79 edges overlap
the phase-43 draw and reuse their recorded verdicts unchanged**; **67 were newly adjudicated.**

### Result — the unsupported rate holds; the supported rate does not

| Allocation | n | SUPPORTED | SCOPE_MISMATCH | UNSUPPORTED | 95% CI (unsupported) |
|---|---|---|---|---|---|
| proportional (phase 43) | 119 | 49.6% | 30.3% | **20.2%** | [13.9, 28.3] |
| **equal (phase 44)** | 146 | **39.0%** | **40.4%** | **20.5%** | [14.8, 27.8] |

- **Unsupported: z = 0.08.** Statistically identical. **The phase-43 headline survives its own
  adversary test** — the tier really is ~20% unsupported, not an artifact of which pairs were
  oversampled.
- Against the phase-36 reference points the conclusion is unchanged and slightly stronger: hub
  tier 63.2% (**z = −5.14**), authoritative stratum 25.0% (**z = −0.36**). The consensus tier
  continues to behave like the authoritative stratum, not like the hub.
- **But the supported rate is allocation-dependent**: 49.6% → 39.0%, with the difference moving
  into `SCOPE_MISMATCH` (30.3% → 40.4%). Thin pairs — many of them section-level HIPAA pairs and
  the newly separated Privacy/Breach pairs — produce proportionally more granularity mismatches
  than the dense PCI × SOC 2 pair does. **Quote the unsupported rate as robust; quote the
  supported rate with its allocation named.**

### What the equal draw surfaced that proportional allocation had not

- **HIPAA Breach Notification pairs (13 edges), newly visible** because phase 44 separated the
  label. They adjudicate well where the counterpart is a notification criterion — 164.406 ×
  SOC 2 P6.7, 164.410 × P6.3, 164.404 × P6.7 all `SUPPORTED` — and badly where the counterpart
  is generic incident-response or role assignment (164.404 × PCI 12.1.4 `UNSUPPORTED`).
- **HIPAA Privacy Rule pairs (19 edges)** show the section-level problem at its worst: 164.530
  is paired with five different PCI "Requirement N policies are documented" criteria, all
  `SCOPE_MISMATCH` for the same reason. Two are genuinely good — 164.528 accounting of
  disclosures × SOC 2 P6.2 record of authorized disclosures, and 164.530(e) sanctions × CC1.5
  accountability.
- **Verdict consistency across draws:** every one of the 79 overlapping edges reuses its
  phase-43 verdict; no edge received two different verdicts. Two independently-drawn pairs on
  the same underlying defect (164.530 × ISO 10.1; documentation-retention × personal-information
  retention) received the same verdict in both draws, which is weak but real evidence the
  labelling standard is stable.

---

## Adversary output (mandatory)

**The claim most likely to be wrong in *this* document: that the two draws are independent
enough for the agreement between them to mean much.** They share a seed, a ranking rule, a
labeller, and 79 of 146 edges. What the re-draw genuinely tests is *allocation* sensitivity —
and it answers that cleanly. What it cannot test is **labeller** bias, which is common to both
and is the larger threat: if my standard for `SUPPORTED` is systematically wrong, both draws are
wrong together and agree beautifully. The overturning evidence is an independent re-label of the
committed keys by someone who did not build this pipeline; the keys, seeds and worksheets for
both draws are in `docs/audits/data/` precisely so that is possible.

**Runner-up:** that the HIPAA subpart split is correct because the CFR subpart boundaries say
so. The boundaries are not in dispute, but *which rule a source intended* can be. When SCF's
"US HIPAA" column cites 164.530, it may mean "HIPAA generally" rather than "the Privacy Rule
specifically"; phase 44 routes on the citation, which is the best available evidence but is an
inference about intent. A source that publishes an explicit rule name would settle it.

## Residual risk (never an all-clear)

1. **Author-as-labeller across both draws** — the dominant unmitigated risk, stated above.
2. **The granularity defect is disclosed, not fixed.** The consensus surface still stores
   `164.308` where the projection carries `164.308(a)(1)(ii)(A)`, and 40.4% of the equal draw
   is `SCOPE_MISMATCH` largely because of it. Fixing it moves `consensus_key`, `master_mappings`,
   the overlap metrics and the scenario pins together and needs its own phase.
3. **The 38 suppressed intra-regulation pairs were never in any published number** — they would
   have been created by phase 44's own label split had the guard not been written first. The
   count is printed at build time, but no gate asserts it stays at a sane level.
4. **Equal allocation over-weights thin pairs by construction.** Neither draw is "the" estimate;
   both are published, and the unsupported rate is the figure robust to the choice.
5. **Four of the 120 phase-43 sample keys no longer resolve** after this phase's relabelling and
   category-heading removal. Their verdicts stand as a record of what was true at `b0e69a1`;
   they are not re-derivable against the current build.
