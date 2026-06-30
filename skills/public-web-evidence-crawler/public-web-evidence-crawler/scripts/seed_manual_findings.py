#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description='Create a manual findings skeleton from a crawl plan.')
    parser.add_argument('crawl_plan_json')
    parser.add_argument('--out-dir', default='.')
    args = parser.parse_args()
    crawl_dir = Path(args.out_dir).resolve() / 'crawl'
    crawl_dir.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(args.crawl_plan_json).read_text())
    findings = []
    for target in plan.get('targets', []):
        findings.append({
            'finding_id': f"manual_{target['target_id']}",
            'source_url': target['value'] if target.get('type') == 'url' else None,
            'source_title': '',
            'source_class': target.get('source_class', 'public_unverified'),
            'publication_date': None,
            'observed_at': None,
            'confidence_level': 'medium',
            'actionability_level': 'monitor_only',
            'signal_type': 'monitor_only',
            'extracted_claim': '',
            'notes': [f"populate manually for target {target['target_id']}"]
        })
    out_path = crawl_dir / 'manual-findings-template.json'
    out_path.write_text(json.dumps({'findings': findings}, indent=2))
    print(f'Wrote {out_path}')


if __name__ == '__main__':
    main()
