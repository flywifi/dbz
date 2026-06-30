---
name: public-web-evidence-crawler
description: gather, classify, and normalize public-web evidence from company sites, trust centers, regulator pages, partner pages, and reputable news into review-ready bundles. use when chatgpt needs fresh external context for account briefs, regulatory monitoring, competitive research, or customer prep and should work well with native web tooling, manual capture, and native web tooling, manual capture, and optional firecrawl-style crawling with credentials or a self-hosted deployment.
---

# Public Web Evidence Crawler

## Mission

Convert web research into a reusable evidence bundle instead of one-off browsing notes. Prefer the highest-quality retrieval path available **without demanding new credentials**.

## Access modes

Read `references/access-modes.md` first.

## Core rules

- Prefer primary sources over media coverage whenever practical.
- Keep source class explicit for every finding.
- Never merge multiple URLs into one uncited conclusion.
- If dates are missing or ambiguous, log that gap instead of guessing.
- Record the selected access mode in `crawl/access-mode.json`.

## Workflow

1. Run `scripts/plan_access_mode.py`.
2. Run `scripts/seed_crawl_plan.py` from explicit URLs and themes.
3. Collect findings using the best available path:
   - runtime-native web tools
   - manual or exported findings normalized locally
   - Firecrawl or self-hosted crawl infrastructure if credentials exist
4. Use `scripts/seed_manual_findings.py` when you need a clean manual finding skeleton.
5. Normalize all findings with `scripts/normalize_findings.py`.
6. Validate with `scripts/validate_crawl_pack.py`.
7. Hand off to `briefing-generator-companion`, `regulatory-monitor`, `regulatory-intelligence-monitor`, `thoropass-positioning-evidence`, or `cs-product-intel`.

## Output contract

- `crawl/access-mode.json`
- `crawl/crawl-plan.json`
- `crawl/finding-log.json`
- `crawl/source-map.json`
- `crawl/external-intelligence-log.json`
- `crawl/crawl-validation.json`
- `summary.md`

## Failure behavior

- If a source is blocked, keep it in the crawl plan and log the block.
- If the user only gave themes, emit a crawl plan and a manual finding skeleton instead of fabricating evidence.
- If a finding comes from a secondary source and the primary source is unavailable, label that limitation clearly.

## Bundled resources

- `scripts/plan_access_mode.py`
- `scripts/seed_crawl_plan.py`
- `scripts/seed_manual_findings.py`
- `scripts/normalize_findings.py`
- `scripts/validate_crawl_pack.py`
- `references/access-modes.md`
- `references/source-classification.md`
- `references/finding-schema.md`
- `references/crawl-heuristics.md`
