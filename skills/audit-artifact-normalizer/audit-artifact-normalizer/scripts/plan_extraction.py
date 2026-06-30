#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path

ROUTES = {
    'pdf': ('layout_aware_pdf', 'document-intelligence'),
    'office': ('native_office', 'document-intelligence'),
    'tabular': ('native_tabular', 'document-intelligence'),
    'image': ('image_or_multimodal_fallback', 'document-intelligence'),
    'transcript_adjacent': ('transcript_adjacent', 'briefing-generator-companion'),
    'text': ('direct_text', 'document-intelligence'),
    'archive': ('expand_archive', 'audit-artifact-normalizer'),
    'unknown': ('manual_review', None),
}


def scan_risk(item: dict) -> str:
    if item.get('is_image_heavy'):
        return 'high'
    if item.get('classification') in {'pdf', 'office'}:
        return 'medium'
    return 'low'


def notes_for(item: dict) -> list[str]:
    notes: list[str] = []
    if item.get('duplicate_of'):
        notes.append(f"duplicate_of:{item['duplicate_of']}")
    if item.get('framework_hints'):
        notes.append('framework_hints=' + ','.join(item['framework_hints']))
    if item.get('account_hints'):
        notes.append('account_hints=' + ','.join(item['account_hints'][:3]))
    if item.get('sensitivity_hint') != 'unknown':
        notes.append(f"sensitivity={item['sensitivity_hint']}")
    return notes


def main() -> None:
    parser = argparse.ArgumentParser(description='Create an extraction plan from a normalized package manifest.')
    parser.add_argument('manifest', help='path to normalized/package-manifest.json')
    parser.add_argument('--out', default=None, help='explicit output path for extraction plan')
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    normalized_dir = manifest_path.parent
    base_dir = normalized_dir.parent
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    items = []
    for item in data['files']:
        route, downstream = ROUTES.get(item['classification'], ROUTES['unknown'])
        if item.get('framework_hints') and downstream == 'document-intelligence':
            downstream = 'compliance-report-analyzer'
        items.append({
            'source_id': item['id'],
            'relative_path': item['relative_path'],
            'classification': item['classification'],
            'recommended_route': route,
            'scan_or_layout_risk': scan_risk(item),
            'recommended_downstream_skill': downstream,
            'notes': notes_for(item),
        })

    out_path = Path(args.out).resolve() if args.out else normalized_dir / 'extraction-plan.json'
    out_path.write_text(json.dumps({'items': items}, indent=2), encoding='utf-8')
    route_counts = Counter(item['recommended_route'] for item in items)
    summary = [
        '# Audit Artifact Normalizer Summary',
        '',
        f"- files inventoried: {len(items)}",
        f"- route types: {dict(route_counts)}",
        '',
        '## downstream skill suggestions',
    ]
    for downstream, count in Counter(item.get('recommended_downstream_skill') or 'manual_review' for item in items).items():
        summary.append(f"- {downstream}: {count}")
    summary_text = '\n'.join(summary) + '\n'
    (normalized_dir / 'summary.md').write_text(summary_text, encoding='utf-8')
    (base_dir / 'summary.md').write_text(summary_text, encoding='utf-8')
    print(f'Wrote extraction plan to {out_path}')


if __name__ == '__main__':
    main()
