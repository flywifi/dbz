#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(description='Validate that required keys exist in a JSON object.')
    parser.add_argument('json_file')
    parser.add_argument('schema_file', help='JSON file with required_keys list')
    args = parser.parse_args()

    payload = json.loads(Path(args.json_file).read_text())
    schema = json.loads(Path(args.schema_file).read_text())
    required = schema.get('required_keys', [])
    missing = [key for key in required if key not in payload]
    report = {'ok': not missing, 'required_keys': required, 'missing_keys': missing}
    out_path = Path(args.json_file).with_name('json-key-validation.json')
    out_path.write_text(json.dumps(report, indent=2))
    print(f'Wrote {out_path}')
    if missing:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
