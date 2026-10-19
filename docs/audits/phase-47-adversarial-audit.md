# Phase-47 closing adversarial audit — 2026-10-19

**Scope.** This phase's own diff: the peer-reported skill fixes (the framework-update-check
crashes, the unresolvable atom and file references, the audit-scope gap) and the two
regulatory-currency registry writes they led to. Those are the correction of the phase-46
`framework_changelog.json` entry and the repoint of 22 dead NIST feed entries in
`feed_registry.json`. Written to satisfy the regulatory-phase closing gate
(`protocol-layer/quality-gates.md`).

**How the phase started.** A peer Claude session installing the skills into a read-only
clone on a workstation reported four defects at `3fd3256`. A peer report is a lead, not a
finding, so each was reproduced on a fresh clone of the same sha before any fix: three
confirmed, one not reproduced.

## Pass 1 — source integrity

- **The dead feed.** `https://www.nist.gov/news-events/cybersecurity/rss` returned
  **HTTP 404** to a direct request from this environment and, independently, to WebFetch's
  separate egress (2026-10-19). The replacement
  `https://www.nist.gov/blogs/cybersecurity-insights/rss.xml` returned **200**: valid RSS
  2.0, channel "Cybersecurity Insights", newest item dated 2026-10-14. The replacement is
  not this phase's choice. Three registry entries already named it ("replaces deprecated
  /news-events/cybersecurity/rss"), and this phase removes the dead entries left beside it.
- **The changelog correction.** The 66 added ids come from a measured id-set diff: the
  2026.1.1 workbook, recovered from git at `26720f6`, against the pinned 2026.2 workbook,
  both read through `spine_loader._canon_scf_id` (+66 / −0). The 23 modified ids are the
  union of the committed errata's "Renamed Controls" (10) and "Wordsmithed Controls" (21)
  lists. Eight ids appear in both: CPL-03, END-08.1, NET-06, PRI-03, PRI-04, PRI-06.4,
  PRI-07.4, PRI-21.2.

## Pass 2 — claim support

| Claim | Probe | Result |
|---|---|---|
| update_check crashed on its documented command | ran it on a fresh clone at `3fd3256` | `TypeError: run() got an unexpected keyword argument 'registry_path'`, rc 1 |
| …and two more crashes hid behind it | re-ran after each fix | `'<' not supported between 'NoneType' and 'NoneType'` (57/62 null dates), then `the JSON object must be str… not list` (stale changelog schema) |
| fixed | documented command after all three fixes | rc 0; reader returns real values (scf: `SCF 2026.2 (2026-07-08)`, 66 added, 0 withdrawn) |
| the widened workflow check fires on the real defect | patched `check_workflows` on the real tree before the atom existed | **2 blocking**, exactly the two `source-manifest-lookup` steps; **0** after the atom landed |
| widening the markdown checks too would be noise | ran them over the packaged skills | 46 findings, 44 false positives (runtime output paths) |
| a naive feed repoint floods 15 frameworks | `process_feed_entry` against the live feed, 90-day window | **600** tagged entries unfiltered vs **1** with label-derived keywords (a genuine SP 800-63 post) |
| the repoint loses no monitoring | keyword set comparison on the 7 dropped duplicates | 0 keywords lost in any feed |
| reverse-index "hang" | `build_reverse_index.py` on a freshly generated catalog | completes in 1 s (rc 0) — **not reproduced** |
| full battery | double build, test_spine, validate_spine, benchmark --check, scenarios, alias contract, sync_check 16/16 (23 atoms), count_truth 16/16, golden, instruction audit (26 skills), CI rehearsal | all green |

## Pass 3 — chain / mutation integrity

- Both registry writes went through `tools/registry_io.py`, with `roundtrip_identical`
  asserted before and after. Each was diff-verified as scoped. The changelog diff touches
  exactly one entry (`controls_added`, `controls_removed`, `controls_modified`, `summary`).
  The feed diff touches exactly 22 feeds and only their `announcement_feeds`;
  `feeds_count` stays 161.
- The filter keywords are not invented. They are the identifier in each feed's own label,
  stripped of revision qualifiers by a rule that raises on any label it can't parse.
- The new atom is read-only by construction (no write primitive; sync invariant 14 green)
  and returns an error, never a synthesized entry, for an unknown key or role.

## Pass 4 — adversary output (mandatory)

**The single claim most likely to be wrong:** *"the old NIST feed is dead, not
bot-walled."* The removed entries' own notes said the URL was "verified valid for normal
browser/residential access". The evidence that would overturn it is a 200 from a
residential connection. It would be found on the reporting session's workstation, which is
exactly where the reply to that session asks for the check. What supports the claim: a 404
(not the 403 a bot wall usually returns) from two independent egresses, and the registry's
own earlier "deprecated" annotation. If it is overturned, the repoint is still harmless
(the replacement is live and keyed), but the seven dropped duplicates should return.

**Second candidate:** *"the reverse-index report was environmental, not a code defect."*
That would be overturned by a stall on a complete catalog, so the reporting session has
been asked for its OS, Python version, catalog size and exact command. No code changed on
the strength of a guess.

**Third candidate, now disconfirmed:** my own pause-time claim that the phantom-atom
defect was "wider than reported, six workflow files". The audit's rule also accepts
installed skill names as step targets, and those other names are skills. The reporting
session's scope was exactly right. That claim was made in conversation, never in the repo,
and is corrected here.

## Residual risk (never an all-clear)

- The all-feeds `update_check` run polls ~160 live endpoints and exceeded a 300 s timeout
  here. It is network-bound and not a crash, but it isn't proven end to end; the documented
  single-feed form is.
- The markdown reference checks still skip the packaged skills (by design, measured above),
  so a broken *repo* path cited in a packaged SKILL.md would not be caught.
- The Insights blog is a thinner signal than the dead news feed for SP and FIPS
  publication events. Whether a NIST CSRC publications feed would serve those feeds better
  is unexamined (parked; no URL asserted).
- The reverse-index report remains open until it reproduces or the reporter confirms an
  environmental cause.
