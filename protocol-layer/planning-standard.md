# Planning standard

The required shape of a plan before work starts. Precedence statement: **a plan is a claim about
what is true, and every claim in it is checkable** — a smaller plan whose numbers can all be
re-derived beats a fuller one whose numbers are recalled.

Every rule below exists because this repository made the mistake it prevents. The scar is named
with the rule; a rule that cannot cite a failure it would have caught does not belong here.

## 1. The seven questions, answered per workstream

Each workstream states, in this order:

| Field | Content |
|---|---|
| **WHY** | the defect, with the evidence that establishes it |
| **WHO/WHAT** | the surfaces, tables and code the change touches |
| **WHERE** | `file:line` for every insertion point |
| **WHEN** | position in the order, and what it blocks or is blocked by |
| **HOW** | the change itself, with code |
| **RIPPLE** | every downstream effect, each with a **measured magnitude** |
| **RISKS AND MITIGATIONS** | a table with likelihood stated per row |

*Scar:* phase-37's WS-1 changed 263 primary-key values. The ripple was enumerated in advance
(digests, scenario pins, re-pinning discipline), so nothing was discovered mid-flight. Where a
ripple was not enumerated — the phase-40 schema bump — CI went red.

## 2. DEEP RESEARCH RECORD

Every number carries the probe that produced it and the date it was measured. A number without a
probe is a memory, and memory is what this standard exists to distrust.

*Scar:* phase-36's own audit reader was wrong three times before it was right (wrong CCM file,
id-padding, wrong CSF artifact) and nearly shipped a false CRITICAL fabrication finding. The
rule that followed — derive the artifact from the loader's declared source — only works if the
probe is written down beside the number.

## 3. Vetted code

**No code enters a plan unless it has been executed read-only against the real data, with its
measured output printed beneath it.** Where a magnitude cannot be measured read-only, the plan
says so explicitly and requires the implementation to print it rather than leaving it assumed.

*Scar:* phase 44's HIPAA subpart router looked obviously correct. Running it revealed that
splitting one framework label into three would make `_row_pairs` emit
`HIPAA Security ↔ HIPAA Privacy Rule` edges — a manufactured agreement between two subparts of
one regulation, in a table that had zero such edges. Review would not have caught it; execution
did, before a line was committed.

## 4. The adversarial check runs before belief, not after writing

Name the finding most likely to be wrong, name the probe that would disconfirm it, **run that
probe**, and report which way it fell. An adversary section that only *describes* the
disconfirming evidence has not been run.

*Scar:* phase-43 finding B-2 claimed eighteen bridge gaps. Its own residual-risk section said
"re-verify against the DISA source before adding any edge" — and that probe, executed at the
start of the next planning pass, showed there were **zero** gaps. The check existed; nobody ran
it before publishing.

## 5. Text plausibility is not authority

When a claim can be checked against the issuing source, check it against the issuing source. A
matching title, a plausible subject, or a confident secondary is not verification.

*Scar:* the same B-2. Every one of the eighteen "gaps" had a CCI whose text matched the claimed
control's title exactly — `CM-2(1)` is "Baseline Configuration | Reviews and Updates" and the
CCI text is about reviewing and updating baselines. DISA's own Rev-5 reference said `CM-2`. The
titles agreed; the authority did not.

## 6. Disconfirmed hypotheses are recorded

When a plausible hypothesis is investigated and refuted, the refutation is written down so the
next session does not re-chase it.

*Scar:* the phase-43 SCF double-count hypothesis (that `w_consensus` and `w_scf_composed` could
both trace to SCF) was refuted by measurement — 0 of 6,842 strong/moderate edges are SCF-alone.
Recording it cost one sentence and saves a future phase the investigation.

## 7. Corrections of record are louder than the original claim

A correction goes in every place the claim was made, states the mechanism that produced the
error, and is never quietly edited away.

*Scar:* three of them. The phase-38 confirmed overcount (53,046 → 23,339) is restated in the
changelog, the benchmark and the vocabulary. The phase-42 audit says in its first line that it
is three phases late. The phase-44 retraction of B-2 opens the section it corrects.

## 8. Measure then pin; red then green

No threshold is set above a measured value. No gate is accepted until it has been proven to fail
on deliberately broken input, with the transcript recorded.

*Scar:* every gate from phase 37 onward was proven red first. The one check that was wired in
without a proof — the phase-41 health-workflow edit — landed as a no-op and had to be fixed in a
follow-up commit.

## 9. Completeness sweep

Parked items are listed with the event that unblocks them. "Out of scope" is written down so it
cannot later be mistaken for an oversight, and near-term dated items are handed to the next
session explicitly.

*Scar:* the twice-missed regulatory audit gate. Both misses were found by archaeology because no
list existed; `docs/audits/INDEX.md` is what a completeness sweep looks like when it is made
durable.

## Applying this outside dbz

The compact form of this standard lives in the user-level `CLAUDE.md` so it governs plans in
every repository. This document is the authority for the worked examples and the scars; the
user-level copy is deliberately short and points here.
