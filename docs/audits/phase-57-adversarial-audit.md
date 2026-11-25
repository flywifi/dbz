# Phase-57 closing adversarial audit — 2026-11-25

**Scope.**
- **Canonical data:** the eCFR text of 45 CFR 164 Subpart E as of 2026-11-18, and the amendatory text of
  91 FR 74848.
- **`source_manifest.json`:** two entries.
- **`feed_registry.json`:** `hipaa-privacy`.
- **`anticipated_updates.json`:** `au-hipaa-privacy-2026`.
- **`framework_changelog.json`:** two confirmed entries.
- **`framework_vocab.json`:** one label.

Written to satisfy the regulatory-phase closing gate (`protocol-layer/quality-gates.md`).

**Origin.**
- **The request:** the user asked for "the new HIPAA security" rule to be integrated as a version.
- **What the research found:** the final rule HHS published is a Privacy Rule final rule (RIN 0945-AA00). The
  Security Rule (RIN 0945-AA22) is still only the 2025 proposal.
- **What the user chose:**
  - the Privacy final rule as its own label beside the in-force one;
  - carry existing mappings only where the text is unchanged;
  - record the business-associate change against HIPAA Security.
- **How it was tested:** the plan followed `protocol-layer/planning-standard.md`. It ran four times in a throwaway
  clone, each with a real commit per stage, a rebuild, the gate battery and the CI rehearsal.

## Pass 1 — source integrity
- **The in-force text** is the eCFR point-in-time XML for 2026-11-18, fetched once through fetchkit and pinned by
  sha256.
- **The amended text is computed**, from that XML and the rule's 12 amendatory instructions.
  - **Instruction text:** extracted from the govinfo page of FR doc 2026-23429, whose own sha256 is recorded.
  - **Where the extract is cut:** from "For the reasons stated in the preamble" to the last "* * * * *", so it holds
    no preamble, contact block or signature.
- **The Federal Register was rechecked** on 2026-11-24 at 19:20 UTC:
  - 0945-AA22 has only the proposed rule;
  - 0945-AA00 has the final rule;
  - HHS published no other HIPAA rule in November 2026.
- **The eCFR has not codified the rule.** Its Subpart E for 2026-11-19 adds only links and a 164.525 placeholder.
  The computed text is checked against the eCFR on 2027-01-19 (`cfr_versions.py --verify-ecfr`).

## Pass 2 — claim support
- **Every restated number comes from a build:**
  - README and the architecture document are restated from the databases before and after;
  - the page `docs/hipaa-privacy-rule-2026-final-rule.md` is rendered from `grc.db`;
  - the changelog entry's counts are read from the build.
- **The implementation reproduced the fourth dry run:**
  - status counts 913 / 5 / 15 / 1 / 98 / 2 / 6 / 62;
  - carried 5,869 (5,791 + 78);
  - master rows 97,704 → 103,573;
  - frameworks 36 → 37 and stored pairs 68 → 73;
  - Monday census 309 → 311 requests.
- **Every quotation of rule text comes from the pinned texts.** The comparison covers only what the amendatory
  instructions change: the preamble's minimum-necessary and SUD/emergency topics change no regulatory text
  (164.502(b), 164.510 and 164.512(j) are not amended).

## Pass 3 — chain / mutation integrity
- **Commits**, each rehearsed when made (22 steps, then 23 once the self-test step joined):

  | Commit | What |
  |---|---|
  | `103015c` | anchor |
  | `b35c6fa` | both texts |
  | `1e16995` | label and carry |
  | `b78ed9b` | registries and page |
  | (this one) | close-out |
- **Table digests that changed:**

  | Commit | Tables |
  |---|---|
  | Both texts | 2 new tables, plus `controls`, whose only differing column is the generator's `generated_at` after the catalog was regenerated |
  | Label and carry | `master_mappings`, `framework_labels` |
  | Registries and page | `anticipated_updates`, `changelog`, `framework_registry` |

  In the dry run, the 97,704 existing master rows were compared column by column: none changed.
- **Registries were written only through `tools/registry_io.py`.**

## Pass 4 — adversary, run
1. **"The new HIPAA rule is the Security Rule."** The Federal Register API by RIN: no. **Overturned.**
2. **"Carry by citation number."** It carries 6,277 rows, 432 of them onto a changed, removed or re-led provision.
   The rule deletes 164.520(c)(2)(ii), the acknowledgment requirement, and gives that number to the paragraph after
   it. **Overturned.**
3. **"Identical text is enough."** 72 rows sit under changed lead-ins, and 12 on 164.520(c)(2)(iv), whose
   Federal Register reprint disagrees with its instruction. **Overturned;** both conditions are part of the carry
   rule.
4. **"The comparison sees wording, not rendering."** Not at first. The first classifier compared heading and text
   separately, and the eCFR italicises headings while the Federal Register runs them into the text. Line-break
   hyphens had the same effect. Found while planning and fixed; a self-test case holds it, and a broken copy that
   restores the old comparison fails it (11/13).
5. **"The preamble's topics are the rule's changes."** No instruction amends 164.502(b), 164.510 or 164.512(j).
   **Overturned;** the page says so.
6. **"Punctuation-only changes are editorial."** In the health-care-operations definition, the commas becoming
   semicolons are the change. **Overturned;** any change in wording blocks the carry.
7. **"The gates only repeat what the build says."** Check 22 re-derives each carry from the stored text. Red on
   three corrupted copies (below). **Holds.**
8. **"Adding the label disturbs other data."** No existing master row changed; the overlap matrix, the CCI verdicts
   and the benchmarks are unchanged. **Holds.**

## Red then green
| Gate | Broken input | Red |
|---|---|---|
| `cfr_versions.py --selftest` (13 cases) | lead-in check removed / reprint check removed / carry by citation number / removal check removed / heading-versus-text comparison restored | 11/13, 10/13, 7/13, 11/13, 11/13; each fails its own case. The unbroken control passes 13/13. |
| check 22 | one stored amended paragraph altered (164.530(c)) | `carried 164.530(c) -> 164.530(c): provision text differs; … lead-in 164.530(c) differs` |
| check 22 | an invented 2026 row, plus a row pairing the versions | `… is not a carry of an in-force row; … 1 master rows pair the two versions of the Privacy Rule` |
| `test_spine` (5 new checks) | a row at the reused number; renumbered rows deleted; votes copied; 1,500 carried rows deleted; the query's dispatch entry removed | all five fail, each with its own message |
| `run_scenarios` scenario 8 | 78 horizon records under the old pin | `scenario 8: horizon registry (want 77; got 78)` |

## Residual risk
- **The amended text is computed until 2027-01-19.** One paragraph is held back (164.520(c)(2)(iii), where the
  reprint disagrees). The eCFR's codified text settles it, and if the two texts differ the eCFR wins.
- **Carried rows rest on text identity, not on an issuer's mapping of the 2026 text.** They are marked as carried,
  and carried consensus rows rank `asserted_by_source`.
- **18 carried provisions (231 rows) use "health care operations",** whose definition the rule re-punctuates.
- **8 HITRUST v11.4 citations (82 rows) are absent from the in-force text.** Their cause is not established; check 22
  pins them.
- **591 in-force rows have no counterpart in the 2026 label** until a source maps the amended text.
