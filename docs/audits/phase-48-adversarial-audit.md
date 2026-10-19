# Phase-48 closing adversarial audit — 2026-10-19

**Scope.** One registry write: NIST's Information Technology topic news feed added to 18
`feed_registry.json` feeds beside the Cybersecurity Insights blog chosen in phase 47.
Written to satisfy the regulatory-phase closing gate (`protocol-layer/quality-gates.md`).

**Origin.** The reporting workstation's session read NIST's feed directory
(`nist.gov/coo/nist-rss-feeds`) and found that directory feeds have the form
`/news-events/<topic>/rss.xml`, that the official Cybersecurity topic feed is live but
empty, and that cybersecurity news now lands in the Information Technology topic feed. It
suggested adding that feed; the user chose to add it only where keywords are specific.

## Pass 1 — source integrity
- Cybersecurity topic feed `/news-events/cybersecurity/rss.xml`: 200, 860 bytes, **0 items**
  (this egress and the workstation agree). **Do not use it as a replacement**: it is alive
  and signal-free, and pointing at it would silently restore the pre-phase-47 state.
- IT topic feed `/news-events/information%20technology/rss.xml`: 200, 27,158 bytes, 40
  items (newest 2026-10-08 per the workstation). Insights blog unchanged (200, 40 items).
- The directory reading itself is the workstation's; it is a listing page, not a feed, so
  it was not re-fetched here.

## Pass 2 — claim support
| Claim | Probe | Result |
|---|---|---|
| The IT feed adds real signal | `process_feed_entry` over all 26 Insights-bearing feeds, 180 days, each feed's own keywords | **6 nist-csf hits** (e.g. "Draft PNT Profile Updated to Align with NIST CSF 2.0"), **1 nvd-cve hit**; 0 for every SP/FIPS/IR feed |
| Generic keywords would flood | unfiltered IT feed vs `oscal-format` keywords | 40 items; `release/schema/breaking change` match **10 of 40** (5G papers, NICE framework) |
| The split is rule-based | regex `\d\|CSF\|NVD\|CVE\|RMF\|OLIR\|OSCAL\|CMMC\|FedRAMP\|HIPAA\|PIV\|KEV` over each keyword | 16 specific + 2 measured (nist-csf, nvd-cve) = **18 added**; 8 skipped, `oscal-format` among them |
| Nothing else moved | diff + `feeds_count` | 161 insertions, one file; `feeds_count` 161; roundtrip identical before and after |
| Battery | rebuild, test_spine, validate_spine, scenarios, sync_check 16/16, count_truth 16/16 (0 URL warnings) | all green |

**Verification limit, stated:** the plan's check 3 (`update_check --dry-run` showing ≥6
nist-csf announcements) was badly designed: in dry-run the monitor writes nothing, so the
reader shows the committed announcements file (5), not the fresh fetch. The 6 hits were
measured directly with `process_feed_entry`; the first non-dry monthly run will land them.

## Pass 3 — chain / mutation integrity
Write via `tools/registry_io.py`, roundtrip asserted pre- and post-save. New entries copy
each feed's existing `filter_keywords` verbatim (no new keywords invented) and carry a
`notes` line naming the date, the reason, and the directory source. Duplicate
announcements across the two feeds are impossible by construction (blog vs news items;
`deduplicate()` keys on `entry_id` regardless).

## Pass 4 — adversary output (mandatory)
**Most likely wrong:** *"the IT topic feed is where SP/FIPS announcements land."* In 180
days it produced 0 SP/FIPS hits; the claim rests on the workstation's directory reading and
on the CSF/NVD hits as proxies. It is overturned if the next SP 800-63 or FIPS release
appears in `/news-events/news/rss.xml` (the unfiltered all-news feed, 40 items, newest
2026-10-16) but not in the IT topic feed. The first such release decides it; if it falls the
other way, the all-news feed with the same identifier keywords is the fallback.

## Residual risk
- The 8 generic-keyword feeds stay news-blind. `oscal-format`'s keywords
  (`release/schema/breaking change`) were designed for a release feed and match general
  news; they deserve a redesign of their own (parked, stated).
- 18 more fetches of one URL per monthly run; fetchkit's conditional GET makes repeats
  304s, but a NIST rate-limit change would surface as `check_failed`, not silently.
