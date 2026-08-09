# Phase 32 closing adversarial audit — CMMC + HIPAA regulatory absorption

**Run 2026-08-09** against the phase's own diff (`f0febb0..HEAD`: commits `1cf7aa3`,
`c1f5f3b`, `4af0bf9`, `1a8ca33`, `075dc74`, `670d9a2`, `e9725fe`, plus the fixes in this
commit). Required by the regulatory-phase closing gate (`protocol-layer/quality-gates.md`);
pass structure and provenance rules per `protocol-layer/regulatory-provenance.md`. The audit
ran against the ledger — the 76 registry provenance blocks, the pinned artifacts, and the
doc source registers — not against prose impressions. Mechanical harness: every provenance
URL re-fetched and every verbatim re-matched by script; results below.

## Input ledger

- 76 `anticipated_updates` provenance blocks (68 backfilled `670d9a2`; 8 from
  `c1f5f3b`/`075dc74`), all enum-enforced by the schema-3.14 build.
- 4 sha-pinned artifacts under `canonical-sources/source_data/dod/` (2 memo PDFs, the
  32 CFR 170 XML, the memo text extraction) + regenerated `cfr/` JSONs.
- Doc claims: `docs/hipaa-security-rule-transition.md` (NPRM identity table + 18 items),
  `docs/cmmc-odp-baseline.md`, `docs/standards-currency.md` rows, feed-registry notes.
- CI history for every pushed sha.

## Pass 1 — source integrity (re-fetch + re-hash)

75 of the 76 provenance URLs were re-fetched on 2026-08-09 by script (scratchpad
`audit/pass1_results.json`); the 76th (`au-iso-15408`) held an empty URL string and so was
never fetchable — a defect this pass did not detect, found later by the phase-33 audit
(finding C-1) and repaired in `38b69f0`. Of those fetched, **66 resolved to the cited page
with the recorded verbatim present**. The 10 flags, dispositioned:

| Record | Flag | Disposition |
|---|---|---|
| `au-cmmc-phase2`, `au-cmmc-171r3-transition` | binary PDFs, no text match | **VERIFIED stronger**: live re-download sha256 == pinned sha256 (`e5a0fdc3…`, `fd83ecf4…`) — byte-identical to the committed pins |
| `au-cmmc-rfi`, `au-cmmc-taskforce-report` | war.gov 403 at audit time | Bot-wall variance; the 2026-08-08 origin read stands (logged in the WS-1 checkpoint with verbatims). Environment-limited re-verification, noted per §2 (a blocked re-check does not upgrade or downgrade) |
| `au-hipaa` | verbatim mismatch | **FINDING-1 (fixed this commit)**: the stored verbatim had an editorial "; " inserted into the timetable text. reginfo.gov static fetch confirms every component ("NPRM 01/06/2025 90 FR 898 Final Action 07/00/2027", stage "Long-Term Actions"); verbatim corrected to the exact rendered text |
| `au-anthropic-api` | cited URL now 404s | **FINDING-2 (fixed this commit)**: /en/api/changelog serves only a 404 SPA shell; block repointed to the /en/api landing (re-fetch confirms the new verbatim live) |
| `au-circia` | harness could not fetch | **FINDING-3 (fixed this commit)**: unencoded `[]` in the stored FR API URL globbed in curl; URL stored percent-encoded (content re-verified identical: town-hall PRORULE docs only, no Rule) |
| `au-google-gemini-api` | OAuth redirect loop at audit time | ai.google.dev now bounces static fetchers into an auth redirect; the 2026-08-09 00:54 origin read (200, verbatim asserted, body on disk) stands. Environment-limited |
| `au-disa-cci-quarterly`, `au-chile-21719` | HTTP 200 on a DEAD_END record | The 200s deliver the same obstacle pages the blocks describe (cyber.mil SSO/JS wall; bcn.cl server-side timeout notice) — DEAD_END manifests as a wall page with a 200 status; state stands |

Artifact re-hash: all 4 `source_data/dod/` pins match their recorded sha256s; the two memo
PDFs additionally match fresh downloads from their dowcio.war.gov URLs.

## Pass 2 — claim support (field states no more than its snippet)

