# Phase-35 closing adversarial audit — 2026-08-16 (LATE: owed 2026-08-10, discovered by the phase-42 sweep)

**This audit is three phases late.** The regulatory-phase closing gate
(`protocol-layer/quality-gates.md`) required it when phase 35 shipped its registry and
regulatory-doc changes on 2026-08-10; it was not written, and the omission went unnoticed until
the phase-42 missed-items sweep. This is the **second occurrence** of the identical miss —
phase 34 shipped without its audit and was cited for it (finding 34-B, written by phase 35,
which then committed the same omission itself). The corrective is `docs/audits/INDEX.md`,
shipped alongside this document.

**Scope:** the phase-35 diff `f099359..b2d3796` (17 files, +997/−127) — its regulatory
surface — **plus phase 42's own registry writes** (the WS-2 elapsed-window outcome checks in
`anticipated_updates.json`), audited jointly so the gate is satisfied once for both without a
self-trigger loop. All checks below were re-executed 2026-08-16; commands and results are
stated with each claim.

## Pass 1 — source integrity

| Target | Check | Result |
|---|---|---|
| `fedramp-consolidated-rules.json` (pin `135707003f0aaa5c`, 2026.07.14.01) | sha256 of the on-disk file, then a fresh `fetchkit` fetch of the raw-GitHub source URL, hashed | on-disk **MATCH**; live fetch HTTP 200, 567,435 bytes, **BYTE-IDENTICAL** to the pin (no upstream revision since 2026-08-10) |
| `FR-2025-01-06-2024-30983.pdf` (pin `d5e1ec4107308e5e`, 1,067,294 bytes) | same two checks against the govinfo URL | on-disk **MATCH** incl. size; live fetch HTTP 200, 1,067,294 bytes, **BYTE-IDENTICAL** |
| ITSG-33 Annex-3A page (cyber.gc.ca) | fresh fetch; recorded verbatim re-matched | HTTP 200. Verbatim matches **after HTML-entity normalization only** — the page renders `(PDF,&nbsp;2.24&nbsp;MB)` where the record stores plain spaces; content is identical. "December 2014" still served: the Rev-4 annex is still current, so the phase-35 window withdrawal **stands** |
| CMS ARS policy page (security.cms.gov) | fresh fetch; recorded verbatim re-matched | HTTP 200, verbatim present exactly; "ARS 5.2" and "Last Reviewed: 7/16/2026" markers present. The THIN downgrade (detection URL tracks ARS, not ARC-AMPE) **stands** |
| All 76 horizon records | conformance walk: 5 provenance keys present, support/terminal enums vocab-valid, URL http(s) and non-empty, verbatim non-empty | **0 violations** |

Recorded obstacles (hhs.gov fact-sheet 403; Common Criteria portal 403) were not re-attempted:
they are recorded environment limits, not claims under audit.

## Pass 2 — claim support

- **The 18 HIPAA FR verbatims** (`docs/hipaa-security-rule-transition.md`): the pinned PDF was
  re-extracted with pdfminer.six 20260107 and every one of the 18 quoted strings re-asserted
  present in the extraction (whitespace/quote-glyph normalized, truncation ellipses stripped).
  **18/18 present.**
- **The "guidance-only revision" claim on the FedRAMP re-pin** (2026.07.06.01 →
  2026.07.14.01): re-counted from the pinned JSON — KSI **10 families / 46 indicators / 373
  control refs**, FRR **17 families**, CTL **14 groups** — exactly the counts the manifest
  version string records and the phase-35 diff claimed unchanged. No pinned count moved.

## Pass 3 — chain / mutation integrity

- Domain-trap sweep over all added lines of the 17-file diff (`[FROM RECALL`, "CMMC 3.0",
  rescind/cancel language): **2 grep hits, both false positives** — they are the phase-34
  audit document *describing its own trap sweep*. Zero real traps.
- **Zero `au-cmmc-*` record lines changed** in the phase-35 diff (the frozen CMMC suspension
  set was untouched, as required).
- Commit hygiene over the 6 phase-35 commits (`ae99dd7`, `c84f509`, `7737b26`, `55ffa93`,
  `3399a48`, `1b7b8f3`): **0 trailers, 0 leak patterns** (no session ids, model ids, links,
  personal emails) on all six.

## Pass 4 — adversary output (mandatory)

**The claim most likely to be wrong,** identified before this audit ran: *"the ITSG-33
window-withdrawal and ARC-AMPE THIN downgrade were evidence-correct but chose review cadences
that may bury both records again."* The phase-42 elapsed-window sweep was the live test, and
the monitor was probed directly:

- At 2026-08-16 and at +4 months, neither record surfaces (`no_fixed_date`, recently checked
  — correct).
- At 2027-02-15 (2× the quarterly poll cadence past `last_checked`), **both records return as
  `DUE_REVIEW`** on `horizon_monitor --overdue`.

Verdict: **refuted with a nuance.** The records are not buried — the monitor's
null-window/stale-check rule resurfaces them mechanically. But the effective resurfacing
horizon for a "quarterly" record is **~180 days** (the monitor uses 2× the poll cadence), not
a quarter. That gap is a design fact of the monitor, recorded here rather than silently
absorbed; it is acceptable for `no_fixed_date` watches and needs no change now.

## Residual risk (never an all-clear)

1. **This audit is three phases late and written by the author of the work it audits** — the
   same author-as-auditor limit as the 32/34/36 documents, mitigated the same way (every
   mechanical claim re-executed with its command; the adversary claim pre-named and tested),
   not eliminated.
2. **ARC-AMPE's detection URL still points at the CMS ARS page**, so the record can detect ARS
   changes but not the artifact it actually watches. Until an ARC-AMPE publication page is
   found, the THIN label is the honest state and detection remains structurally misdirected.
3. **The ITSG-33 verbatim is entity-sensitive**: a byte-level matcher fails on `&nbsp;` where
   an entity-normalizing matcher passes. Future audit harnesses must normalize entities before
   declaring verbatim drift.
4. **Quarterly-labelled `no_fixed_date` records resurface at ~180 days, not ~90** (the
   monitor's 2× rule). Anyone reading `poll_frequency: quarterly` as a resurfacing guarantee
   overestimates the clock by 2×.
