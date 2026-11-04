# Phase-49 closing adversarial audit — 2026-11-04

**Scope.** One `feed_registry.json` write (new feed `nist-ncp`; three dead NIST links
repaired; a currency note on `disa-stig-library`), the `doc_claims.json` coverage extension
for `horizon_count`, and two stale doc restatements. Written to satisfy the
regulatory-phase closing gate (`protocol-layer/quality-gates.md`).

**Origin.** The user asked for a recursive crawl of NIST's feed directory and of NCP checklist
953, adding appropriate pages and feeds to the seed sources. The full crawl record is in
`docs/source-inventory.md` (Phase 49 section).

## Pass 1 — source integrity
- NIST feed directory (`www.nist.gov/coo/nist-rss-feeds`, page updated 2026-07-01): 30
  feeds, all `/rss.xml`. The bare `/rss` forms the registry still used for three feeds
  return **404**; the `/rss.xml` forms return 200 (news 40 items, events 24).
- NCP data feeds: `checklist-0.1-feed.meta` and `-modified.meta` return 200 `text/plain`
  with `lastModifiedDate` and SHA-256. The downloaded full feed (6,797,835 bytes uncompressed)
  **matched the published SHA-256**, so the measurements below ran on authentic data.
- The NCP HTML pages are a JavaScript app (2,250-byte shell). Their `Last-Modified`
  (2026-09-16) is the app build date. Polling them would have been a vacuous "current" echo,
  the phase-45 defect class, so the registry polls the `.meta` file instead. The monitor's own
  check returned `Wed, 04 Nov 2026 05:15:14 GMT` for the entry as written.

## Pass 2 — claim support
| Claim | Probe | Result |
|---|---|---|
| The two registered NIST feeds already carry the GRC signal | identifier/topic regex over each directory feed, 180 days, items deduplicated by URL | Insights 32 and IT 24 relevant items; the other 11 feeds add 11, 6 of them event listings |
| All-news adds nothing material | per-entry keywords of the 18 IT-keyed feeds against all-news, minus IT-feed URLs | 1 item (a CSF small-business guide) |
| Unfiltered events entries would flood | events feed with and without label-derived keywords | 24 tagged unfiltered vs 0 keyed |
| NCP coverage | parsed the feed | 918 entries; DISA 447, CIS 322, CISA 18, NIST mSCP 14 |
| STIG catalog is behind | exact token-set title match, NCP DISA FINAL vs `stig_catalog.json` | 96 matched (3 ambiguous excluded): **50 newer in NCP**, 44 same, 2 older |
| Counts restated | `count_truth --check` | feeds 161→162 in both cited docs; green |

## Pass 3 — chain / mutation integrity
- Registry write via `tools/registry_io.py`, roundtrip asserted pre- and post-save. Diff
  scope: one new feed, three `announcement_feeds` entries repointed, one `notes` append.
- Keywords added to the two events entries come from the phase-47 label rule, verbatim; no
  keyword was invented.
- The NCP point-of-contact email address was deliberately left out of the notes
  (publication hygiene).
- **Correction of record (gate gap):** README line 78 and the architecture diagram both still
  said "76" horizon records, two phases after the registry reached 77. `count_truth` passed
  because a claim only requires the value to appear *somewhere* in a cited file (README line
  32 said 77), and the diagram wasn't cited at all. My phase-45 edit fixed only the
  plain-text occurrence and missed the bold-markup one. Both are fixed now, and the diagram is
  registered on `horizon_count`. That was proven red on the stale value before the fix and
  green after. A stale *second* occurrence inside a cited file is still not caught; that
  limit stands, recorded on the claim.

## Pass 4 — adversary output (mandatory)
**Most likely wrong:** *"50 of 96 STIGs are newer in NCP than in our catalog."* Title matching
is the weak link: a wrong pairing could compare two different benchmarks. That is mitigated
by exact token-set equality (no fuzzy scores) and by excluding ambiguous matches, and the one
pair checked by hand agrees (Office 365 ProPlus, V3R8 vs V3R5). It would be overturned by a
re-harvest (`stig_harvest.py --refresh-stale`) that leaves most of those 50 unchanged. That
harvest is owed regardless, and it decides the question.

## Residual risk
- NCP's `.meta` changes about every two hours, so `poll_landing` will flag `nist-ncp` as
  changed on nearly every monthly run. That is true but coarse: no NCP loader exists yet
  (`metadata_only`), so per-checklist deltas need the `-modified` feed and a loader.
- The STIG layer stays stale until the refresh-stale harvest runs, and that harvest depends
  on trackr or DISA zip access.
- The three repaired links had 0 keyed hits in the window. They are alive now, but their
  value is unproven until the next matching publication.