Verbatim-presence is mechanically guaranteed for the 68 backfilled blocks — the generator
asserted every verbatim against its fetched body before writing (`gen_blocks.py`), and pass 1
re-confirmed 66/76 live. Named high-value targets re-checked by hand:

- **Suspension boundary** (`au-cmmc-phase2`): record states L1(Self)/L2(Self) only, no
  waivers, 7012 remains — each phrase present in the pinned implementation memo (hash-verified
  above). The suspended-vs-in-force boundary is stated in origin form.
- **Dates**: RFI 2026-08-14 (THIN, SAM.gov-cited — correctly not WELL_SUPPORTED);
  2025-09-10/2025-11-10/2026-11-10 rule dates (FR API origin, re-confirmed);
  reginfo July-2027 + edition 202510 (re-confirmed at reginfo, including the stronger
  "Long-Term Actions" stage signal); 90 FR 898 / RIN / docket / 4,747 comments (FR API).
- **NPRM timeframes** (the mutation-prone numbers): 24-hour, 72-hour, 6-month, 12-month
  items in the transition doc match the HHS fact-sheet enumeration; the doc explicitly
  defers FR-text verbatims as a named follow-up (stated, not silently missing).
- **Materialized close-outs** write no more than their snippets: IR 8477 and 800-172 close
  on "Date Published" statements; FedRAMP Class A closes on "Available now" (a current-state
  statement); `au-fedramp-ready-sunset` was deliberately NOT closed because its evidence is
  a schedule line, not a completion notice — the distinction held.
- **Drift repairs** each carry the authority's own text (July-2025 800-63 dates, OpenAPI
  3.2.0 release line, MCP 2025-06-18, C-27 "prior session", OCC CAT sunset).

## Pass 3 — chain and mutation integrity

- Support labels justified: `au-hipaa` is CONTESTED (not WELL_SUPPORTED) with both signals
  recorded; `au-cmmc-171r3-transition` CONTESTED on timing; single-weak-read and
  wall-blocked records are THIN (18 total); no UNSUPPORTED written anywhere.
- Terminal states justified: no ORPHAN_CONFIRMED or CIRCULAR_UNRESOLVED claimed (none
  earned — environmentally blocked escapes stayed DEAD_END per §2); every DEAD_END names
  its obstacle in the record notes.
- Grep sweep of all 36 changed files against the §5 trap list: zero `[FROM RECALL` in
  canonical files; "CMMC 3.0" and "NPRM goes into effect" appear only as the protocol's own
  trap definitions; no rescind/cancel language about the program; the eliminated -7019
  appears only with its elimination stated; hedges intact ("agency projection",
  "firmly in place", "until further notice", "not a commitment").
- CI story verified against the Actions history: `1cf7aa3` green → `c1f5f3b`/`1a8ca33`
  **red** (the secret-scan CI backstop caught the org-mailbox-in-CFR-text finding after an
  incomplete local gating sequence — the backstop working as designed) → green from
  `4af0bf9` (reasoned path allowlist) through `075dc74`, `670d9a2`, `e9725fe`. The
  2026-08-03 `standards-watch` failure on `f0febb0` predates this phase (monthly drift run
  on the pre-phase sha; superseded by this phase's refresh work).
- Salvaged-evidence handling: batch-0 agent evidence (FFIEC, ARC-AMPE, FedRAMP rules) was
  re-verified by fresh fetches before use except the ARC-AMPE Vol I PDF, whose URL was not
  re-located — that claim was therefore NOT written into the record; `au-cms-arc-ampe`
  carries only the re-verified ARS page read (THIN) with the re-pin named as follow-up.

## Pass 4 — adversary output (mandatory)

**The single claim most likely to be wrong:** the Feb-2026 DFARS clause-renumbering map in
the `dfars-cyber` feed label — "252.240-7997 (ex -7020); FAR 52.240-93 (ex 52.204-21);
-7019 eliminated Feb 2026."

**Why this one:** it is the only load-bearing claim in the phase shipped without any origin
read. The DPCAP class-deviation memos on acq.osd.mil stayed bot-walled through every
attempt; support rests on one law-firm analysis (Latham, corroborating -7997 only) plus
trade press (Secureframe) for the full map. The July-2026 implementation memo citing
**FAR 52.204-21** as the operative L1 clause already proved the popular "renumbered/
eliminated" framing is itself a mutation (deviation clause numbers used in solicitations,
not CFR text changes) — the same mutation pressure applies to every other detail of the
map, and the -7019 "elimination" and the exact -93 number have no primary behind them at
all.

