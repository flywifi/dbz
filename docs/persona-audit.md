# Persona audit — 2026-07-18

A dated review of actual `dbz_query.py` output from three user perspectives, capturing concrete
output gaps as the backlog feed for future UX work. Method: run the canonical queries each
persona would run, read the output as that person, note what's missing or confusing. This is an
audit document (observations, not commitments); re-run and re-date it after major query-surface
changes.

## Persona 1 — External auditor ("can I rely on this pairing?")

Ran: `master --framework "HIPAA Security" --control 164.312`, `overlap` on SOC2×ISO.

**Works well:** every edge shows tier + provenance + the new `ev=` evidence state inline;
`needs_confirmation` and confidence gating are explicit; corroborating surfaces are counted.

**Gaps observed:**
- Consensus edges display `relationship: unspecified` frequently — an auditor wants to know
  *why* it's unspecified (voters disagreed vs. never stated). The voter breakdown exists in the
  DB but is not shown inline.
- No single flag to emit a citation-ready line ("per NIST OLIR SP 800-66r2, edge X") — the
  auditor assembles citations manually from `source_ref`.
- `164.312` (base) vs `164.312(a)(2)(i)` (cited form) both work, but the output doesn't say
  which granularity matched — worth an explicit `matched_at: base_section` note.

## Persona 2 — CISO ("what's my fastest path to the next framework?")

Ran: `overlap --framework-a "SOC 2" --framework-b "PCI DSS v4.0"`, `master --framework-a
"SOC 2" --scope-fedramp moderate`, with and without `--overlay`.

**Works well:** the three-number summary (Jaccard, A-covers-B, B-covers-A) answers the headline
question fast; caveat lines are honest; overlays give a segment-shaped answer with disclosed
suppression.

**Gaps observed:**
- No effort weighting: 37.8% overlap treats a policy-only control the same as a heavy technical
  control. Even a coarse controls-vs-evidence-requests split would make the % more decision-
  useful.
- The "what do I still need" direction (uncovered PCI requirements, ranked by family) requires
  a second query; a `--gap-list` convenience on `overlap` would close the loop.
- No export-friendly one-pager: CISO consumers want the summary + top-20 shared controls as a
  single artifact (the pieces exist across `overlap` and `master`).

## Persona 3 — Sales engineer ("prove the reuse story in a call")

Ran: `overlap` SOC2×ISO, `fedramp --coverage`, `master --framework-a "SOC 2" --framework-b
"HITRUST CSF" --overlay industry/healthcare`.

**Works well:** instant, deterministic numbers; the overlay emphasizes the frameworks the
prospect cares about; BENCHMARK.md gives a measured-accuracy line to quote.

**Gaps observed:**
- Output is terminal-shaped; there is no `--format brief` that yields 3 talking-point lines
  safe to paste into a deck (and pre-passed through `tools/output_validate.py`).
- Framework display names are canonical-technical ("ISO 27001/2 (2022)") — fine for auditors,
  clunky in sales copy; a display-label column in `framework_labels` would fix it at the source.
- The evidence-state ladder is a strong trust story ("1,467 edges oracle-confirmed by
  production audit data") but no query summarizes the ladder counts in one line
  (`master --state-summary` would).

## Disposition

These are candidate backlog items, deliberately NOT implemented in this pass (audit ≠ scope
creep). Highest-leverage next steps by persona value: (1) `--gap-list` on overlap,
(2) a validated `--format brief`, (3) inline voter breakdown on consensus edges.
