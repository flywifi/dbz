#!/usr/bin/env python3
"""
Reverse-index builder for the handoff contract.

The generated catalog is NIST-anchored: each NIST control lists its mappings
OUT to other frameworks. But a complete handoff contract must answer the reverse
question too: "Given ISO 27001 A.5.16 (or GDPR Art. 32, or PCI DSS 8.2), which
NIST 800-53 controls satisfy it?"

This builds that inverted index from the generated catalog, so any framework's
native control ID resolves back to the NIST controls that cover it — the lookup
a customer migrating INTO NIST (or auditing a NIST system against ISO/PCI/GDPR)
actually needs.

Output: cross-mapping/output/reverse_index.json
  { framework → { target_control_id → [nist_control_ids] } }

Usage:
    python3 build_reverse_index.py
    python3 build_reverse_index.py --catalog <path> --out <path>
    python3 build_reverse_index.py --query "ISO/IEC 27001:2022" A.5.16
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent

DEFAULT_CATALOG = (
    _REPO_ROOT / "cross-mapping" / "nist-catalog" / "output"
    / "NIST_800_53_FULL_ALL_FAMILIES.json"
)
DEFAULT_OUT = _HERE.parent / "output" / "reverse_index.json"


def _iter_records(catalog: dict):
    """Yield every base control and enhancement record."""
    is_nested = all(re.match(r"^[A-Z]{2,3}$", k) for k in list(catalog.keys())[:10])
    groups = catalog.values() if is_nested else [{"_": r} for r in [catalog]]

    def _walk(record):
        yield record
        for enh in record.get("enhancements", []):
            yield enh

    if is_nested:
        for fam_controls in catalog.values():
            for record in fam_controls.values():
                yield from _walk(record)
    else:
        for record in catalog.values():
            yield from _walk(record)


def build_reverse_index(catalog_path: Path) -> dict:
    """
    Invert the catalog's unified_mappings into:
      { framework → { target_control_id → sorted [nist_control_ids] } }
    """
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    # framework → target_id → set(nist_ids)
    index: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    framework_versions: Dict[str, str] = {}

    for record in _iter_records(catalog):
        nist_id = record.get("id", "")
        if not nist_id:
            continue
        for m in record.get("unified_mappings", []):
            fw = m.get("framework", "")
            tid = m.get("control_id", "")
            if not fw or not tid:
                continue
            index[fw][tid].add(nist_id)
            if m.get("framework_version") and fw not in framework_versions:
                framework_versions[fw] = m["framework_version"]

    # Materialize sets → sorted lists
    out_index = {
        fw: {tid: sorted(nist_ids) for tid, nist_ids in sorted(targets.items())}
        for fw, targets in sorted(index.items())
    }

    stats = {
        fw: {
            "target_controls": len(targets),
            "total_nist_links": sum(len(v) for v in targets.values()),
            "version": framework_versions.get(fw, ""),
        }
        for fw, targets in out_index.items()
    }

    return {
        "_schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_catalog": str(catalog_path),
        "framework_count": len(out_index),
        "stats": stats,
        "index": out_index,
    }


def query(index_doc: dict, framework: str, control_id: str) -> List[str]:
    """Look up which NIST controls map to a given framework control."""
    fw_index = index_doc.get("index", {}).get(framework, {})
    return fw_index.get(control_id, [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the reverse cross-framework index")
    ap.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--query", nargs=2, metavar=("FRAMEWORK", "CONTROL_ID"),
                    help="query mode: print NIST controls mapping to FRAMEWORK CONTROL_ID")
    a = ap.parse_args(argv)

    catalog_path = Path(a.catalog)
    if not catalog_path.exists():
        print(f"[✗] Catalog not found: {catalog_path}\n    Run generate_controls.py first.")
        return 1

    doc = build_reverse_index(catalog_path)

    if a.query:
        fw, cid = a.query
        hits = query(doc, fw, cid)
        print(json.dumps({
            "framework": fw,
            "control_id": cid,
            "nist_controls": hits,
            "count": len(hits),
            "human_review_required": True,
        }, indent=2, ensure_ascii=False))
        return 0

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)

    print(f"[✓] Reverse index: {out_path}")
    print(f"    {doc['framework_count']} frameworks indexed")
    # Show top frameworks by coverage
    top = sorted(doc["stats"].items(), key=lambda kv: -kv[1]["total_nist_links"])[:12]
    for fw, st in top:
        print(f"    {fw:<42} {st['target_controls']:>5} controls  "
              f"{st['total_nist_links']:>6} NIST links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