**Specific evidence that would overturn it:** the class-deviation memo texts (attachment
clause lists and effective-date lines) showing different deviation numbers, a different
disposition for -7019 (e.g. suspended-in-deviation rather than eliminated), or scope limited
to certain solicitation classes.

**Where it would be found:** DPCAP/DARS class deviation index at
acq.osd.mil (Defense Pricing, Contracting, and Acquisition Policy → class deviations,
2026-O-series), mirrored on DAU's acquisition.gov community pages; or any solicitation on
sam.gov issued after Feb 2026 quoting the deviation clauses in section I. Until one of
those is read, the label's framing ("class deviations", not CFR renumbering) is the
protective hedge — and it is present.

**Runner-up:** the `au-cmmc-taskforce-report` window (~2026-09-11) is derived arithmetic
("final report to the DoW CIO within 60 days" from 2026-07-13) — the basis states the
derivation, but "60 days" could run from a different anchor or slip without announcement;
overturned by any DoW CIO statement, found at war.gov releases or the dowcio.war.gov
library.

## Findings → fixes

| # | Finding | Fix | Commit |
|---|---|---|---|
| 1 | `au-hipaa` verbatim carried an editorial "; " not on the page | Verbatim replaced with the exact rendered timetable text; re-matched live | this commit |
| 2 | `au-anthropic-api` cited a URL that now 404s | Repointed to the live landing; new verbatim re-matched live | this commit |
| 3 | `au-circia` provenance URL unencoded (`[]` globs in curl) | Percent-encoded; content re-verified identical | this commit |

Affected pass (1) re-run after the fixes: all three records now fetch and match
(re-verified live before commit). No findings in passes 3–4 required data changes.

**Phase-33 follow-up (independent audit of this phase, 2026-08-09).** A separate full-surface
audit re-ran this document's checks and found what this pass could not see, because its
DEAD_END branch skipped URL validation entirely: `au-iso-15408` carried an empty
`primary_source_url` (C-1, repaired `38b69f0`), and the Pass-1 sentence above overstated
coverage by one record (G-2, corrected above). The gap is now mechanized rather than left to
practice — `load_anticipated_updates()` hard-fails on a non-http provenance URL in every
terminal state (`cd1449c`), so this record class cannot ship unauditable again.

## Residual risk (never an all-clear)

1. **The clause-renumbering map** (adversary target above) remains THIN until a DPCAP
   memo is read — most likely to be wrong in detail.
2. **Ten browser-gated records** (DEAD_END/THIN walls: ISO ×3, IEEE, DISA, SWIFT, MeitY,
   CISA, Chile, HITRUST) were verified only as obstacles; any of those authorities could
   have shipped a revision this phase would not have seen. The OVERDUE/DUE_REVIEW
   escalations are the designed recovery, not a guarantee.
3. **Temporal proximity:** the audit re-fetched sources hours after the writes; it proves
   the claims match today's pages, not that they will survive the next agency action.
   The most volatile: the reginfo July-2027 projection and everything CMMC during the
   reform review (report window opens ~September).
4. **Single-read WELL_SUPPORTED labels:** most csrc/eur-lex/fedramp blocks rest on one
   origin page (the authority's own, corroborated by the repo's pinned data) — a
   compromised or mis-rendered page would propagate. Mitigation is the enum-enforced
   re-verification cadence, not this audit.
5. **What was NOT verified:** the 18 NPRM items' FR-text verbatims (fact-sheet-sourced,
   named follow-up), the AHA/AMA withdrawal letters at origin (secondary-reported,
   CONTESTED label carries the uncertainty), the SAM.gov RFI page (THIN), and the CIO
   policy memo referenced by the implementation memo (never located).

A clean re-run of this audit after the task-force report lands is the next scheduled
falsification opportunity (`au-cmmc-taskforce-report` escalation).
