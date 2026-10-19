#!/usr/bin/env python3
"""
source_manifest_lookup.py — read-only lookup into canonical-sources/source_manifest.json.

The atom behind the `source-manifest-lookup` workflow step (audit-artifact-normalizer,
bulk-evidence-partitioner). Two modes, matching the two workflows' inputs:

  --key  <source id>   exact manifest entry (e.g. scf-controls)
  --role <role>        every entry whose `role` equals the value (e.g. scf_meta_framework)

Unknown keys/roles return an error object and exit 1 — an entry is never synthesized.
Stdlib only; never writes.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "canonical-sources" / "source_manifest.json"


def _entries() -> list:
    return json.loads(MANIFEST.read_text(encoding="utf-8")).get("sources", [])


def lookup(key: str | None = None, role: str | None = None) -> dict:
    entries = _entries()
    if key:
        hit = next((e for e in entries if e.get("id") == key), None)
        if hit is None:
            return {"error": f"source key not found in source_manifest: {key!r}",
                    "human_review_required": True}
        return {"manifest_entry": hit, "count": 1, "human_review_required": True}
    hits = [e for e in entries if e.get("role") == role]
    if not hits:
        roles = sorted({e.get("role") for e in entries if e.get("role")})
        return {"error": f"role not found in source_manifest: {role!r}",
                "known_roles": roles, "human_review_required": True}
    return {"manifest_entries": hits, "count": len(hits), "human_review_required": True}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only source_manifest.json lookup")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--key", help="exact source id")
    g.add_argument("--role", help="source role (all matching entries)")
    a = ap.parse_args(argv)
    out = lookup(key=a.key, role=a.role)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 1 if "error" in out else 0


if __name__ == "__main__":
    sys.exit(main())
