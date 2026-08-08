# CMMC ODP baseline — stage marker for the r3 transition comparison

**Stage frozen: 2026-08-08.** This document records exactly where the CMMC → NIST SP 800-171
r3 transition stood when phase 32 closed its scoping, so that when the reform review
concludes and final values exist, the added/removed/changed analysis can be run offline
against pinned artifacts rather than reconstructed from memory. Rules of evidence:
`protocol-layer/regulatory-provenance.md`.

## Where things stand (all origin-verified 2026-08-08)

- **CMMC Phase 2 is suspended** (2026-07-13; OUSD(A&S) implementation memo, open-publication
  case 26-P-1023): only Level 1 (Self) / Level 2 (Self) designations; no waivers during the
  review; "CMMC Level 2 is aligned with NIST SP 800-171 Rev 2." A 60-day CMMC Reform Task
  Force review is running (report to the DoW CIO due ~2026-09-11, derived from the release's
  60-day statement); an RFI closed/closes 2026-08-14 (SAM.gov). Horizon records:
  `au-cmmc-phase2`, `au-cmmc-taskforce-report`, `au-cmmc-rfi`.
- **The 2025-04-10 ODP memo is the pre-review baseline** for DoD's intended r3 parameter
  values: "In preparation to implement reference (a) as the minimum requirement for
  contractors, the Department of Defense (DoD) has defined as policy the attached values for
  the ODPs identified in the reference (a) source document." Signed David W. McKeown
  (Performing the Duties of the Deputy DoD CIO for Cybersecurity and DoD CISO). Attachment A
  carries values embedded in per-requirement prose across **50 unique r3 requirement
  headings**; "In four (4) instances the ODP has been defined as guidance versus a specified
  value." All 50 requirements verify against the pinned CPRT 171r3 dataset
  (`cprt-sp800-171r3`), so a future load joins the spine completely.
- **Decision (user, 2026-08-08): wait for the task-force outcome before loading the values**
  into `odp_values`. The memo stays pinned; nothing is transcribed yet — prose transcription
  is the top fabrication surface and the review may change the numbers.

## Offline canonical baseline (everything needed for the future diff, committed + sha-pinned)

| Artifact | Path | Manifest id | Why it is in the baseline |
|---|---|---|---|
| ODP memo (authority) | `canonical-sources/source_data/dod/OrgDefinedParmsNISTSP800-171.pdf` | `dod-odp-values-memo` | The pre-review DoD r3 parameter values, as signed |
| ODP memo, extracted text | `canonical-sources/source_data/dod/OrgDefinedParmsNISTSP800-171.extracted.txt` | `dod-odp-values-memo-text` | Diff-ready form; PDF-to-PDF diffs are impractical. Header records extractor + source sha |
| Suspension implementation memo | `canonical-sources/source_data/dod/ImplementingSuspensionCMMC-PhaseII.pdf` | `dod-cmmc-suspension-memo` | Defines the suspension-era assessment posture the baseline sits inside |
| 32 CFR Part 170 full text (as of 2026-08-01) | `canonical-sources/source_data/dod/ecfr-32cfr170-2026-08-01.xml` | `ecfr-32cfr170-xml` | The program rule text at the stage freeze — the object any future amendment diffs against (the generated `cfr/32-cfr-170.json` truncates section text; this XML is complete) |
| 171r3 requirement catalog | `canonical-sources/source_data/cprt/cprt_SP_800_171_3_0_0_07-03-2026.json` | `cprt-sp800-171r3` | The requirement id space the ODP values attach to |

## The comparison procedure (run when final values exist)

1. **Trigger**: the task-force outcome, a superseding ODP memo, rescission of the May-2024
   class deviation, or a proposed/final rule amending 32 CFR 170 (horizon records
   `au-cmmc-taskforce-report` / `au-cmmc-171r3-transition` escalate on each).
2. **Pin the new document(s)** exactly as this baseline was pinned: PDF + sha256 + retrieval
   URL + date into `source_data/dod/`, manifest-registered, provenance block per
   `regulatory-provenance.md` (verbatim + support label + terminal state).
3. **Extract text with the same tool** (pdfminer.six) so the diff is tool-consistent; record
   the extractor + source sha in the header as done here.
4. **Diff against `OrgDefinedParmsNISTSP800-171.extracted.txt`** per requirement heading
   (`3.x.y` sections): classify each as UNCHANGED / VALUE_CHANGED (state both values,
   origin-form) / ADDED / REMOVED / GUIDANCE↔VALUE flipped. The mutation-check categories
   apply — values are quoted verbatim from each document, never paraphrased.
5. **If 32 CFR 170 was amended**, diff the new eCFR XML against
   `ecfr-32cfr170-2026-08-01.xml` the same way (the eCFR versioner serves any as-of date, so
   the amendment date bounds the comparison).
6. Only after the comparison is documented does the load decision reopen (transcribe final
   values into `odp_values` with the gates already designed in the phase-32 plan: count
   equality, id existence vs CPRT, no duplicates, ≥10-value spot check).

## What this stage marker is NOT

Not a prediction of the review's outcome; not a load of any value into the database; not a
claim that the 2025 memo will survive the review. It is the fixed point the future analysis
measures from.
