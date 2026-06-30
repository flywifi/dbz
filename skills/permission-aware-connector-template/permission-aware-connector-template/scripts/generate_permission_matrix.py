#!/usr/bin/env python3
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate a permission matrix from a CSV.')
    parser.add_argument('csv_file')
    parser.add_argument('--out-dir', default='.')
    args = parser.parse_args()
    base_dir = Path(args.out_dir).resolve()
    out_dir = base_dir / 'security'
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with Path(args.csv_file).open(encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    (out_dir / 'permission-matrix.json').write_text(json.dumps({'rows': rows}, indent=2), encoding='utf-8')
    summary = '\n'.join([
        '# Permission Aware Connector Summary',
        '',
        f'- permission rows: {len(rows)}',
        f'- source csv: `{args.csv_file}`',
    ]) + '\n'
    (out_dir / 'summary.md').write_text(summary, encoding='utf-8')
    (base_dir / 'summary.md').write_text(summary, encoding='utf-8')
    print(f'Wrote {out_dir / "permission-matrix.json"}')


if __name__ == '__main__':
    main()
