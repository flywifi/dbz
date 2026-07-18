#!/usr/bin/env python3
"""
registry_io.py — the single writer for the canonical registries.

The canonical registries are human-authored (or human-confirmed) JSON files whose
formatting must stay diffable: schema key order preserved (no sorting), 2-space
indent, ensure_ascii=False, one trailing newline. Multiple ad-hoc writers with
divergent json.dump conventions turn semantic diffs into formatting noise — so
ALL programmatic writes route through save() here, and sync_check invariant 14
flags any other file that both names a canonical registry and contains a write
primitive.

Canonical registries:
  canonical-sources/feed_registry.json
  canonical-sources/anticipated_updates.json
  canonical-sources/crawl_seeds.json
  canonical-sources/source_manifest.json
  canonical-sources/framework_changelog.json
  canonical-sources/doc_claims.json
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANONICAL = {
    "feed_registry": ROOT / "canonical-sources" / "feed_registry.json",
    "anticipated_updates": ROOT / "canonical-sources" / "anticipated_updates.json",
    "crawl_seeds": ROOT / "canonical-sources" / "crawl_seeds.json",
    "source_manifest": ROOT / "canonical-sources" / "source_manifest.json",
    "framework_changelog": ROOT / "canonical-sources" / "framework_changelog.json",
    "doc_claims": ROOT / "canonical-sources" / "doc_claims.json",
}


def path_for(name: str) -> Path:
    if name not in CANONICAL:
        raise KeyError(f"not a canonical registry: {name!r} (choose from {sorted(CANONICAL)})")
    return CANONICAL[name]


def load(name: str) -> dict:
    """Load a canonical registry (raises if absent — registries are never implicit)."""
    return json.loads(path_for(name).read_text(encoding="utf-8"))


def save(name: str, data: dict) -> Path:
    """Write a canonical registry with the repo's one true JSON convention:
    key order preserved (insertion order — never sorted), indent=2,
    ensure_ascii=False, single trailing newline."""
    p = path_for(name)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def roundtrip_identical(name: str) -> bool:
    """True when load->save of the unchanged registry is byte-identical —
    the guard that adopting registry_io never introduces formatting churn."""
    p = path_for(name)
    before = p.read_text(encoding="utf-8")
    after = json.dumps(json.loads(before), indent=2, ensure_ascii=False) + "\n"
    return before == after


if __name__ == "__main__":
    for n in sorted(CANONICAL):
        ok = CANONICAL[n].exists() and roundtrip_identical(n)
        print(f"  {'ok' if ok else 'DIFFERS' if CANONICAL[n].exists() else 'missing'}: {n}")
