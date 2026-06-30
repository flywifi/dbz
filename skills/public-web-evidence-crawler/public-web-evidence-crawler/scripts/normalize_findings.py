#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

VALID_CLASSES = {
    'public_company_primary', 'public_regulatory_primary', 'public_legal_primary', 'public_government_primary',
    'public_partner_announcement', 'public_news_media', 'public_industry_analysis', 'public_social_company',
    'public_social_individual', 'public_third_party_secondary', 'public_unverified'
}
VALID_CONFIDENCE = {'high', 'medium', 'low'}
VALID_ACTIONABILITY = {'immediate', 'near_term', 'strategic', 'monitor_only'}

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def normalize_item(idx: int, item: dict) -> dict:
    source_class = item.get('source_class', 'public_unverified')
    if source_class not in VALID_CLASSES:
        source_class = 'public_unverified'
    confidence = item.get('confidence_level', 'medium')
    if confidence not in VALID_CONFIDENCE:
        confidence = 'medium'
    actionability = item.get('actionability_level', 'monitor_only')
    if actionability not in VALID_ACTIONABILITY:
        actionability = 'monitor_only'
    return {
        'finding_id': item.get('finding_id', f'finding_{idx:03d}'),
        'source_url': item.get('source_url'),
        'source_title': item.get('source_title', ''),
        'source_class': source_class,
        'publication_date': item.get('publication_date'),
        'observed_at': item.get('observed_at', iso_now()),
        'confidence_level': confidence,
        'actionability_level': actionability,
        'signal_type': item.get('signal_type', 'monitor_only'),
        'extracted_claim': item.get('extracted_claim', '').strip(),
        'notes': item.get('notes', []),
    }

def main() -> None:
    parser = argparse.ArgumentParser(description='Normalize external findings into the crawl contract.')
    parser.add_argument('input_json', help='raw findings json list or object with findings[]')
    parser.add_argument('--out-dir', default='.', help='base output directory')
    args = parser.parse_args()

    crawl_dir = Path(args.out_dir).resolve() / 'crawl'
    crawl_dir.mkdir(parents=True, exist_ok=True)
    raw = json.loads(Path(args.input_json).read_text())
    if isinstance(raw, dict):
        items = raw.get('findings', [])
    else:
        items = raw
    normalized = [normalize_item(idx, item) for idx, item in enumerate(items)]
    payload = {'findings': normalized}
    (crawl_dir / 'finding-log.json').write_text(json.dumps(payload, indent=2))
    (crawl_dir / 'external-intelligence-log.json').write_text(json.dumps({'items': normalized}, indent=2))
    source_map = {'sources': sorted({item['source_url'] for item in normalized if item.get('source_url')})}
    (crawl_dir / 'source-map.json').write_text(json.dumps(source_map, indent=2))
    print(f'Wrote normalized findings to {crawl_dir}')

if __name__ == '__main__':
    main()
