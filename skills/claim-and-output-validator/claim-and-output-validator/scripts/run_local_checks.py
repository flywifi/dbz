#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

BLOCKED_PATTERNS = {
    'unsupported_superiority': ['best in class', 'better than everyone', 'most rigorous'],
    'implied_guarantee': ['guarantee', 'ensures compliance', 'fully compliant'],
    'blurred_audit_judgment': ['automates audit judgment', 'decides materiality', 'replaces the auditor'],
}
WARNING_PATTERNS = {
    'missing_proof_boundary': ['trusted', 'rigorous', 'fast', 'secure'],
}


def check_text(text: str) -> dict:
    lowered = text.lower()
    blocked = []
    warnings = []
    for code, patterns in BLOCKED_PATTERNS.items():
        for pattern in patterns:
            if pattern in lowered:
                blocked.append({'code': code, 'pattern': pattern})
    for code, patterns in WARNING_PATTERNS.items():
        for pattern in patterns:
            if pattern in lowered:
                warnings.append({'code': code, 'pattern': pattern})
    unresolved_placeholders = re.findall(r'\{\{[^}]+\}\}', text)
    if unresolved_placeholders:
        warnings.append({'code': 'unresolved_placeholders', 'pattern': ', '.join(sorted(set(unresolved_placeholders)))})
    status = 'blocked' if blocked else 'narrow_before_use' if warnings else 'safe'
    return {'status': status, 'blocked': blocked, 'warnings': warnings}


def main() -> None:
    parser = argparse.ArgumentParser(description='Run deterministic claim validation checks on text.')
    parser.add_argument('input_file', help='path to text or markdown file')
    parser.add_argument('--out-dir', default='.', help='base output directory')
    args = parser.parse_args()

    text = Path(args.input_file).read_text(encoding='utf-8')
    base_dir = Path(args.out_dir).resolve()
    out_dir = base_dir / 'validation'
    out_dir.mkdir(parents=True, exist_ok=True)
    result = check_text(text)
    result['input_file'] = str(Path(args.input_file).resolve())
    (out_dir / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (out_dir / 'blocked-claims.json').write_text(json.dumps({'blocked': result['blocked']}, indent=2), encoding='utf-8')
    rewrite = ['# Suggested rewrite notes', '', f"Status: {result['status']}"]
    if result['blocked']:
        rewrite.append('Replace or remove blocked phrases before reuse.')
    elif result['warnings']:
        rewrite.append('Narrow wording and add proof boundaries where needed.')
    else:
        rewrite.append('No deterministic issues detected.')
    body = '\n'.join(rewrite) + '\n'
    (out_dir / 'rewrite.md').write_text(body, encoding='utf-8')
    (out_dir / 'validation-summary.md').write_text(body, encoding='utf-8')
    (base_dir / 'summary.md').write_text(body, encoding='utf-8')
    print(f'Validation output written to {out_dir}')
    if result['status'] == 'blocked':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
