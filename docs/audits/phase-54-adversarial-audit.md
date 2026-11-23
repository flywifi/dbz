# Phase-54 closing adversarial audit — 2026-11-23

**Scope.** `source_manifest.json` (`upstream_check` on 22 sources), `fetch_schedule.json` (the Monday
job's measured requests), `feed_registry.json` (six dead links superseded). No framework data,
mapping or schema changed. Written to satisfy the regulatory-phase closing gate
(`protocol-layer/quality-gates.md`).

**Origin.** The user asked to test more update feeds and avoid drift, then approved this scope:
a fingerprint check for sources that serve the file itself, the dead links repaired in the same
phase, each discovered change ingested separately, and the web-page-only feeds left for later.

## Pass 1 — source integrity
- **Every checked URL was fetched and compared before it was registered.** Four sources matched
  their committed files byte for byte (SP 800-171 r3, SP 800-172 r3 and SP 800-66 r2 CPRT exports,
  the Microsoft SSPA DPR); eighteen differed.
- **Each difference was examined, not assumed.** The FedRAMP rules carry a newer `info.version`;
  the schemas and the rules schema differ in parsed content (4 to 29 paths), not formatting; the
  corpus's `_sources.json` names newer commits; the OSCAL catalog's metadata shows a newer
  `last-modified` and OSCAL version with the same 1,196 control ids; the CCI mapping's rows differ
  at equal counts. The CSF 2.0 export differs at equal length and was not examined further.
- **Each replacement link answered 200** from this client on 2026-11-23. Two dead links have no
  confirmed direct replacement (the 800-171 workbook, the 800-66 PDF); their entries point at the
  publication page and say so.

## Pass 2 — claim support
- **"Report-only" is literal:** the tool has no write path to a canonical file.
- **Request counts are derived from the registered checks,** added to the Monday job's record, and
  the census gate passes (Monday 252 planned requests; csrc.nist.gov 22 of 25).

## Pass 3 — chain / mutation integrity
- **Commits:** `c7bca4d` anchor, `9acf5b5` the check, `2515861` the links, then this close-out.
  Each rehearsed package-free at commit time (22 steps from the check on); both stages were first
  applied and rehearsed in a throwaway clone.
- **Registries** written only through `tools/registry_io.py`; all round-trip identical.

## Pass 4 — adversary, run
1. **"A bot-challenge page will read as drift."** Selftest: an HTML body where JSON or a PDF is
   expected is `check_failed`. **Holds.**
2. **"A failed fetch will read as current."** Selftest: a failure without a change makes the run
   `check_failed`. **Holds.**
3. **"The rows reach the issue."** The workflow's script was run under Node against the real
   report: `upstream | drift` and 18 `upstream/<id>` rows render. **Holds.**
4. **"The existing checks would have caught these."** The dispatch of 2026-11-22 listed ATT&CK
   only. **Overturned**; that is the gap this phase closes.
5. **"Adding 22 requests breaks a host cap."** A test pinned Monday's raw-GitHub reads at 3 and went
   red in the rehearsal; the pin is now 9 and the census passes. **Holds after the fix.**

## Residual risk
- **The drift issue will list 18 rows until the ingests land.** That is the honest state.
- **About twenty feeds publish only a web page** and still report stored status.
- **A checksum cannot say what changed,** only that something did; review is manual.
- **csrc.nist.gov is at 22 of its 25-request cap on Mondays;** two CPRT exports are left out for
  that reason.
