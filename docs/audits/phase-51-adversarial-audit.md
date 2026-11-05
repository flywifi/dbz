# Phase-51 closing adversarial audit — 2026-11-05

**Scope.** This audit covers the regulatory-currency writes:
- **`feed_registry.json`, 2 feeds.** `mitre-attack` (v20.0 ingested; `source_manifest_keys`
  repointed to an entry that exists; TAXII and CTID URLs) and `cisa-kev` (catalogVersion
  2026.11.04).
- **`framework_changelog.json`.** The new entry `chg-mitre-attack-v19.1-to-v20.0`, and the
  provenance block that the phase-50 entry `chg-disa-stig-library-2026-10` shipped without.
- **`source_manifest.json`.** The new entry `mitre-attack-enterprise`.
- **Two canonical registries.** A new one, `fetch_schedule.json`, and `host_policies.json`
  (`eur-lex.europa.eu` added).
- **The ATT&CK and KEV artifacts.**

It is written to satisfy the regulatory-phase closing gate (`protocol-layer/quality-gates.md`).

**Origin.** The user asked for:
1. everything that can be automated to run weekly, spread across weekdays;
2. canonical changes to arrive as pull requests;
3. NVD, FIPS and OLIR to be report-only, with a commit suggestion waiting at the next session;
4. the ATT&CK v20 ingest;
5. slots placed where GitHub has the least traffic.

KEV refresh was approved separately. The robots.txt items were omitted by the user. The plan
was executed read-only before approval. Its research record and test transcripts are summarised
in `docs/source-inventory.md` (Phase 51).

## Pass 1 — source integrity
- **ATT&CK comes from MITRE's own TAXII 2.1 server.** The Enterprise collection was paged at 100.
  The 706 live attack-patterns split **227 techniques + 479 sub-techniques**, which are exactly
  the counts MITRE states on attack.mitre.org/resources/updates. The version (20.0) comes from
  the collection object, not from a file name.
- **The control mapping is the issuer's.** It is CTID Mappings Explorer (MITRE), fetched from
  ctid.mitre.org. Its `metadata` names the ATT&CK version (16.1), the framework (nist_800_53
  rev5) and `last_update` 04/16/2025; all three are recorded in `nist_mapping_source`. The NIST
  v13 spreadsheet the loader had pointed at answers 404, which is why every committed mapping was
  the keyword fallback. That fallback is deleted.
- **KEV comes from www.cisa.gov** through the governed loader, 1 request. The file is CISA's text
  verbatim; the loader adds only `nist_families`.
- **Each changelog verbatim was quoted from the issuer.**
  - ATT&CK: "The October 2026 (v20) ATT&CK release updates Techniques, Groups, Campaigns and
    Software for Enterprise, Mobile, and ICS." (attack.mitre.org/resources/updates, retrieved
    2026-11-05).
  - DISA (correction of record): the revision-history PDF inside the October 2026 library zip.
- **`eur-lex.europa.eu` is recorded as "none published".** That is the result of searching
  eur-lex.europa.eu and op.europa.eu for a usage or rate statement on 2026-11-05. The enforced
  3.0 s equals the loader's previous delay, so EUR-Lex is not hit faster than before.

## Pass 2 — claim support
- **Every number in the phase's docs names its probe.**
  - T-2: the live dry runs.
  - T-9: the ATT&CK ingest.
  - T-11: KEV adds and drops.
  - R9: queue delay.
  - The census.

  Re-derived from the committed files at close:
  - ATT&CK: 20.0, 706 / 479 sub, 454 mapped, 252 blank, 10 notes, 5,264 pairs over 470
    techniques, 109 controls.
  - KEV: 2026.11.04, 1,768 records.
  - `host_policies`: 13 hosts.
- **The NVD suggestion's figures come from the run that produced them:** 9,676 CVEs, 7.3 MB,
  about 382 MB a year. The digest recomputes them every week.
- **The four "not scheduled" reasons are each a measured response,** recorded with its date in
  `fetch_schedule.json`: 0 articles; CMVP unavailable; 404; 404.
- **No claim relies on a source outside the session's scope.** The OSCAL and ATT&CK raw-GitHub
  counts were computed from file size and window size, or taken from the TAXII server, not
  fetched from those repositories.

## Pass 3 — chain / mutation integrity
- **Every registry write went through `registry_io`,** and each round-trips byte-identical.
  `fetch_schedule.json` is registered in `registry_io.CANONICAL`, `sync_check` and the health
  audit's hygiene list.
- **The bot cannot write the default branch.** `rotation_commit.sh` pushes only
  `auto/refresh-<slot>`. `test_weekly_workflows.py` runs it in a throwaway repository with a bare
  remote and asserts the remote's default branch is unchanged. It also asserts the commit carries
  GitHub's noreply bot identity, the message is trailer-free, and only the report's changed files
  are committed.
