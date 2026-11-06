# Phase-50 closing adversarial audit — 2026-11-04

**Scope.** This audit covers the regulatory-currency writes:
- **`feed_registry.json`, 14 feeds.** Four verified version moves, a repo repoint, two
  robots-compliance landing repoints, `nist-ncp` made poll-exempt, the STIG library re-pin, and
  seven re-verifications.
- **`framework_changelog.json`:** the entry `chg-disa-stig-library-2026-10`.
- **`source_manifest.json`:** the STIG library version.
- **The new canonical registry `host_policies.json`.**
- **The STIG artifacts.**

Written to satisfy the regulatory-phase closing gate (`protocol-layer/quality-gates.md`).

**Origin.** The user asked for a plan to add STIGs to the monthly update feed and to make sure
each seed source's usage rules are known, so the subsystem never overloads a host or gets
banned. The plan was executed read-only before approval. The plan, research record and test
transcripts are summarised in `docs/source-inventory.md` (Phase 50).

## Pass 1 — source integrity
- **Every published rule was quoted from the host's own page on 2026-11-04.**
  - NCP: the data-feeds route text in the site bundle.
  - NVD: `/developers/start-here`.
  - GitHub: the REST rate-limits page.
  - eCFR: the API documentation's full-XML entry.

  Hosts with no stated rule say "none published" with the date checked; no limit was invented.
- **robots.txt was fetched from 17 hosts** (none publishes a Crawl-delay). They are committed
  as test fixtures where tests use them. An 18th, `www.ismap.go.jp`, was fetched after the CI
  dispatch (39 B, "User-agent: * / Disallow: / / Allow: /csm") and committed as a fixture.
- **The DISA October 2026 library was hashed on download** (sha256 `ea581eb2…d1d`,
  375,827,141 B). The refresh re-verified size and hash before distilling it. It was never
  re-downloaded and never committed.
- **NCP's sha-256 was proven to be the zip's own hash** on a real listed zip
  (`U_MS_Windows_Server_2016_V2R10_STIG.zip`). That is the precondition for using NCP hashes
  to verify downloads.
- **The NCP feed download was verified against its `.meta` sha256** before parsing.
- **The live CCI list was verified at origin.** `U_CCI_List.xml` from DISA is byte-identical
  (sha256 `a9e3850f…`) to the committed copy. The zip's newer HTTP date (2026-04-28) is a
  repackage.

## Pass 2 — claim support
| Claim | Probe | Result |
|---|---|---|
| The monthly STIG check could never report drift | replay of the real `--check --json` output through the phase-21 parser; the first live governed run | multi-line JSON → `}` → check_failed. Then, once the producer emitted one line, `_run`'s 4,000-character tail **truncated** it → check_failed again. Both causes are fixed and pinned by selftests (10/10) |
| trackr was not unreachable | the same 2026-11-03 run's CCI check | `cci_status: current` (trackr answered) |
| 164 of 383 benchmarks were stale | live `stig_harvest --check` (trackr) | 164 stale, 185 changed, 22 new titles |
| DISA dropped RHEL 8 / WS2019 deliberately | the library's own revision history | listed as "Deleted content that has been sunset/removed" (09/30/2026, 07/01/2026); the Exchange Mailbox STIGs are **not** listed, so the DB flag states only "not in the current library" |
| Refresh outcome | `--full --retain-absent --refresh-final`, `--refresh-stale --allow-trackr-crawl`, rebuild | 407 benchmarks / 20,842 rules / 539 CCIs; library, NCP and trackr all `same` |
| Monthly request plan | `tools/fetch_census.py --check` | 423 (193 ungoverned) → **328, 0 ungoverned**; busiest host api.github.com 37 of 50. **Corrected (0.15.1):** GitHub was undercounted (live: 54). The upper bound is now **327**, api.github.com **38** of 50 (Pass 4, item 5) |
| Version moves | live tag (2026-11-03 run) + issuer page | OpenAPI 3.2.1, ATT&CK v20.0, MCP 2026-07-28 and OSCAL 1.2.3 confirmed. SCF 2026.3 and ATLAS v2026.10 had no issuer statement, so they stay pending |
| Witness ripple | before/after counts on `grc.db` | pairs 180,413 unchanged; confirmed 23,551 → 23,540; corroborated +13; reachable −2; STIG-exercised witness 15,057 → 15,028; oracle benchmark: all metrics at or above pins |

