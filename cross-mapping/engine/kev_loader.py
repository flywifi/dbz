#!/usr/bin/env python3
"""
kev_loader.py
CISA Known Exploited Vulnerabilities (KEV) Catalog loader.

Fetches the CISA KEV JSON catalog, enriches each CVE with a heuristic NIST
800-53 control-family mapping based on vulnerability keywords, and writes
the enriched catalog to canonical-sources/known_exploited_vulnerabilities.json.

Sources:
  Primary   — CISA KEV JSON: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
  Fallback  — cisagov/kev-data GitHub mirror (preferred after CISA RSS deprecation May 2025):
              https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json

Output: canonical-sources/known_exploited_vulnerabilities.json

Usage:
    python3 kev_loader.py --dry-run
    python3 kev_loader.py --max-results 500
    python3 kev_loader.py --format summary
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import fetchkit  # governed fetch: host_policies.json caps, pacing, breaker, ledger (phase 51)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
OUTPUT_PATH = _REPO_ROOT / "canonical-sources" / "known_exploited_vulnerabilities.json"

# ---------------------------------------------------------------------------
# Source URLs (no cross-repo dependencies — all stdlib)
# ---------------------------------------------------------------------------
KEV_PRIMARY_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
)
KEV_FALLBACK_URL = (
    "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json"
)

TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_BASE = 2.0
USER_AGENT = "dbz-kev-loader/1.0 (GRC cross-mapping; polite client)"



# ---------------------------------------------------------------------------
# HTTP fetch with retry
# ---------------------------------------------------------------------------
def _fetch(url: str) -> bytes | None:
    try:
        return fetchkit.fetch(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
                              retries=MAX_RETRIES, retry_on=(429, 503), backoff=BACKOFF_BASE).body
    except (fetchkit.PolicyRefused, fetchkit.HostCooldown) as e:
        print(f"  [!] fetch policy: {e}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 — contract: None on failure
        print(f"  [!] {type(e).__name__} {getattr(e, 'code', '')}: {url}", file=sys.stderr)
    return None


def fetch_kev_catalog() -> dict:
    """Fetch KEV catalog from CISA (primary) or GitHub mirror (fallback)."""
    for url, label in [(KEV_PRIMARY_URL, "CISA primary"), (KEV_FALLBACK_URL, "GitHub mirror")]:
        print(f"  [~] Trying {label}: {url}", file=sys.stderr)
        raw = _fetch(url)
        if raw:
            try:
                data = json.loads(raw)
                if "vulnerabilities" in data:
                    print(f"  [+] Fetched {len(data['vulnerabilities'])} CVEs from {label}",
                          file=sys.stderr)
                    return data
            except json.JSONDecodeError:
                print(f"  [!] JSON parse error from {label}", file=sys.stderr)
    raise RuntimeError("Could not fetch KEV catalog from primary or fallback URL.")


def enrich_kev_catalog(raw_catalog: dict, max_results: int | None = None) -> dict:
    """KEV entries as CISA publishes them. nist_families stays empty: no issuer maps KEV entries to
    NIST 800-53 families, and a keyword guess is a fabricated mapping (CLAUDE.md; phase 52)."""
    vulns = raw_catalog.get("vulnerabilities", [])
    if max_results is not None:
        vulns = vulns[:max_results]
    enriched = []
    for v in vulns:
        entry = dict(v)
        entry["nist_families"] = []
        enriched.append(entry)
    return {"catalogVersion": raw_catalog.get("catalogVersion", ""), "dateReleased": raw_catalog.get("dateReleased", ""),
            "_loader": "kev_loader.py", "_fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "_vulnerability_count": len(enriched), "vulnerabilities": enriched}


def _print_dry_run_summary(catalog: dict) -> None:
    vulns = catalog.get("vulnerabilities", [])
    print(f"\n[DRY-RUN] CISA KEV Catalog")
    print(f"  Catalog version : {catalog.get('catalogVersion', 'unknown')}")
    print(f"  Date released   : {catalog.get('dateReleased', 'unknown')}")
    print(f"  CVE count       : {len(vulns)}")
    if vulns:
        # Show family distribution
        family_counts: dict[str, int] = {}
        for v in vulns:
            for f in v.get("nist_families", []):
                family_counts[f] = family_counts.get(f, 0) + 1
        print("\n  NIST family distribution (top CVEs → families):")
        for fam, count in sorted(family_counts.items(), key=lambda x: -x[1]):
            print(f"    {fam}: {count}")
        # Sample 3 entries
        print("\n  Sample CVEs:")
        for v in vulns[:3]:
            print(f"    {v.get('cveID', '?')} — {v.get('vulnerabilityName', '?')}")
            print(f"      NIST families: {', '.join(v.get('nist_families', []))}")


def run(
    dry_run: bool = False,
    max_results: int | None = None,
    fmt: str = "summary",
) -> dict:
    print("[kev_loader] Fetching CISA KEV catalog…", file=sys.stderr)
    raw_catalog = fetch_kev_catalog()
    catalog = enrich_kev_catalog(raw_catalog, max_results=max_results)

    if dry_run:
        _print_dry_run_summary(catalog)
        return catalog

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(
        f"[+] Saved {catalog['_vulnerability_count']} enriched KEV entries → {OUTPUT_PATH.name}",
        file=sys.stderr,
    )

    if fmt == "json":
        print(json.dumps(catalog, indent=2, ensure_ascii=False, default=str))
    elif fmt == "summary":
        _print_dry_run_summary(catalog)

    return catalog


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch and enrich CISA KEV catalog with NIST 800-53 family mappings.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and enrich but do not write output file.",
    )
    p.add_argument(
        "--max-results", type=int, default=None, metavar="N",
        help="Limit to first N vulnerabilities (useful for testing).",
    )
    p.add_argument(
        "--format", dest="fmt", choices=["summary", "json", "none"],
        default="summary",
        help="Output format: summary (default), json, or none.",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    run(
        dry_run=args.dry_run,
        max_results=args.max_results,
        fmt=args.fmt,
    )


if __name__ == "__main__":
    fetchkit.run_cli(main, "kev_loader")