- **A report-only job cannot leave a change,** and a change of volatile stamps alone is restored
  byte-for-byte (`test_rotation.py`, on the real 45 CFR 164 file).
- **Each commit C0–C7 was gated after commit** with `ci_rehearsal` (the artifacts-hidden CI
  condition), and the branch was bisect-walked before the push.

## Pass 4 — adversary, run
1. **"CTID's 16.1 mapping fits v20."**
   - **Partly overturned.** 10 mapped techniques were renamed, some broadening scope ("Browser
     Extensions" → "Software Extensions").
   - Each now carries a `nist_mapping_note`. The 15 ids that v20 deprecated or revoked are
     excluded by construction.
2. **"Stripping volatile keys never hides a real change."**
   - **Holds.** Every volatile key in the six PR-written files is a single stamp.
   - On 2026-11-05, 45 CFR 164 differed only in `_as_of_date`, with all nine sections identical.
3. **"Every automated job works under the recorded rules."**
   - **Held for the rules, overturned for four sources.** There were 0 refusals.
   - EUR-Lex, FIPS, OLIR and CPRT return nothing, so they are recorded as not scheduled.
4. **"06:17 UTC is busy, so another hour is better."**
   - **Not decidable yet.** Five samples at one hour cannot rule out a constant
     repository-level delay.
   - No time is pinned until 14 days of six-time probe data exist.
5. **"Bot PRs will show CI."**
   - `health.yml` is dispatched on the refresh branch, the documented exception for
     `GITHUB_TOKEN`.
   - Whether that run is listed among the PR's checks can only be seen on the first real PR.
     The PR body carries the battery output either way.
   - **Open until the first PR.**
6. **"KEV only adds."**
   - **Holds for membership:** 137 added, 0 dropped.
   - **Every record changed upstream,** so description edits ripple into the build.

**Found during implementation, each red then green:**
- **Missing import.** The loader never imported `re`; the first live T-9 run raised `NameError`.
- **Wrong comparison in T-11.** Enriched records were compared with raw ones, which reported all
  1,631 as changed; corrected to compare CISA's own fields.
- **Probe attribution.** Nearest-earlier-fire attribution would have credited a 06:17 run that
  started at 10:05 to the 09:47 cron, hiding 3h48m as 18 minutes. The probe now titles each run
  with the cron that fired.
- **Secret scan on the KEV refresh.** It flagged email-shaped strings in CISA's mailing-list
  archive URLs. The fix is an exact-path exemption for the verbatim file, with its reason, and
  upstream text is never edited.
- **Ambient git identity.** An ambient identity overrode the commit script's `git config`. The
  new test caught it; the script now exports GitHub's bot identity, so it always wins.
- **No PyYAML on the health workflow.** It installs no packages, so the workflow test's YAML
  import would have failed on CI. A stdlib step parser replaces it, and it was cross-checked
  equal to PyYAML on all nine steps.
- **The digest could not report a failed PR step.** The digest was written before the PR step
  ran. The digest step now receives the PR and battery outcomes and appends a note (it names the
  owner setting) inside the slot's own section.
- **The census omitted the build's OSCAL warm-up.** It is now counted
  (`build_requests_measured`, 11) on every building day: Monday 241, Tuesday–Wednesday 17,
  Thursday 76, all inside the caps.
- **Two ATT&CK sources.** The manual `--fetch` recipe still forced ATT&CK through a raw GitHub
  bundle while the Thursday slot reads TAXII. Both now use the loader's TAXII + CTID default.
- **The secret scan flagged the new test's placeholder git address.** It was replaced with a
  noreply-form address.

## Residual risk
- **CTID maps ATT&CK 16.1, not 20.0.** The skew is recorded, and a newer CTID mapping is a human
  decision.
- **252 techniques are blank.** They are honest gaps, not "no control applies"; the
  `attack-mapper` skill flags `human_review_required`.
- **Slot times are provisional until the C8 pin** (2026-11-19 or later). GitHub may drop queued
  scheduled jobs under load, and a dropped run shows as a missing sample.
- **PRs are not proposed until the owner setting is on.** Until the owner enables "Allow GitHub
  Actions to create and approve pull requests", the PR step fails. The digest says so, and the
  refresh branch is still pushed.
- **NVD stays report-only.** Committing it is the user's decision, taken from the digest.
- **EUR-Lex, FIPS, OLIR and CPRT stay unscheduled** until a verified machine source exists.
- **GitHub disables the schedules after 60 days without activity.** The Monday check warns from
  45 days.
- **The 18 `releases.atom` announcement entries** (refused since 0.15.1) are deferred by the
  user.
