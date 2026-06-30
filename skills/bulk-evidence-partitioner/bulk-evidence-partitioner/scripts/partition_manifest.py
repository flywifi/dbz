#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

TEXT_EXTS = {'.txt', '.md', '.markdown', '.json', '.yaml', '.yml', '.csv', '.tsv', '.vtt', '.srt'}


def load_sources(input_path: Path) -> list[dict]:
    if input_path.name == 'package-manifest.json':
        data = json.loads(input_path.read_text())
        return data['files']
    files = [input_path] if input_path.is_file() else [p for p in input_path.rglob('*') if p.is_file()]
    out = []
    for idx, path in enumerate(sorted(files)):
        out.append({'id': f'src_{idx:04d}', 'absolute_path': str(path), 'relative_path': str(path.relative_to(input_path)) if input_path.is_dir() else path.name, 'classification': 'text' if path.suffix.lower() in TEXT_EXTS else 'unknown'})
    return out


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return path.read_text(encoding='utf-8', errors='replace')


def split_lines(text: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines()]
    items = []
    for line in lines:
        if not line:
            continue
        if line.startswith('#'):
            items.append(('heading', line.lstrip('# ').strip()))
        elif line.startswith(('-', '*', '•')):
            items.append(('bullet', line.lstrip('-*• ').strip()))
        elif ',' in line and len(line.split(',')) > 2:
            items.append(('row', line))
        else:
            items.append(('paragraph', line))
    return items


def account_hints(text: str) -> list[str]:
    tokens = re.findall(r'[A-Z][A-Za-z0-9&._-]{2,}', text)
    return sorted(set(tokens))[:5]


def main() -> None:
    parser = argparse.ArgumentParser(description='Create typed elements from a corpus manifest or directory.')
    parser.add_argument('input_path', help='package-manifest.json, file, or directory')
    parser.add_argument('--out-dir', default='.', help='base directory for partition outputs')
    args = parser.parse_args()

    input_path = Path(args.input_path).resolve()
    out_dir = Path(args.out_dir).resolve() / 'partition'
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = load_sources(input_path)

    elements = []
    for source in sources:
        path = Path(source['absolute_path'])
        if source.get('classification') == 'unknown' or path.suffix.lower() not in TEXT_EXTS:
            elements.append({'element_id': f"{source['id']}_e000", 'source_id': source['id'], 'kind': 'placeholder', 'text': '', 'start_marker': 0, 'end_marker': 0, 'metadata': {'reason': 'binary_or_non_text_source', 'relative_path': source['relative_path']}})
            continue
        text = read_text(path)
        items = split_lines(text)
        if not items:
            elements.append({'element_id': f"{source['id']}_e000", 'source_id': source['id'], 'kind': 'empty', 'text': '', 'start_marker': 0, 'end_marker': 0, 'metadata': {'relative_path': source['relative_path']}})
            continue
        for idx, (kind, value) in enumerate(items):
            elements.append({
                'element_id': f"{source['id']}_e{idx:03d}",
                'source_id': source['id'],
                'kind': kind,
                'text': value,
                'start_marker': idx,
                'end_marker': idx,
                'metadata': {
                    'relative_path': source['relative_path'],
                    'account_hints': account_hints(value),
                },
            })

    with (out_dir / 'elements.jsonl').open('w', encoding='utf-8') as fh:
        for element in elements:
            fh.write(json.dumps(element) + '\n')
    (out_dir / 'source-summary.json').write_text(json.dumps({'source_count': len(sources), 'element_count': len(elements), 'sources': sources}, indent=2))
    print(f'Wrote {len(elements)} elements to {out_dir / "elements.jsonl"}')


if __name__ == '__main__':
    main()
