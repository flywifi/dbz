#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate that each permission row has a scope and effect.')
    parser.add_argument('matrix_json')
    args = parser.parse_args()
    matrix_path = Path(args.matrix_json)
    security_dir = matrix_path.parent
    base_dir = security_dir.parent
    rows = json.loads(matrix_path.read_text(encoding='utf-8'))['rows']
    violations = [row for row in rows if not row.get('scope') or not row.get('effect')]
    report = {'ok': not violations, 'violations': violations, 'row_count': len(rows)}
    out_path = security_dir / 'validation-report.json'
    out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    summary = '\n'.join([
        '# Permission Aware Connector Summary',
        '',
        f'- validation ok: {report["ok"]}',
        f'- row count: {report["row_count"]}',
        f'- violations: {len(violations)}',
    ]) + '\n'
    (security_dir / 'summary.md').write_text(summary, encoding='utf-8')
    (base_dir / 'summary.md').write_text(summary, encoding='utf-8')
    print(f'Wrote {out_path}')
    if violations:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