## Pass 3 — chain / mutation integrity
- **Every registry write went through `tools/registry_io.py`**, with round-trip asserted before
  and after saving. `host_policies.json` was added to `registry_io` and to sync_check
  invariant 14.
- **Committed code equals tested code.** Every implementation block from the approved plan was
  spliced into its file and verified **AST-identical** to the code that ran during planning.
  Deviations are deliberate and each has its own test:
  - `retain_absent` now keeps `last_library` across repeated refreshes. Review caught the
    tested version mislabelling a benchmark kept twice; the new test is red on the old code.
  - `mode_full` hashes the zip in chunks.
  - The context patterns live in `doc_claims.json`, not in a checker constant.
- **The STIG map stays byte-deterministic** (fixture test). `_merge_and_rewrite` now carries
  `library_sha256` and the distill stats forward. The first refresh had dropped them, so it was
  re-run before commit.
- **Every commit was bisect-walked green before push.** The pre-push hook ran the CI rehearsal.

## Pass 4 — adversary, run
1. **"The parser, not the network, blinded the check."**
   - Disconfirming probe: if trackr were down on the runner, the same-host CCI check would fail
     too.
   - Ran: it did not fail. **Holds.**
   - Then the adversary ran *again*, on the first live run of the repaired code. It found a
     second cause (truncation) that every offline test had missed, because those tests
     injected the payload.
   - Lesson recorded: offline fixtures prove a parser, but only a live run proves the pipe.
2. **"No seed URL breaks robots."**
   - The first sweep was a false clean, caused by the stdlib parser.
   - The RFC-faithful sweep was clean for 157 URLs on hosts with fetched robots files.
     *Correction (item 5):* that sweep was blank-line-faithful but still used the stdlib's
     first-match precedence, so it was not fully RFC-faithful.
   - But the first live governed run found 2 more registered URLs disallowed, on hosts never
     swept (`capitol.texas.gov`, `www.ismap.go.jp`). **Overturned.** The census can only check
     hosts whose robots it has; the live ledger is the complete check, and now it runs monthly.
3. **"GitHub calls are safely under the limit."** Overturned for CI. The workflow called
   unauthenticated at 37–55 calls per run against 60/h per IP. It now passes its token, which
   allows 1,000/h per repository.
4. **"DISA dropped these STIGs on purpose."** Holds for 16 of 20 via the revision history. For
   the rest (the Exchange Mailbox STIGs) it is unproven, so the flag is factual, not "sunset".
5. **"The close-out code passes from GitHub's own runners."** Ran: the `standards-watch`
   dispatch on `201ab5c` (run 41936204283, `fetch=false`, green, oracle benchmark included).
   - **Holds** for the STIG verdict: `stig_status: current`, and library, NCP and trackr all
     read `same`. The pipe that was blind July–November now carries a live verdict.
   - **Overturned twice** by the run ledger, against the plan's pass condition
     ("`policy_refusals == 0`; max per host ≤ cap"):
     - **Robots precedence.** `www.ismap.go.jp/csm` was refused, though that file allows it.
       The stdlib parser applies the first matching rule, and RFC 9309 §2.2.2 requires the
       longest one, with allow winning a tie. So item 2's "RFC-faithful" sweep was faithful to
       blank lines only. fetchkit now evaluates robots itself (`RobotsRules`). It is pinned by
       the ISMAP fixture, which is red on the stdlib parser, and by the RFC's six precedence
       examples. Re-swept, 64 URLs on 16 hosts with fetched robots files gave exactly one
       changed verdict (that URL).
     - **GitHub.** api.github.com made 54 calls: no process exceeded its cap of 50, but the run
       total did. The census had said 37.
       - Cause: `framework_monitor` and `standards_refresh` both looked up all 19 release
         feeds, though `standards_refresh` reads only the monitor's exit code.
       - Why the census missed it: it answered every lookup with a release, so it never
         counted the tags fallback.
       - Fix: the monitor now skips `github_release` in that path. The census answers every
         release lookup with 404 (a true upper bound): red at 74 > 50 without the skip, green
         at 38 ≤ 50 with it.
   - The other six refusals are the four TLS/timeout hosts, failing the same way from the
     runners.
   - Lesson: the census is an upper bound only for the responses it models. Its stand-in
     responses must take each fallback branch, not the happy path.
   - **A third defect, found by the pre-push rehearsal after a live local run.** The offline
     governors (tests, census, release selftest) passed `state_path=None` meaning "no state".
     The constructor read it as "the shared `.fetch-cache` file".
     - What it caused: the tests hit a real `www.cisa.gov` cooldown, and the census counted
       304 instead of 327 with no violation.
     - Why CI never showed it: CI starts with no `.fetch-cache`.
     - Fix: `None` is now stateless, pinned by a planted-breaker test (70 assertions).
   - **Second dispatch** (run 41940244303, on `0a295f5`, green).
     - **Holds:** the three fixes. ISMAP `/csm` was admitted (2 requests, 0 refused).
       api.github.com made 28 calls (cap 50) and was the busiest host. No host exceeded its cap.
       230 requests in all, and the STIG verdict is still `current`.
     - **Overturned once more** by its 23 refusals.
       - 16 refusals on `github.com/…/releases.atom` are **correct**. GitHub's `*` group
         disallows `/*.atom$`, which the stdlib parser cannot express. So the 18
         `announcement_feeds` entries had broken GitHub's rules every month until then.
       - 1 refusal on law.lis.virginia.gov was a **matcher defect**. A `Crawl-delay` line did
         not end the user-agent run, so `GPTBot: Disallow: /` merged into `*`. Fixed, and
         pinned by the real file.
       - The other 6 are the TLS/timeout hosts.
     - Neither GitHub nor Virginia was in the robots sweep: no file was held for either.
       Once again only the live ledger saw them.

