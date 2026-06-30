#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description='Validate partition outputs.')
    parser.add_argument('partition_dir', help='path to partition directory')
    args = parser.parse_args()

    partition_dir = Path(args.partition_dir).resolve()
    base_dir = partition_dir.parent
    elements = [json.loads(line) for line in (partition_dir / 'elements.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    chunks = json.loads((partition_dir / 'chunk-index.json').read_text(encoding='utf-8'))['chunks']
    element_ids = {element['element_id'] for element in elements}
    bad_refs = []
    empty_chunks = []
    for chunk in chunks:
        if not chunk['element_ids']:
            empty_chunks.append(chunk['chunk_id'])
        for element_id in chunk['element_ids']:
            if element_id not in element_ids:
                bad_refs.append({'chunk_id': chunk['chunk_id'], 'element_id': element_id})
    report = {'ok': not bad_refs and not empty_chunks, 'bad_refs': bad_refs, 'empty_chunks': empty_chunks, 'element_count': len(elements), 'chunk_count': len(chunks)}
    out_path = partition_dir / 'partition-validation.json'
    out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    summary = '\n'.join([
        '# Bulk Evidence Partitioner Summary',
        '',
        f"- validation ok: {report['ok']}",
        f"- element count: {report['element_count']}",
        f"- chunk count: {report['chunk_count']}",
        f"- empty chunks: {len(empty_chunks)}",
        f"- bad references: {len(bad_refs)}",
    ]) + '\n'
    (partition_dir / 'summary.md').write_text(summary, encoding='utf-8')
    (base_dir / 'summary.md').write_text(summary, encoding='utf-8')
    print(f'Validation written to {out_path}')
    if not report['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
