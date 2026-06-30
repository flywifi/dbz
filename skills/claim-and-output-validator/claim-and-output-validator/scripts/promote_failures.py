#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(description='Convert validation failures into a reusable regression case skeleton.')
    parser.add_argument('report_json', help='path to validation/report.json')
    parser.add_argument('--out', default='promoted-regression-case.json', help='output path')
    args = parser.parse_args()

    report = json.loads(Path(args.report_json).read_text())
    case = {
        'id': 'promoted-from-validation',
        'description': 'Regression case generated from validation failures.',
        'input': {'source_report': str(Path(args.report_json).resolve())},
        'expected': {'status': 'safe'},
        'blocked_patterns': [item['pattern'] for item in report.get('blocked', [])],
        'warning_patterns': [item['pattern'] for item in report.get('warnings', [])],
    }
    Path(args.out).write_text(json.dumps(case, indent=2))
    print(f'Wrote {args.out}')

if __name__ == '__main__':
    main()