## Residual risk
- **Four hosts' robots files fail TLS or time out**, from the session network and (measured,
  run 41936204283) from GitHub's runners alike: `www.acq.osd.mil`, `www.cnss.gov`,
  `www.ilga.gov` ("unable to get local issuer certificate") and `www.cyber.gov.au` (timeout).
  Their feeds fail the same way, so this is unchanged reachability, now named in the ledger.
- **KEV and ATT&CK artifacts are `artifact_stale`.** `--fetch` and the ATT&CK v20 ingest are
  owed.
- **18 `announcement_feeds` entries point at URLs GitHub's robots disallows**
  (`…/releases.atom`, 16 distinct). The governor refuses them, so no request is sent, and the
  release signal comes through the API. They add 16 refusals to every monthly ledger until
  they are removed or replaced via `registry_io`.
- **Seven release rows stay `registry_stale`** for want of an issuer statement:
  - scf 2026.3: the SCF download page still names 2026.2.
  - mitre-atlas v2026.10: atlas.mitre.org states no version.
  - cisa-scubagear and openai-api: the registry carries free text.
  - Three OWASP rows: the first tags-API entry is not a release of record.
- **Eight release rows are `check_failed`.**
  - Five repositories publish no releases or tags: cisa-csaf, cisa-kev, enisa-ecsf, fedramp
    (`FedRAMP/rules`) and huggingface-hub.
  - For three (csa-ccm, csa-star-ccm5, nist-ai-rmf) the repository itself answers 404.

  Each needs a check-strategy change or a repoint, backed by evidence.
- **15 kept STIGs remain at their last harvested release.** Their final zip is date-coded or
  not served.
- **The `.meta` sha short-circuit in the NCP signal is effectively inactive.** NCP regenerates
  the feed daily with a new `pub_date`. This is accepted: the cost is 2 requests a month.
- **A fresh-checkout build is not byte-identical to a warm one** in one generated file.
  - What differs: `uncertainty_ledger.jsonl` gives five NIST CSF 2.0 CCI-basis `overlap_pct`
    rows 0.1 lower (e.g. CSF 2.0 ↔ 800-171 r3: 50.7 vs 50.8).
  - How measured (2026-11-05): the `--standards-watch` rehearsal build, with its outputs
    hidden as on a CI runner, against a warm rebuild of the same commit.
  - The committed file matches the warm build, and the oracle benchmark passes both ways.
  - Not attributed: some gitignored artifact under `cross-mapping/output/` that the fresh path
    does not regenerate. Phase 50 does not change these rows.
  - **Correction of record (phase 52, 2026-11-06): attributed.** The fresh path downloaded the
    upstream OSCAL catalog from an unpinned `main` URL, while the committed derived data had been
    built from the 2026-10-19 copy; the committed `oscal_v5.2.0_full_extract.json` could not stand
    in (no part trees). Given the same catalog, a fresh build reproduces `uncertainty_ledger.jsonl`
    exactly (0 of 247 lines differ). Phase 52 committed that catalog as the build input
    (`canonical-sources/source_data/nist-800-53/`), so a fresh checkout builds from the same input
    as the committed data.
- **Manual-only loaders are not yet behind the governor** (fr_watcher, nvd_api_loader,
  kev_loader and others). The census covers only the monthly path, and says so.
