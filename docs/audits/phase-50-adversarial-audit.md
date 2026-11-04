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
  as test fixtures where tests use them.
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
| Monthly request plan | `tools/fetch_census.py --check` | 423 (193 ungoverned) → **328, 0 ungoverned**; busiest host api.github.com 37 of 50 |
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
   - But the first live governed run found 2 more registered URLs disallowed, on hosts never
     swept (`capitol.texas.gov`, `www.ismap.go.jp`). **Overturned.** The census can only check
     hosts whose robots it has; the live ledger is the complete check, and now it runs monthly.
3. **"GitHub calls are safely under the limit."** Overturned for CI. The workflow called
   unauthenticated at 37–55 calls per run against 60/h per IP. It now passes its token, which
   allows 1,000/h per repository.
4. **"DISA dropped these STIGs on purpose."** Holds for 16 of 20 via the revision history. For
   the rest (the Exchange Mailbox STIGs) it is unproven, so the flag is factual, not "sunset".

## Residual risk
- **Four hosts' robots files fail TLS or time out from the session network.** On CI runners
  they may differ; the monthly ledger will say.
- **KEV and ATT&CK artifacts are `artifact_stale`.** `--fetch` and the ATT&CK v20 ingest are
  owed.
- **SCF 2026.3 and ATLAS v2026.10 are pending issuer confirmation.**
- **15 kept STIGs remain at their last harvested release.** Their final zip is date-coded or
  not served.
- **The `.meta` sha short-circuit in the NCP signal is effectively inactive.** NCP regenerates
  the feed daily with a new `pub_date`. This is accepted: the cost is 2 requests a month.
- **Manual-only loaders are not yet behind the governor** (fr_watcher, nvd_api_loader,
  kev_loader and others). The census covers only the monthly path, and says so.
