#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

TEMPLATE = """# Resource Model

## Principal
- name:
- scope:

## Resource
- type:
- id pattern:

## Actions
- list
- read
- write
- administer
"""


def main() -> None:
    parser = argparse.ArgumentParser(description='Write a resource model template and example policies.')
    parser.add_argument('--out-dir', default='.')
    parser.add_argument('--matrix-json', default=None)
    args = parser.parse_args()
    base_dir = Path(args.out_dir).resolve()
    out_dir = base_dir / 'security'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'resource-model.md').write_text(TEMPLATE, encoding='utf-8')
    rows = []
    if args.matrix_json:
        rows = json.loads(Path(args.matrix_json).read_text(encoding='utf-8')).get('rows', [])
    policy_items = []
    for row in rows:
        policy_items.append({
            'principal': row.get('principal') or row.get('role') or 'operator',
            'resource_type': row.get('resource_type') or row.get('resource') or 'account',
            'scope': row.get('scope') or 'scoped',
            'effect': row.get('effect') or 'allow',
            'actions': [action.strip() for action in (row.get('actions') or row.get('action') or 'read').split('|') if action.strip()],
        })
    (out_dir / 'example-policies.json').write_text(json.dumps({'policies': policy_items}, indent=2), encoding='utf-8')
    print(f'Wrote resource templates to {out_dir}')


if __name__ == '__main__':
    main()
