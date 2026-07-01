# MAINTAINER — public-web-evidence-crawler

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`public-web-evidence-crawler` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Source class must be explicit for every finding — never merge multiple URLs into one uncited conclusion.
- Primary sources are preferred over media coverage whenever practical.
- Access mode determined by `references/access-modes.md`; prefer highest-quality path without demanding new credentials.
- `human_review_required: true` in every output used for compliance, regulatory, or customer-facing decisions.
- Never fabricates URLs, company statements, or regulatory text not found in the actual crawled content.
- Robot exclusion rules (`robots.txt`) must be respected — do not crawl disallowed paths.

## Known failure modes
- **Hallucinating citations**: generating plausible-looking URLs or policy text that wasn't actually retrieved. Every citation must be traceable to a crawled source.
- **Media-as-primary confusion**: treating a news article about a company's compliance status as equivalent to the company's own trust center or regulatory filing.
- **Scope creep**: being asked to analyze or interpret the crawled content for compliance opinions. This skill crawls and normalizes only — analysis belongs to `compliance-report-analyzer`.
- **Credential assumption**: assuming Firecrawl or similar is available without checking the access mode.
- **Stale evidence**: returning cached or stale evidence without noting the retrieval timestamp. All evidence records must include `retrieved_at`.

## Fragile fallbacks that must not become defaults
- Manual capture (screenshot + user-paste) is a valid access mode — never refuse a task just because automated crawling is unavailable.
- `retrieved_at` timestamps are required on every evidence record; never omit even on cached results.

## Regression cases to preserve
1. Every evidence record includes `source_url`, `source_class`, and `retrieved_at`.
2. No single conclusion cites multiple URLs without listing each URL separately.
3. Returns `human_review_required: true` when evidence is used for compliance or regulatory context.
4. Respects `robots.txt` — does not attempt crawl of disallowed paths.
5. Does not fabricate any URL, policy excerpt, or regulatory text not present in crawled content.

## Approval-gated changes
- Adding new source classes to the evidence vocabulary.
- Adding new Firecrawl-style integration paths.
- Changing how `robots.txt` compliance is enforced.
- Modifying the evidence record schema (source_url, source_class, retrieved_at, content shape).

## Minority-report policy
When two crawled sources disagree on a factual claim (e.g., trust center says "ISO 27001 certified"
but the certificate registry shows no active certification), emit `minority_report.conflicts` with
both sources before returning the evidence bundle. See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Confirm `references/access-modes.md` access-mode hierarchy is current.
- [ ] Verify `retrieved_at` is populated on all evidence record paths.
- [ ] Test robots.txt compliance with a known-disallowed path.
- [ ] Confirm no fabricated citations in smoke-test output.
- [ ] Confirm `human_review_required: true` present in compliance/regulatory output paths.
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
