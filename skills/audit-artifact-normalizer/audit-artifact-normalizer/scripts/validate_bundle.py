#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

REQUIRED = ['package-manifest.json', 'source-index.json', 'warnings.json', 'duplicate-report.json', 'extraction-plan.json']


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate normalized bundle outputs.')
    parser.add_argument('normalized_dir', help='path to normalized directory')
    args = parser.parse_args()

    normalized = Path(args.normalized_dir).resolve()
    base_dir = normalized.parent
    missing = [name for name in REQUIRED if not (normalized / name).exists()]
    report = {'ok': not missing, 'missing_files': missing, 'checks': []}
    manifest = None
    plan = None
    if not missing:
        manifest = json.loads((normalized / 'package-manifest.json').read_text(encoding='utf-8'))
        source_ids = {item['id'] for item in manifest['files']}
        plan = json.loads((normalized / 'extraction-plan.json').read_text(encoding='utf-8'))
        planned = {item['source_id'] for item in plan['items']}
        report['checks'].append({'name': 'source_coverage', 'ok': source_ids == planned, 'missing_plan_ids': sorted(source_ids - planned), 'extra_plan_ids': sorted(planned - source_ids)})
        duplicate_report = json.loads((normalized / 'duplicate-report.json').read_text(encoding='utf-8'))
        duplicate_sources = {dup for group in duplicate_report['duplicate_groups'] for dup in group['duplicate_sources']}
        report['checks'].append({'name': 'duplicate_sources_known', 'ok': duplicate_sources.issubset(source_ids), 'unknown_duplicate_sources': sorted(duplicate_sources - source_ids)})
        report['ok'] = all(check['ok'] for check in report['checks'])

    out_path = normalized / 'bundle-validation.json'
    out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    summary_lines = [
        '# Audit Artifact Normalizer Summary',
        '',
        f"- validation ok: {report['ok']}",
        f"- missing files: {', '.join(report['missing_files']) if report['missing_files'] else 'none'}",
    ]
    if manifest is not None:
        summary_lines.append(f"- source count: {len(manifest['files'])}")
    if plan is not None:
        summary_lines.append(f"- planned extractions: {len(plan['items'])}")
    for check in report['checks']:
        summary_lines.append(f"- check `{check['name']}`: {check['ok']}")
    summary = '\n'.join(summary_lines) + '\n'
    (normalized / 'summary.md').write_text(summary, encoding='utf-8')
    (base_dir / 'summary.md').write_text(summary, encoding='utf-8')
    print(f'Validation written to {out_path}')
    if not report['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
