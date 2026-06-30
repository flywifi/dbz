#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from pathlib import Path


def purpose_tags(kind: str, text: str) -> list[str]:
    lowered = text.lower()
    tags = []
    if any(word in lowered for word in ['risk', 'issue', 'blocker', 'exception']):
        tags.append('risk_or_blocker')
    if any(word in lowered for word in ['action', 'next step', 'follow up', 'todo']):
        tags.append('follow_up_action')
    if any(word in lowered for word in ['soc', 'iso', 'hipaa', 'audit', 'control']):
        tags.append('compliance_evidence')
    if kind == 'heading':
        tags.append('section_anchor')
    return tags or ['general_context']


def main() -> None:
    parser = argparse.ArgumentParser(description='Build retrieval-safe chunks from elements.jsonl')
    parser.add_argument('elements', help='path to elements.jsonl')
    parser.add_argument('--out-dir', default='.', help='base directory for partition outputs')
    parser.add_argument('--chunk-size', type=int, default=3, help='max element count per chunk')
    args = parser.parse_args()

    elements_path = Path(args.elements).resolve()
    out_dir = Path(args.out_dir).resolve() / 'partition'
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [json.loads(line) for line in elements_path.read_text().splitlines() if line.strip()]
    chunks = []
    retrieval_hints = {'high_signal_chunk_ids': [], 'chunk_count': 0}
    by_source = {}
    for element in lines:
        by_source.setdefault(element['source_id'], []).append(element)

    chunk_counter = 0
    for source_id, items in by_source.items():
        buffer = []
        for element in items:
            if element['kind'] == 'heading' and buffer:
                items_to_write = buffer
                chunk_text = '\n'.join(x['text'] for x in items_to_write if x['text'])
                chunk = {
                    'chunk_id': f'chk_{chunk_counter:04d}',
                    'source_ids': [source_id],
                    'element_ids': [x['element_id'] for x in items_to_write],
                    'text': chunk_text,
                    'purpose_tags': sorted({tag for x in items_to_write for tag in purpose_tags(x['kind'], x['text'])}),
                    'account_hints': sorted({hint for x in items_to_write for hint in x['metadata'].get('account_hints', [])}),
                    'date_hints': [],
                    'confidence_notes': [],
                }
                chunks.append(chunk)
                if 'risk_or_blocker' in chunk['purpose_tags'] or 'follow_up_action' in chunk['purpose_tags']:
                    retrieval_hints['high_signal_chunk_ids'].append(chunk['chunk_id'])
                chunk_counter += 1
                buffer = []
            buffer.append(element)
            if len(buffer) >= args.chunk_size:
                chunk_text = '\n'.join(x['text'] for x in buffer if x['text'])
                chunk = {
                    'chunk_id': f'chk_{chunk_counter:04d}',
                    'source_ids': [source_id],
                    'element_ids': [x['element_id'] for x in buffer],
                    'text': chunk_text,
                    'purpose_tags': sorted({tag for x in buffer for tag in purpose_tags(x['kind'], x['text'])}),
                    'account_hints': sorted({hint for x in buffer for hint in x['metadata'].get('account_hints', [])}),
                    'date_hints': [],
                    'confidence_notes': [],
                }
                chunks.append(chunk)
                if 'risk_or_blocker' in chunk['purpose_tags'] or 'follow_up_action' in chunk['purpose_tags']:
                    retrieval_hints['high_signal_chunk_ids'].append(chunk['chunk_id'])
                chunk_counter += 1
                buffer = []
        if buffer:
            chunk_text = '\n'.join(x['text'] for x in buffer if x['text'])
            chunk = {
                'chunk_id': f'chk_{chunk_counter:04d}',
                'source_ids': [source_id],
                'element_ids': [x['element_id'] for x in buffer],
                'text': chunk_text,
                'purpose_tags': sorted({tag for x in buffer for tag in purpose_tags(x['kind'], x['text'])}),
                'account_hints': sorted({hint for x in buffer for hint in x['metadata'].get('account_hints', [])}),
                'date_hints': [],
                'confidence_notes': [],
            }
            chunks.append(chunk)
            if 'risk_or_blocker' in chunk['purpose_tags'] or 'follow_up_action' in chunk['purpose_tags']:
                retrieval_hints['high_signal_chunk_ids'].append(chunk['chunk_id'])
            chunk_counter += 1

    retrieval_hints['chunk_count'] = len(chunks)
    (out_dir / 'chunk-index.json').write_text(json.dumps({'chunks': chunks}, indent=2))
    (out_dir / 'retrieval-hints.json').write_text(json.dumps(retrieval_hints, indent=2))
    print(f'Wrote {len(chunks)} chunks to {out_dir / "chunk-index.json"}')


if __name__ == '__main__':
    main()
