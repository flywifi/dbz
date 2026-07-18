#!/usr/bin/env python3
"""
registry_currency.py — content-sha drift baselines for the canonical registries.

A silent edit to a canonical registry (a feed URL change, a horizon date, a pin)
should trigger a named review step, not slip through. This tool keeps a sha256
baseline per registry in canonical-sources/registry_baselines.json; on --check,
any drift is reported as an ADVISORY naming the re-verification authority —
registries change legitimately, so drift is a review prompt, not a failure
(use --strict for a hard gate in a release context).

Re-verification authority per registry (who/what confirms a change is right):
  feed_registry / crawl_seeds  -> docs/standards-refresh-runbook.md procedure
  anticipated_updates          -> docs/horizon-scanning.md (no fabricated dates)
  source_manifest              -> the pinned source itself (re-open, re-verify pin)
  framework_changelog          -> human_confirmed flag per entry
  doc_claims                   -> tools/count_truth.py --check

Usage:
  python3 tools/registry_currency.py --check           # advisory drift report
  python3 tools/registry_currency.py --check --strict  # exit 1 on drift
  python3 tools/registry_currency.py --update          # re-baseline after review
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry_io

BASELINES = registry_io.ROOT / "canonical-sources" / "registry_baselines.json"

AUTHORITY = {
    "feed_registry": "docs/standards-refresh-runbook.md procedure",
    "crawl_seeds": "docs/standards-refresh-runbook.md procedure",
    "anticipated_updates": "docs/horizon-scanning.md (no fabricated dates)",
    "source_manifest": "the pinned source itself (re-open, re-verify the pin)",
    "framework_changelog": "human_confirmed flag per entry",
    "doc_claims": "tools/count_truth.py --check",
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def current() -> dict:
    return {n: _sha(p) for n, p in sorted(registry_io.CANONICAL.items()) if p.exists()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--strict", action="store_true", help="with --check: exit 1 on drift")
    ap.add_argument("--update", action="store_true", help="re-baseline (after review)")
    a = ap.parse_args(argv)

    now = current()
    if a.update:
        BASELINES.write_text(json.dumps(
            {"_purpose": "sha256 baselines per canonical registry; drift is an advisory "
                         "naming the re-verification authority (tools/registry_currency.py).",
             "baselines": now}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"baselined {len(now)} registries -> {BASELINES.relative_to(registry_io.ROOT)}")
        return 0

    if not BASELINES.exists():
        print("[advisory] no baselines yet — run with --update to establish them")
        return 1 if a.strict else 0
    base = json.loads(BASELINES.read_text(encoding="utf-8"))["baselines"]
    drifted = [n for n in now if base.get(n) != now[n]]
    missing = [n for n in base if n not in now]
    for n in drifted:
        print(f"  [advisory] {n} changed since baseline — re-verify via: {AUTHORITY[n]}; "
              "then tools/registry_currency.py --update")
    for n in missing:
        print(f"  [advisory] {n} missing (was baselined)")
    if not drifted and not missing:
        print(f"[registry-currency OK] {len(now)} registries match their baselines")
        return 0
    return 1 if a.strict else 0


if __name__ == "__main__":
    sys.exit(main())
