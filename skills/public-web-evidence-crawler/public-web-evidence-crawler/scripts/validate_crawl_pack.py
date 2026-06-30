#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

REQUIRED = ['crawl-plan.json', 'finding-log.json', 'source-map.json', 'external-intelligence-log.json']


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate crawl bundle outputs.')
    parser.add_argument('crawl_dir', help='path to crawl directory')
    args = parser.parse_args()
    crawl_dir = Path(args.crawl_dir).resolve()
    base_dir = crawl_dir.parent
    missing = [name for name in REQUIRED if not (crawl_dir / name).exists()]
    report = {'ok': not missing, 'missing_files': missing, 'checks': []}
    findings = []
    if not missing:
        findings = json.loads((crawl_dir / 'finding-log.json').read_text(encoding='utf-8'))['findings']
        bad = []
        for item in findings:
            for field in ['finding_id', 'source_url', 'source_class', 'confidence_level', 'actionability_level', 'extracted_claim']:
                if not item.get(field):
                    bad.append({'finding_id': item.get('finding_id'), 'missing_field': field})
        report['checks'].append({'name': 'required_fields', 'ok': not bad, 'violations': bad})
        report['ok'] = all(check['ok'] for check in report['checks'])
    out_path = crawl_dir / 'crawl-validation.json'
    out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    summary = '\n'.join([
        '# Public Web Evidence Crawler Summary',
        '',
        f'- validation ok: {report["ok"]}',
        f'- missing files: {", ".join(report["missing_files"]) if report["missing_files"] else "none"}',
        f'- normalized findings: {len(findings)}',
        '- note: without runtime-native browsing or crawler credentials, this skill remains a planning and normalization layer, not a live crawling service.',
    ]) + '\n'
    (crawl_dir / 'summary.md').write_text(summary, encoding='utf-8')
    (base_dir / 'summary.md').write_text(summary, encoding='utf-8')
    print(f'Validation written to {out_path}')
    if not report['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
