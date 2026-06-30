#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import mimetypes
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ARCHIVES = {'.zip'}
TEXTISH = {'.txt', '.md', '.markdown', '.json', '.yaml', '.yml', '.csv', '.tsv', '.vtt', '.srt'}
OFFICE = {'.docx', '.pptx', '.xlsx'}
IMAGES = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp'}

def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def classify(path: Path) -> tuple[str, bool]:
    ext = path.suffix.lower()
    if ext == '.pdf':
        return 'pdf', True
    if ext in OFFICE:
        return 'office', False
    if ext in {'.csv', '.tsv'}:
        return 'tabular', False
    if ext in IMAGES:
        return 'image', True
    if ext in TEXTISH:
        if ext in {'.vtt', '.srt'}:
            return 'transcript_adjacent', False
        return 'text', False
    if ext in ARCHIVES:
        return 'archive', False
    return 'unknown', False

def hint_accounts(name: str) -> list[str]:
    tokens = re.findall(r'[A-Za-z0-9][A-Za-z0-9._-]{2,}', name)
    return sorted({t for t in tokens if t.lower() not in {'final', 'draft', 'copy', 'report', 'notes', 'policy', 'evidence', 'screen', 'screenshot'}})[:5]

def hint_frameworks(name: str) -> list[str]:
    lowered = name.lower()
    hints = []
    for key in ['soc 2', 'soc2', 'soc 1', 'soc1', 'iso 27001', 'iso27001', 'iso 27002', 'iso27002', 'hipaa']:
        if key in lowered:
            hints.append(key.replace(' ', '-'))
    return sorted(set(hints))

def sensitivity_hint(name: str) -> str:
    lowered = name.lower()
    if any(x in lowered for x in ['internal', 'private', 'notes', 'draft']):
        return 'likely_internal'
    if any(x in lowered for x in ['customer', 'client', 'external', 'shared']):
        return 'likely_customer_facing'
    return 'unknown'

def expand_archives(files: list[Path], scratch: Path) -> tuple[list[Path], list[dict]]:
    expanded = list(files)
    expansions = []
    for path in list(files):
        if path.suffix.lower() != '.zip':
            continue
        target = scratch / f"expanded_{path.stem}"
        target.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(target)
            members = [p for p in target.rglob('*') if p.is_file()]
            expanded.extend(members)
            expansions.append({
                'archive_path': str(path),
                'expanded_to': str(target),
                'member_count': len(members),
            })
        except zipfile.BadZipFile:
            expansions.append({
                'archive_path': str(path),
                'expanded_to': None,
                'member_count': 0,
                'error': 'bad_zip_file',
            })
    return expanded, expansions

def main() -> None:
    parser = argparse.ArgumentParser(description='Create a normalized bundle manifest for a file or directory.')
    parser.add_argument('input_path', help='file or directory to inventory')
    parser.add_argument('--out-dir', default='.', help='output directory for normalized bundle files')
    args = parser.parse_args()

    root = Path(args.input_path).resolve()
    out_dir = Path(args.out_dir).resolve()
    norm = out_dir / 'normalized'
    scratch = norm / '_scratch'
    norm.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)

    files = [root] if root.is_file() else [p for p in root.rglob('*') if p.is_file()]
    files, expansions = expand_archives(files, scratch)

    manifest = []
    by_hash: dict[str, list[str]] = defaultdict(list)
    for idx, path in enumerate(sorted(set(files))):
        rel = path.name if root.is_file() else str(path.relative_to(root)) if root in path.parents or path == root else str(path)
        classification, image_heavy = classify(path)
        digest = sha256(path)
        source_id = f'src_{idx:04d}'
        item = {
            'id': source_id,
            'relative_path': rel,
            'absolute_path': str(path),
            'filename': path.name,
            'extension': path.suffix.lower(),
            'size_bytes': path.stat().st_size,
            'mime_type': mimetypes.guess_type(path.name)[0],
            'sha256': digest,
            'classification': classification,
            'is_archive': path.suffix.lower() in ARCHIVES,
            'is_image_heavy': image_heavy,
            'sensitivity_hint': sensitivity_hint(path.name),
            'account_hints': hint_accounts(path.stem),
            'framework_hints': hint_frameworks(path.name),
            'duplicate_of': None,
            'warnings': [],
        }
        manifest.append(item)
        by_hash[digest].append(source_id)

    duplicates = []
    source_map = {item['id']: item for item in manifest}
    for digest, ids in by_hash.items():
        if len(ids) <= 1:
            continue
        canonical = ids[0]
        for dup_id in ids[1:]:
            source_map[dup_id]['duplicate_of'] = canonical
            source_map[dup_id]['warnings'].append('duplicate_hash')
        duplicates.append({'sha256': digest, 'canonical_source': canonical, 'duplicate_sources': ids[1:]})

    warnings = []
    for item in manifest:
        if item['classification'] == 'unknown':
            warnings.append({'source_id': item['id'], 'severity': 'warning', 'code': 'unknown_type', 'message': 'Unrecognized extension; manual review may be required.', 'suggested_fallback': 'manual_review'})
        if item['is_image_heavy']:
            warnings.append({'source_id': item['id'], 'severity': 'info', 'code': 'layout_sensitive', 'message': 'Layout-aware or multimodal parsing is likely safer for this file.', 'suggested_fallback': 'layout_or_multimodal'})
        if item['duplicate_of']:
            warnings.append({'source_id': item['id'], 'severity': 'info', 'code': 'duplicate_hash', 'message': f"Content duplicates source {item['duplicate_of']}", 'suggested_fallback': 'preserve_one_canonical_source'})

    manifest_payload = {
        'bundle_version': '1.0',
        'input_root': str(root),
        'created_at': iso_now(),
        'source_count': len(manifest),
        'archive_expansions': expansions,
        'files': manifest,
    }
    source_index = {
        'source_count': len(manifest),
        'classifications': dict(Counter(item['classification'] for item in manifest)),
        'sources': [{k: v for k, v in item.items() if k not in {'absolute_path'}} for item in manifest],
    }
    duplicate_report = {
        'canonical_sources': [group['canonical_source'] for group in duplicates],
        'duplicate_groups': duplicates,
    }

    (norm / 'package-manifest.json').write_text(json.dumps(manifest_payload, indent=2))
    (norm / 'source-index.json').write_text(json.dumps(source_index, indent=2))
    (norm / 'warnings.json').write_text(json.dumps({'warnings': warnings}, indent=2))
    (norm / 'duplicate-report.json').write_text(json.dumps(duplicate_report, indent=2))
    print(f'Created normalized bundle in {norm} with {len(manifest)} files.')

if __name__ == '__main__':
    main()
