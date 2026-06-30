#!/usr/bin/env python3
"""
cprt_traverser.py
NIST CPRT (Catalog of Publications, Resources, and Tools) recursive traverser.

Enumerates all NIST publications and OLIRs (Online Informative References)
via the CPRT API and compares against feed_registry.json to identify gaps
in framework monitoring coverage.

CPRT API endpoints:
  Publications list : https://csrc.nist.gov/api/catalog/pubs/page/{N}
  OLIR list         : https://csrc.nist.gov/projects/cprt/catalog#olirs (HTML) +
                      https://csrc.nist.gov/api/olir/finalized (unofficial JSON)
  Framework detail  : https://csrc.nist.gov/extensions/nudp/services/json/nudp/
                        framework/version/{pub_id}/element/ALL/structure/default

Output:
  canonical-sources/cprt_gap_report.json
    {framework_id, title, url, in_feed_registry, gap_type}

Usage:
    python3 cprt_traverser.py --dry-run
    python3 cprt_traverser.py --report-only
    python3 cprt_traverser.py --auto-download  # used by olir_crawler
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
FEED_REGISTRY_PATH = _REPO_ROOT / "canonical-sources" / "feed_registry.json"
GAP_REPORT_PATH = _REPO_ROOT / "canonical-sources" / "cprt_gap_report.json"

CPRT_BASE = "https://csrc.nist.gov"
CPRT_PUBS_URL = f"{CPRT_BASE}/api/catalog/pubs/page"
CPRT_OLIR_URL = f"{CPRT_BASE}/api/olir/finalized"

TIMEOUT = 20
MAX_RETRIES = 3
BACKOFF_BASE = 2.0
USER_AGENT = "dbz-cprt-traverser/1.0 (GRC gap analysis; polite client)"


def _fetch_json(url: str) -> dict | list | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(req, timeout=TIMEOUT) as resp:
                raw = b""
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    raw += chunk
                return json.loads(raw)
        except HTTPError as e:
            print(f"  [!] HTTP {e.code} attempt {attempt}: {url}", file=sys.stderr)
            if e.code in (429, 503):
                time.sleep(BACKOFF_BASE ** attempt)
            else:
                return None
        except URLError as e:
            print(f"  [!] URL error attempt {attempt}: {e.reason}", file=sys.stderr)
            time.sleep(BACKOFF_BASE ** attempt)
        except Exception as e:
            print(f"  [!] Error attempt {attempt}: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE ** attempt)
    return None


def _load_feed_registry() -> dict:
    if not FEED_REGISTRY_PATH.exists():
        return {}
    data = json.loads(FEED_REGISTRY_PATH.read_text(encoding="utf-8"))
    return data.get("feeds", {})


def list_all_publications(max_pages: int = 20) -> list[dict]:
    """
    Enumerate NIST CPRT publications via paginated API.
    Returns list of {id, title, url, type} dicts.
    """
    pubs: list[dict] = []
    page = 1
    while page <= max_pages:
        url = f"{CPRT_PUBS_URL}/{page}"
        print(f"  [~] CPRT pubs page {page}: {url}", file=sys.stderr)
        data = _fetch_json(url)
        if data is None:
            print(f"  [!] Failed at page {page}; stopping.", file=sys.stderr)
            break

        items = data if isinstance(data, list) else data.get("items", data.get("results", []))
        if not items:
            break

        for item in items:
            pub_id = item.get("id") or item.get("publicationIdentifier") or item.get("name", "")
            title = item.get("title") or item.get("publicationTitle", "")
            pub_type = item.get("type") or item.get("publicationType", "")
            detail_url = (
                item.get("url")
                or item.get("detailUrl")
                or f"{CPRT_BASE}/publications/detail/{pub_id}"
            )
            if pub_id and title:
                pubs.append({"id": pub_id, "title": title, "type": pub_type, "url": detail_url})

        if len(items) < 10:
            break
        page += 1
        time.sleep(0.5)

    return pubs


def list_all_olirs() -> list[dict]:
    """
    Enumerate all published OLIRs via the CPRT OLIR endpoint.
    Returns list of {olir_id, focal_document, reference_document, download_url} dicts.
    """
    print(f"  [~] Fetching OLIR list from {CPRT_OLIR_URL}", file=sys.stderr)
    data = _fetch_json(CPRT_OLIR_URL)
    if data is None:
        print("  [!] Could not fetch OLIR list.", file=sys.stderr)
        return []

    items = data if isinstance(data, list) else data.get("oLIRs", data.get("items", []))
    olirs: list[dict] = []
    for item in items:
        olir_id = item.get("id") or item.get("olirId", "")
        focal = item.get("focalDocument") or item.get("focal_document", "")
        reference = item.get("referenceDocument") or item.get("reference_document", "")
        download = (
            item.get("downloadUrl")
            or item.get("download_url")
            or item.get("url", "")
        )
        if olir_id or focal:
            olirs.append({
                "olir_id": olir_id,
                "focal_document": focal,
                "reference_document": reference,
                "download_url": download,
            })

    print(f"  [+] Found {len(olirs)} OLIRs", file=sys.stderr)
    return olirs


def find_registry_gaps(
    publications: list[dict],
    olirs: list[dict],
    feed_registry: dict,
) -> list[dict]:
    """
    Compare CPRT publications and OLIRs against feed_registry to find gaps.
    Returns list of gap records.
    """
    gaps: list[dict] = []
    registry_ids = set(feed_registry.keys())

    # Known NIST SP series → feed_registry ID patterns
    sp_patterns = [
        ("sp800-53", "nist-800-53"),
        ("sp800-171", "nist-800-171"),
        ("sp800-172", "nist-800-172"),
        ("sp800-37", "nist-sp-800-37"),
        ("sp800-63", "nist-sp-800-63"),
        ("sp800-56", "nist-sp-800-56a"),
        ("sp800-57", "nist-sp-800-57pt1"),
        ("sp800-160", "nist-sp-800-160-2"),
        ("sp800-213", "nist-sp-800-213a"),
        ("ai100-1", "nist-ai-rmf"),
        ("ai600-1", "nist-ai-600-1"),
        ("fips140", "fips-140-3"),
        ("fips197", "fips-197"),
        ("fips198", "fips-198-1"),
        ("fips199", "fips-199"),
        ("fips200", "fips-200"),
        ("fips201", "fips-201-3"),
        ("ir8477", "nist-ir-8477"),
        ("csf2", "nist-csf"),
    ]

    for pub in publications:
        pub_id_lower = pub["id"].lower().replace("-", "").replace(".", "").replace(" ", "")
        matched_feed_id = None
        for pattern, feed_id in sp_patterns:
            if pattern in pub_id_lower:
                matched_feed_id = feed_id
                break

        in_registry = (matched_feed_id in registry_ids) if matched_feed_id else False
        if not in_registry:
            gaps.append({
                "type": "publication",
                "cprt_id": pub["id"],
                "title": pub["title"],
                "pub_type": pub.get("type", ""),
                "url": pub["url"],
                "suggested_feed_id": matched_feed_id,
                "in_feed_registry": False,
                "gap_type": "unmonitored_publication",
            })

    # Check OLIR coverage
    olir_feed_ids = {
        "SP 800-53": "nist-800-53",
        "CSF": "nist-csf",
        "Privacy Framework": "nist-privacy-fw",
        "SP 800-171": "nist-800-171",
        "SP 800-82": "nist-800-82",
        "AI RMF": "nist-ai-rmf",
    }
    for olir in olirs:
        focal = olir.get("focal_document", "")
        ref = olir.get("reference_document", "")
        matched = False
        for pattern, feed_id in olir_feed_ids.items():
            if pattern.lower() in focal.lower():
                matched = True
                if feed_id not in registry_ids:
                    gaps.append({
                        "type": "olir",
                        "olir_id": olir["olir_id"],
                        "focal_document": focal,
                        "reference_document": ref,
                        "download_url": olir["download_url"],
                        "suggested_feed_id": feed_id,
                        "in_feed_registry": False,
                        "gap_type": "olir_focal_not_monitored",
                    })
                break
        if not matched:
            gaps.append({
                "type": "olir",
                "olir_id": olir["olir_id"],
                "focal_document": focal,
                "reference_document": ref,
                "download_url": olir["download_url"],
                "suggested_feed_id": None,
                "in_feed_registry": False,
                "gap_type": "olir_unmatched",
            })

    return gaps


def _print_summary(
    publications: list[dict],
    olirs: list[dict],
    gaps: list[dict],
) -> None:
    print(f"\n[CPRT Traverser Summary]")
    print(f"  Publications found : {len(publications)}")
    print(f"  OLIRs found        : {len(olirs)}")
    print(f"  Gaps detected      : {len(gaps)}")
    by_type: dict[str, int] = {}
    for g in gaps:
        t = g.get("gap_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    for t, count in sorted(by_type.items()):
        print(f"    {t}: {count}")
    if gaps[:5]:
        print("\n  Sample gaps:")
        for g in gaps[:5]:
            print(f"    [{g['type']}] {g.get('cprt_id') or g.get('olir_id')} → {g.get('gap_type')}")


def run(dry_run: bool = False, report_only: bool = False, max_pages: int = 5) -> dict:
    from datetime import datetime, timezone

    feed_registry = _load_feed_registry()
    print(f"[cprt_traverser] Registry: {len(feed_registry)} feeds", file=sys.stderr)

    print("[cprt_traverser] Fetching CPRT publications…", file=sys.stderr)
    publications = list_all_publications(max_pages=max_pages)

    print("[cprt_traverser] Fetching OLIR list…", file=sys.stderr)
    olirs = list_all_olirs()

    gaps = find_registry_gaps(publications, olirs, feed_registry)

    report = {
        "_generator": "cprt_traverser.py",
        "_generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_feed_registry_count": len(feed_registry),
        "_publications_found": len(publications),
        "_olirs_found": len(olirs),
        "_gaps_found": len(gaps),
        "publications": publications,
        "olirs": olirs,
        "gaps": gaps,
    }

    if dry_run or report_only:
        _print_summary(publications, olirs, gaps)
        return report

    GAP_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    GAP_REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[+] Gap report → {GAP_REPORT_PATH.name} "
        f"({len(publications)} pubs, {len(olirs)} OLIRs, {len(gaps)} gaps)",
        file=sys.stderr,
    )
    _print_summary(publications, olirs, gaps)
    return report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Traverse NIST CPRT to find framework monitoring gaps.",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch but do not write output file.")
    p.add_argument("--report-only", action="store_true",
                   help="Print summary only; skip writing.")
    p.add_argument("--max-pages", type=int, default=5, metavar="N",
                   help="Max CPRT publication API pages to fetch (default: 5).")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    run(dry_run=args.dry_run, report_only=args.report_only, max_pages=args.max_pages)


if __name__ == "__main__":
    main()
