#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_url(url: str) -> str:
    lowered = url.lower()
    if 'linkedin.com' in lowered:
        return 'public_social_company'
    if any(domain in lowered for domain in ['sec.gov', 'ftc.gov', 'ec.europa.eu', '.gov']):
        return 'public_regulatory_primary'
    if 'partner' in lowered:
        return 'public_partner_announcement'
    return 'public_company_primary'


def main() -> None:
    parser = argparse.ArgumentParser(description='Create a crawl plan from URLs and themes.')
    parser.add_argument('--url', action='append', default=[], help='URL to include in the crawl plan')
    parser.add_argument('--theme', action='append', default=[], help='search theme or topic')
    parser.add_argument('--out-dir', default='.', help='base output directory')
    args = parser.parse_args()

    base_dir = Path(args.out_dir).resolve()
    crawl_dir = base_dir / 'crawl'
    crawl_dir.mkdir(parents=True, exist_ok=True)
    targets = []
    for idx, url in enumerate(args.url):
        targets.append({'target_id': f'tgt_{idx:03d}', 'type': 'url', 'value': url, 'source_class': classify_url(url), 'reason': 'explicit_url'})
    theme_offset = len(targets)
    for idx, theme in enumerate(args.theme):
        targets.append({'target_id': f'tgt_{theme_offset + idx:03d}', 'type': 'theme', 'value': theme, 'source_class': 'discovery_needed', 'reason': 'search_theme'})

    payload = {'created_at': iso_now(), 'targets': targets}
    (crawl_dir / 'crawl-plan.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    summary = '\n'.join([
        '# Public Web Evidence Crawler Summary',
        '',
        f'- planned targets: {len(targets)}',
        f'- explicit urls: {len(args.url)}',
        f'- themes: {len(args.theme)}',
        '- note: planning a crawl is not the same as collecting evidence; normalize actual findings before using them as support.',
    ]) + '\n'
    (crawl_dir / 'summary.md').write_text(summary, encoding='utf-8')
    (base_dir / 'summary.md').write_text(summary, encoding='utf-8')
    print(f'Wrote crawl plan to {crawl_dir / "crawl-plan.json"}')


if __name__ == '__main__':
    main()
