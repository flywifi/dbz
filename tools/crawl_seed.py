#!/usr/bin/env python3
"""Recursive crawl-seed / link-graph resolver (Phase 25).

Expands the seed roots in canonical-sources/crawl_seeds.json into candidate child
URLs using DETERMINISTIC, OFFLINE URL-template expansion (no network) — so a review
run produces the same candidate set every time. The network-heavy live traversal
runs LOCALLY via tools/crawl_seed.ps1 (PowerShell), whose JSON output is merged back
with `--import`. Nothing here auto-ingests; every candidate is a review stub, and any
anticipatable signal a live crawl finds is routed to anticipated_updates.json.

Usage:
  crawl_seed.py --list [--seed ID] [--format json|table]   # deterministic candidate expansion
  crawl_seed.py --import discovered.json [--format ...]      # merge a PS1 live-crawl result set
  crawl_seed.py --selftest                                   # determinism + well-formedness self-check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
SEEDS_PATH = REPO_ROOT / "canonical-sources" / "crawl_seeds.json"


def load_registry(path: Path = SEEDS_PATH) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expand_seed(seed: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return the deterministic candidate child URLs for one seed."""
    out: List[Dict[str, str]] = []
    resolver = seed.get("resolver")
    tmpl = seed.get("child_template", "")
    sid = seed["id"]
    if resolver == "id_range":
        lo, hi = seed.get("id_range", [0, 0])
        for i in range(int(lo), int(hi) + 1):
            out.append({"seed": sid, "kind": "olir_detail", "url": tmpl.format(id=i)})
    elif resolver == "cfr_titles":
        for t in seed.get("titles", []):
            out.append({"seed": sid, "kind": "cfr_title", "url": tmpl.format(title=t)})
    elif resolver == "fr_saved_query":
        for a in seed.get("agencies", []):
            out.append({"seed": sid, "kind": "fr_query", "url": tmpl.format(agency=a)})
    elif resolver == "celex":
        for c in seed.get("celex", []):
            out.append({"seed": sid, "kind": "celex", "url": tmpl.format(celex=c)})
    elif resolver == "github_raw":
        for r in seed.get("repos", []):
            out.append({"seed": sid, "kind": "github_raw",
                        "url": tmpl.format(repo=r["repo"], ref=r.get("ref", "main")),
                        "status": r.get("status", "")})
    # deterministic order
    out.sort(key=lambda r: (r["seed"], r["kind"], r["url"]))
    return out


def expand_seeds(registry: Dict[str, Any], only: str | None = None) -> List[Dict[str, str]]:
    """Deterministic candidate expansion across all seeds (or one via `only`)."""
    cands: List[Dict[str, str]] = []
    for seed in registry.get("seeds", []):
        if only and seed.get("id") != only:
            continue
        cands.extend(_expand_seed(seed))
    cands.sort(key=lambda r: (r["seed"], r["kind"], r["url"]))
    return cands


def _selftest() -> int:
    reg = load_registry()
    # well-formedness
    problems = []
    seen_ids = set()
    for s in reg.get("seeds", []):
        for k in ("id", "authority", "root", "resolver"):
            if not s.get(k):
                problems.append(f"seed missing {k}: {s.get('id')}")
        if s.get("id") in seen_ids:
            problems.append(f"duplicate seed id {s.get('id')}")
        seen_ids.add(s.get("id"))
    # determinism
    a = expand_seeds(reg)
    b = expand_seeds(reg)
    if a != b:
        problems.append("expand_seeds not deterministic")
    if not a:
        problems.append("expand_seeds produced no candidates")
    if problems:
        print("CRAWL-SEED SELFTEST: FAIL")
        for p in problems:
            print("  -", p)
        return 1
    print(f"CRAWL-SEED SELFTEST: PASS ({len(reg['seeds'])} seeds, "
          f"{len(a)} deterministic candidates)")
    return 0


def cmd_list(args) -> int:
    reg = load_registry()
    cands = expand_seeds(reg, only=args.seed)
    if args.format == "json":
        print(json.dumps({"tool": "crawl-seed", "candidate_count": len(cands),
                          "candidates": cands,
                          "note": "deterministic offline expansion; run tools/crawl_seed.ps1 for live traversal, "
                                  "then merge with --import. Nothing auto-ingests.",
                          "human_review_required": True}, indent=2))
    else:
        for c in cands:
            flag = f"  [{c['status']}]" if c.get("status") else ""
            print(f"  {c['seed']:20} {c['kind']:12} {c['url']}{flag}")
        print(f"\n{len(cands)} candidates (deterministic). Live traversal: tools/crawl_seed.ps1")
    return 0


def cmd_import(args) -> int:
    """Merge a PowerShell live-crawl result set (list of {url,...}) — dedup + sort."""
    disc = json.loads(Path(args.import_file).read_text(encoding="utf-8"))
    items = disc.get("discovered", disc) if isinstance(disc, dict) else disc
    urls = {}
    for it in items:
        u = it.get("url") if isinstance(it, dict) else str(it)
        if u:
            urls[u] = it if isinstance(it, dict) else {"url": u}
    merged = [urls[u] for u in sorted(urls)]
    if args.format == "json":
        print(json.dumps({"tool": "crawl-seed-import", "merged_count": len(merged),
                          "discovered": merged, "human_review_required": True}, indent=2))
    else:
        for m in merged:
            print(f"  {m.get('url')}")
        print(f"\n{len(merged)} discovered URLs (deduped). Review before adding to feed_registry.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Recursive crawl-seed / link-graph resolver")
    ap.add_argument("--list", action="store_true", help="deterministic candidate expansion (offline)")
    ap.add_argument("--seed", metavar="ID", help="limit --list to one seed id")
    ap.add_argument("--import", dest="import_file", metavar="FILE",
                    help="merge a crawl_seed.ps1 live-crawl JSON result")
    ap.add_argument("--selftest", action="store_true", help="determinism + well-formedness check")
    ap.add_argument("--format", choices=["json", "table"], default="table")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.import_file:
        return cmd_import(args)
    # default is --list
    return cmd_list(args)


if __name__ == "__main__":
    sys.exit(main())
