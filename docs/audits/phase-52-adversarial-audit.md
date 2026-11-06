# Phase-52 closing adversarial audit — 2026-11-06

**Scope.** This audit covers every regulatory-currency write of the phase:
- **`feed_registry.json`.** Six feeds (illinois-bipa, cmmc, nist-800-171, cnssi-1253,
  asd-essential8, asd-ism: URLs, `superseded_urls`, `poll_exempt`); the 18 `releases.atom`
  announcement entries (`enabled: false`, `gated_reason`); nineteen release and `rss_feed` rows
  settled from issuer statements; mitre-atlas, openai-api and mitre-attack settled from the
  dispatch; the gdpr feed's dangling `source_manifest_keys`.
- **`framework_changelog.json`.** Three stubs, `human_confirmed: false`:
  `chg-scf-2026.2-to-2026.3`, `chg-owasp-llm-top10-2025-to-2026`, `chg-mitre-attack-v20.0-to-v20.1`.
- **`source_manifest.json`.** Four EUR-Lex article files and the OSCAL catalog.
- **`host_policies.json`.** `www.ilga.gov` (pinned intermediate) and `publications.europa.eu`.
- **`fetch_schedule.json`.** The `eurlex` job joins Tuesday; the build load is empty.
- **Canonical data.** KEV, two CFR files, EDGAR and SP 800-63B rewritten with only the guessed
  fields changed; four EUR-Lex files refetched; the OSCAL 5.2.0 catalog committed; one TLS PEM.

It is written to satisfy the regulatory-phase closing gate (`protocol-layer/quality-gates.md`).

**Origin.** The user asked for a detailed remediation plan for the system's existing problems with
no new features, in the seven-question format with pre-tested code
(`protocol-layer/planning-standard.md`). Four decisions were the user's: blank the guessed links;
keep the 18 atom entries gated, default off; pin intermediates and keep every superseded URL with
why it fails and where to go; SCF 2026.3 and SP 800-63B-4 are separate phases. The plan's research
record and transcripts are summarised in `docs/source-inventory.md` (Phase 52).

## Pass 1 — source integrity
- **Every URL change was confirmed live before it was written.** The new BIPA page answers 200
  through the pinned chain (87,164 B, "740 ILCS 14/15" present). Every DoD CIO host — the CMMC
  landing and PDF, the dowcio.war.gov mirror, www.war.gov — answers automated clients 403, which
  is why cmmc is `poll_exempt` with the URLs recorded as the confirmed location. All three
  acq.osd.mil URLs are 404 even after TLS verifies, so that host is not pinned.
- **The pinned intermediate is the issuer's.** It is the certificate at the leaf's AIA
  `caIssuers` URL (crt.sectigo.com, Sectigo Public Server Authentication CA OV R40, not-after
  2040-05-13), stored as PEM with its sha256 beside it. Partial chains are disabled, so it can
  only complete a chain to a public root. A tampered pin refuses before connecting.
- **Each registry settlement cites its issuer.** SCF: "SCF 2026.3 Sep 21, 2026 Major … 1,457
  controls renumbered" (securecontrolsframework.com). OWASP: "OWASP GenAI LLM Top 10 2026 August 3,
  2026 … the latest" (genai.owasp.org); "ASVS 5.0.0 Published 30 May 2025" (asvs.owasp.org). CISA:
  "announces the release of updated ScubaGear v2.0". ATLAS: "Updated ATLAS data to version 2026.10"
  (atlas.mitre.org/resources/updates/2026-10) and the issuer's GitHub release v2026.10. ATT&CK:
  "ATT&CK v20.1 / October 13, 2026 - current" (attack.mitre.org/resources/versions, read
  2026-11-06; the same page read v20.0 on 2026-11-05). OpenAI: the issuer's own release 2.0.0 of
  openai/openai-openapi, the feed's declared preferred check.
