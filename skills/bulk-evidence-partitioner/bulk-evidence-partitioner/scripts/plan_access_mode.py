#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ARTIFACT_SUBDIR_BY_SKILL = {
    'audit-artifact-normalizer': 'normalized',
    'bulk-evidence-partitioner': 'partition',
    'claim-and-output-validator': 'validation',
    'durable-account-memory': 'memory',
    'permission-aware-connector-template': 'security',
    'public-web-evidence-crawler': 'crawl',
    'semantic-account-memory': 'semantic',
    'skill-observability': 'trace',
    'skill-regression-and-red-team': 'eval',
    'url-reader-and-cleaner': 'url-pack',
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def choose_mode(args: argparse.Namespace) -> tuple[str, str, list[str]]:
    if args.oauth or args.api_key or args.self_hosted:
        return (
            'direct_integration',
            'direct vendor credentials or a self-hosted endpoint are available',
            [
                'Use the explicit integration path only for the parts that truly need it.',
                'Keep local or runtime-native fallbacks available in case the integration path fails.',
            ],
        )
    if args.connector_access or args.web_access:
        return (
            'runtime_native',
            'runtime-native connectors, browsing, or tools are available without new credentials',
            [
                'Prefer native runtime tools before external services.',
                'Preserve stable artifacts so the run can be audited or repeated later.',
            ],
        )
    if args.uploaded_files:
        return (
            'local_artifact',
            'uploaded files, exports, or manual JSON are available',
            [
                'Use local artifacts as the evidence base.',
                'Do not imply that any live system was queried unless it actually was.',
            ],
        )
    return (
        'planning_only',
        'no live or local artifact path is available yet',
        [
            'Emit contracts, templates, and next-step instructions only.',
            'Do not invent findings, memories, traces, or validations that were not actually run.',
        ],
    )


def resolve_dirs(out_dir: Path, skill_name: str, explicit_subdir: str | None) -> tuple[Path, Path]:
    artifact_subdir = explicit_subdir or ARTIFACT_SUBDIR_BY_SKILL.get(skill_name, 'artifacts')
    out_dir = out_dir.resolve()
    if out_dir.name == artifact_subdir:
        return out_dir.parent, out_dir
    return out_dir, out_dir / artifact_subdir


def write_summary(base_dir: Path, artifact_dir: Path, payload: dict) -> None:
    lines = [
        f"# {payload['skill_name']} access mode",
        '',
        f"- selected mode: `{payload['selected_mode']}`",
        f"- rationale: {payload['rationale']}",
        '',
        '## inputs',
    ]
    for key, value in payload['inputs'].items():
        lines.append(f"- {key}: {value}")
    if payload.get('recommendations'):
        lines.extend(['', '## recommendations'])
        lines.extend([f"- {item}" for item in payload['recommendations']])
    if payload.get('operator_notes'):
        lines.extend(['', '## operator notes', payload['operator_notes']])
    summary = '\n'.join(lines) + '\n'
    (artifact_dir / 'access-mode-summary.md').write_text(summary, encoding='utf-8')
    (base_dir / 'summary.md').write_text(summary, encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description='Choose the safest available access mode for this skill.')
    parser.add_argument('--skill-name', required=True)
    parser.add_argument('--out-dir', default='.')
    parser.add_argument('--artifact-subdir', default=None)
    parser.add_argument('--connector-access', action='store_true', help='native connector or runtime tool access is available')
    parser.add_argument('--uploaded-files', action='store_true', help='user supplied files, exports, or manual JSON are available')
    parser.add_argument('--web-access', action='store_true', help='native web browsing is available inside the runtime')
    parser.add_argument('--oauth', action='store_true', help='oauth-based vendor integration is available')
    parser.add_argument('--api-key', action='store_true', help='api key based vendor integration is available')
    parser.add_argument('--self-hosted', action='store_true', help='self-hosted service endpoint is available')
    parser.add_argument('--notes', default='')
    args = parser.parse_args()

    mode, rationale, recommendations = choose_mode(args)
    base_dir, artifact_dir = resolve_dirs(Path(args.out_dir), args.skill_name, args.artifact_subdir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        'skill_name': args.skill_name,
        'artifact_subdir': artifact_dir.name,
        'selected_mode': mode,
        'rationale': rationale,
        'inputs': {
            'connector_access': args.connector_access,
            'uploaded_files': args.uploaded_files,
            'web_access': args.web_access,
            'oauth': args.oauth,
            'api_key': args.api_key,
            'self_hosted': args.self_hosted,
        },
        'operator_notes': args.notes,
        'recommendations': recommendations,
        'generated_at': iso_now(),
    }

    artifact_path = artifact_dir / 'access-mode.json'
    artifact_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    root_path = base_dir / 'access-mode.json'
    if root_path != artifact_path:
        root_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    write_summary(base_dir, artifact_dir, payload)
    print(f'Wrote {artifact_path}')


if __name__ == '__main__':
    main()