- **EUR-Lex comes from the documented channel.** EUR-Lex's reuse page names the Publications
  Office Cellar RESTful API; the loader's `Accept: application/xhtml+xml` call is the one the
  Cellar manual shows. The EUR-Lex HTML page itself answers HTTP 202 with an AWS WAF JavaScript
  challenge (saved as `cross-mapping/tests/fixtures/eurlex_waf_challenge_202.html`).
- **The OSCAL catalog is NIST's file verbatim** (5,136,923 B; metadata version 5.2.0, OSCAL
  1.2.2, last-modified 2026-05-11), byte-identical to the cache the committed data was built
  from. Its metadata carries NIST's organizational contact address; the secret-scan backstop
  allowlists the file by exact path with that reason, as phase 51 did for KEV. Upstream text is
  never edited.
- **Blanking removed claims; it added none.** Only `nist_families`, `nist_800_53_controls`,
  `cci_provenance`, `_cprt_url` and `_fetched_at` changed in the committed files; each file's
  own JSON formatting was preserved (measured per file before writing).

## Pass 2 — claim support
- **Every number names its probe** in the plan, the inventory record and this audit. Re-derived
  from the committed data at close: KEV 1,768 rows with 0 families; `cfr_requirements` 34/34
  blank; EDGAR 85/85 blank; 800-63B 26/26 without control links and without fetch stamps;
  `eurlex_articles` 322 (99/46/64/113) with 0 empty titles or texts; `host_policies` 15 hosts;
  `sync_check` 17 invariants; the census 230/10/6/65.
- **The dispatch is the measurement of the registry work** (run 42227394107, 2026-11-06): 233
  requests to 94 hosts, 0 refused; ilga.gov 2 requests, 0 refused; api.github.com 8 lookups
  (19 before); drift rows mitre-atlas, mitre-attack, openai-api, scf. After C4b the offline
  re-run of `_release_row` over the same observations leaves scf and mitre-attack, both
  `artifact_stale` with the reason "issuer version … confirmed; the committed artifact lags".
- **The fresh-build claim is measured, not inferred:** with the gitignored cache moved away, the
  build read the committed catalog, `uncertainty_ledger.jsonl` had 0 differing lines, and only
  `controls.generated_at` and `assessment_objectives.source_file` (bookkeeping columns) differed
  among table digests.
- **BENCHMARK's per-framework list is re-pinned from the database** (confirmed by framework,
  2026-11-06) and the correction names which figures had moved and why nothing caught it.
- **No claim relies on a source outside the session's scope.** Issuer statements came from the
  issuers' own sites; release tags from the dispatch's api.github.com reads (this session's own
  unauthenticated lookup answered 403, so the artifact was read with the workflow token through
  the same tool class `ci_status.py` uses, never raw curl).

## Pass 3 — chain / mutation integrity
- **Every registry write went through `registry_io`** and round-trips byte-identical:
  `feed_registry`, `framework_changelog`, `source_manifest`, `host_policies`, `fetch_schedule`.
- **Every commit was gated after commit and rehearsed package-free before its push**
  (`ci_rehearsal.py`, the runner's condition); the pre-push hook enforces it. Two rehearsals went
  red and were fixed before pushing (below). CI on the pushed heads at close: C1 `b7f8525` no run listed; C2–C4 `889fde2` success; C5 `948404e` success; C6 `a1b9474` success; C4b `1e016cc` success; C7 `3da5179` success; C8 `3e9d401` success; C9 `0ee289c` success.
- **Red then green, each with its transcript in the plan:** the Tuesday writer (T-1), robots retry
  (T-2), the tampered pin (T-3), the gated entries (T-4), the EUR-Lex fixtures (T-7), invariant 17
  and the widened invariant 14 on HEAD's text versus the tree (T-9, re-run at C8), the workflow
  test on the pre-C7 schedule.
- **The private production data was not touched;** no provider identifier appears in any new
  text.

## Pass 4 — adversary, run
1. **"The Tuesday job is safe because volatile keys are stripped."** Ran: `substantive=True` with
   zero new documents. **Overturned**, and the run found a second changed key (`_usage`, which the
   shipped writer *adds*) the research had missed.
2. **"The fresh/warm gap is the OSCAL input."** Ran: 0/247 ledger lines differ with the warm
   catalog on the committed path. **Holds** for the derived data; **partly overturned** for "every
   digest equal" (two bookkeeping columns).
3. **"The Cellar is a workaround for EUR-Lex's bot check."** Ran against EUR-Lex's own reuse page:
   it is the documented channel. **Holds.**
4. **"Pinning acq.osd.mil restores CMMC; DoD CIO is a confirmed replacement."** Ran: TLS verifies
   but all three URLs are 404; then every DoD CIO host answers 403. **Overturned twice.**
5. **"Blanking families breaks nothing."** Ran: two skill evals quoted family codes. **Partly
   overturned**; evals updated.
6. **"A quiet KEV week opens a PR."** Ran: 0 differing keys after the volatile strip. **Holds** (no
   false PR).
7. **"Gating the atom entries changes other requests."** Ran: 78 requests before and after,
   identical. **Holds.**
8. **"A pinned SCF row would print `current` while the artifact is stale."** Ran: it prints
   `artifact_stale` only because `_release_row` keeps it. **Holds** by construction.
9. **"One 502 on robots.txt loses a whole slot."** Ran: the shipped method refuses after one
   attempt. **Confirmed**, and fixed (admitted on the retry; three 502s still disallow).
10. **"The plan's settlement rule works on the real API note."** Ran against the dispatch artifact:
    the note for a release is the string `'latest release'`, not `None` as the plan's fixture
    assumed, so the rule as written would have moved ATLAS and OpenAI to landing polling.
    **Overturned**; the rule applied is `api_note == 'latest release'` ⇒ release ⇒ version + pin.

**Found during implementation, each red then green:**
- **The CFR files carry two lists.** `requirements[]` beside `sections[]`, and `build_db` reads the
  former; the first blanking left 18 non-blank rows. Both lists are blanked now (34/34).
- **A certificate PEM read as key material.** The health audit's `data_at_rest` rule flagged the
  pinned intermediate; the rule now exempts certificate-only PEMs, proven on a planted key and a
  planted private-key PEM in the golden set.
- **`| tail -1` hid two failing exit codes** (a health-audit block and a `global` SyntaxError in
  the selftest that reached a commit). Every gate chain now runs under `set -o pipefail`.
- **ATT&CK v20.1 was real drift** the plan did not list. It is recorded, not re-ingested.
- **The secret-scan backstop** flagged the OSCAL catalog (NIST's contact address) and the new
  test's placeholder contact. The file is allowlisted by exact path with its reason; the test uses
  a noreply-form address, as phase 51 did.
- **A fourth workflow** (`instruction-audit.yml`) pinned `checkout@v4`; bumped with the three.
- **`cprt_traverser --auto-download` never existed** and olir_crawler never invoked it; the usage
  line is deleted rather than reworded.
- **The workflow test pinned the build's request count**; it now asserts the build makes none.
- **This session's api.github.com lookups answered 403**, so the dispatch's artifact, not a local
  re-poll, settled the three rows.

## Residual risk
- **ATT&CK artifact v20.0 versus issuer v20.1.** The Thursday slot compares TAXII with the committed
  file and proposes the ingest as a PR; until merged the drift issue shows the row.
- **SCF 2026.3 (Major) and SP 800-63B-4** are separate phases; both rows say so.
- **The blanked fields stay blank** until an issuer mapping is adopted; the skills flag
  `human_review_required`.
- **CMMC is not polled** while every DoD CIO host answers 403; the Federal Register DoD feed carries
  CMMC rulemaking.
- **The 18 atom entries stay gated** by the user's decision; the reason on each says why not to
  re-enable them.
- **Cellar format drift** would fail closed (nothing written) and show in the Tuesday digest.
- **Upstream OSCAL `main` may differ from the committed copy**; adopting it is a reviewed diff via
  `standards_refresh --fetch`.
- **The first scheduled Monday run after this phase** (2026-11-09) is the live confirmation of the
  refusal count; the slot pin (2026-11-19+) and the owner's PR setting remain open.
