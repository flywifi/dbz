#!/usr/bin/env python3
"""
NVD CVE API 2.0 Loader

Pulls CVE data from the NIST National Vulnerability Database (NVD) CVE API 2.0
and maps each CVE to NIST SP 800-53 Rev. 5 control families via its associated
CWE (Common Weakness Enumeration) identifiers using a heuristic mapping.

API endpoint: https://services.nvd.nist.gov/rest/json/cves/2.0
Rate limits:
  Without API key: 5 requests / 30 seconds  → 6 s sleep between pages
  With API key:   50 requests / 30 seconds  → 0.6 s sleep between pages
  Set env var NVD_API_KEY to enable higher-rate mode.

Output: canonical-sources/nvd-cve-{YYYY-MM-DD}.json

Usage:
  python3 nvd_api_loader.py                        # last 30 days, summary
  python3 nvd_api_loader.py --days 7               # last 7 days
  python3 nvd_api_loader.py --days 30 --dry-run    # parse without file write
  python3 nvd_api_loader.py --days 30 --format json
  python3 nvd_api_loader.py --format summary        # summary statistics only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import fetchkit  # governed fetch: host_policies.json caps, pacing, breaker, ledger (phase 51)

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_CANONICAL_DIR = _REPO_ROOT / "canonical-sources"

NVD_CVE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_RESULTS_PER_PAGE = 2000   # NVD API 2.0 maximum

# Rate-limit sleeps (seconds)

# ── CWE → NIST 800-53 family mapping ─────────────────────────────────────────
# Based on CWE taxonomy / NIST 800-53 Rev. 5 control categories.
# Multiple families can match a single CWE.




def _nist_families_for_cwes(cwe_ids):
    """Always []: no issuer maps CWE to NIST 800-53 controls; the hand table (default SI-3) was a guess."""
    return []


# ── network utilities ─────────────────────────────────────────────────────────

def _fetch_json(url, params, api_key, max_retries=3, initial_delay=6.0, timeout=60):
    """Fetch JSON from NVD API with query params, through the governor."""
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": "dbz-grc-nvd-loader/1.0 (GRC cross-mapping backend)",
               "Accept": "application/json"}
    if api_key:
        headers["apiKey"] = api_key
    try:
        raw = fetchkit.fetch(full_url, headers=headers, timeout=timeout, retries=max_retries,
                             retry_on=(403, 429, 503), backoff=initial_delay).body
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429, 503):
            raise RuntimeError(f"Failed to fetch NVD API after {max_retries} attempts") from exc
        raise
    except (fetchkit.PolicyRefused, fetchkit.HostCooldown):
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to fetch NVD API after {max_retries} attempts") from exc
    return json.loads(raw.decode("utf-8"))


# ── CVE parsing ───────────────────────────────────────────────────────────────

def _extract_cve(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured fields from a single NVD CVE 2.0 API result item.

    Returns a dict with:
      cve_id, published, last_modified, description, cvss_score,
      severity, cwe_ids, nist_families, affected_products
    """
    cve_data = item.get("cve", {})
    cve_id   = cve_data.get("id", "")

    # Description (English preferred)
    descriptions = cve_data.get("descriptions", [])
    description  = ""
    for d in descriptions:
        if d.get("lang") == "en":
            description = d.get("value", "")
            break
    if not description and descriptions:
        description = descriptions[0].get("value", "")

    # CVSS score and severity — prefer v3.1 then v3.0 then v2
    cvss_score: Optional[float] = None
    severity:   Optional[str]   = None
    metrics = cve_data.get("metrics", {})

    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key, [])
        if entries:
            e = entries[0]
            cvss_data = e.get("cvssData", {})
            cvss_score = cvss_data.get("baseScore")
            severity   = cvss_data.get("baseSeverity") or e.get("baseSeverity")
            if cvss_score is not None:
                break

    # CWE IDs
    cwe_ids: List[str] = []
    weaknesses = cve_data.get("weaknesses", [])
    for w in weaknesses:
        for desc in w.get("description", []):
            val = desc.get("value", "")
            if val.upper().startswith("CWE-"):
                if val not in cwe_ids:
                    cwe_ids.append(val)

    # NIST families via CWE mapping
    nist_families = _nist_families_for_cwes(cwe_ids)

    # Affected products (CPE matches — summarized)
    affected_products: List[str] = []
    configs = cve_data.get("configurations", [])
    seen_products: Set[str] = set()
    for cfg in configs:
        for node in cfg.get("nodes", []):
            for cpe_match in node.get("cpeMatch", []):
                cpe = cpe_match.get("criteria", "")
                if cpe:
                    # Extract vendor:product from CPE URI (part 3 and 4)
                    parts = cpe.split(":")
                    if len(parts) >= 5:
                        product_key = f"{parts[3]}:{parts[4]}"
                        if product_key not in seen_products:
                            seen_products.add(product_key)
                            affected_products.append(product_key)
                            if len(affected_products) >= 10:
                                break

    return {
        "cve_id":           cve_id,
        "published":        cve_data.get("published", ""),
        "last_modified":    cve_data.get("lastModified", ""),
        "description":      description[:500] + ("…" if len(description) > 500 else ""),
        "cvss_score":       cvss_score,
        "severity":         severity,
        "cwe_ids":          cwe_ids,
        "nist_families":    nist_families,
        "affected_products": affected_products,
    }


# ── main class ────────────────────────────────────────────────────────────────

class NVDLoader:
    """
    Fetches CVE data from the NVD CVE API 2.0 and maps CVEs to NIST
    SP 800-53 Rev. 5 control families via CWE identifiers.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key  = api_key or os.environ.get("NVD_API_KEY")

    def map_cwe_to_nist(self, cwe_id: str) -> List[str]:
        """Always []: no issuer maps CWE ids to NIST 800-53 controls (phase 52; the hand table was a guess)."""
        return []

    def fetch_page(
        self,
        start_index: int,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Fetch one page of CVE results from NVD API 2.0.

        Parameters:
          start_index  — zero-based offset for pagination
          start_date   — ISO 8601 datetime string (e.g. '2024-01-01T00:00:00.000')
          end_date     — ISO 8601 datetime string

        Returns the raw API response dict.
        """
        params: Dict[str, str] = {
            "lastModStartDate":  start_date,
            "lastModEndDate":    end_date,
            "resultsPerPage":    str(_RESULTS_PER_PAGE),
            "startIndex":        str(start_index),
        }
        return _fetch_json(
            NVD_CVE_URL,
            params,
            api_key=self._api_key,
        )

    def fetch_range(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Fetch all CVEs modified between start_date and end_date (paginated).

        Returns list of parsed CVE dicts.
        Sleeps between pages to respect NVD rate limits.
        """
        cves: List[Dict[str, Any]] = []
        start_index = 0
        total_results: Optional[int] = None

        while True:
            page = self.fetch_page(start_index, start_date, end_date)

            if total_results is None:
                total_results = page.get("totalResults", 0)
                results_per_page = page.get("resultsPerPage", _RESULTS_PER_PAGE)
                print(
                    f"  NVD API: {total_results} total CVEs in range "
                    f"({start_date[:10]} → {end_date[:10]})"
                )

            items = page.get("vulnerabilities", [])
            if not items:
                break

            for item in items:
                try:
                    cves.append(_extract_cve(item))
                except Exception as exc:
                    cve_id = item.get("cve", {}).get("id", "unknown")
                    print(f"  [warn] Skipping {cve_id}: {exc}", file=sys.stderr)

            start_index += len(items)

            # Progress indicator
            print(f"  Fetched {len(cves)}/{total_results} CVEs…")

            if start_index >= (total_results or 0):
                break

        return cves

    def run(self, days: int = 30, dry_run: bool = False) -> Dict[str, Any]:
        """
        Full pipeline: fetch last 'days' days of CVE data from NVD API 2.0,
        map to NIST families, and optionally save output.

        Returns result dict.
        """
        print("=== NVD CVE API 2.0 Loader ===")
        if self._api_key:
            print("  Using NVD_API_KEY (higher rate limit)")
        else:
            print("  No API key — NVD window from host_policies.json (5 per 30 s; 50 with NVD_API_KEY)")

        now       = datetime.now(timezone.utc)
        end_dt    = now
        start_dt  = now - timedelta(days=days)

        # NVD API 2.0 datetime format: ISO 8601 with milliseconds, no TZ suffix
        def _fmt(dt: datetime) -> str:
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000")

        start_str = _fmt(start_dt)
        end_str   = _fmt(end_dt)

        print(f"  Date range: {start_str[:10]} → {end_str[:10]} ({days} days)")

        try:
            cves = self.fetch_range(start_str, end_str)
        except RuntimeError as exc:
            print(f"  [error] {exc}", file=sys.stderr)
            cves = []

        # Statistics
        high_cvss = sum(1 for c in cves if (c.get("cvss_score") or 0.0) >= 7.0)
        critical  = sum(1 for c in cves if (c.get("severity") or "").upper() == "CRITICAL")

        # Family frequency
        family_freq: Dict[str, int] = {}
        for c in cves:
            for f in c.get("nist_families", []):
                family_freq[f] = family_freq.get(f, 0) + 1

        print(
            f"\n  Summary: {len(cves)} CVEs loaded, "
            f"CVSS >= 7.0: {high_cvss}, "
            f"CRITICAL: {critical}"
        )

        # Version anchor: max lastModified across all fetched CVEs for incremental re-runs
        modified_dates = [c["last_modified"] for c in cves if c.get("last_modified")]
        latest_cve_modified = max(modified_dates) if modified_dates else end_str

        result: Dict[str, Any] = {
            "_latest_cve_modified_date": latest_cve_modified,
            "metadata": {
                "generated_at":     now.isoformat(),
                "query_start_date": start_str,
                "query_end_date":   end_str,
                "days_covered":     days,
                "total_cves":       len(cves),
                "high_cvss_count":  high_cvss,
                "critical_count":   critical,
                "nist_family_freq": dict(
                    sorted(family_freq.items(), key=lambda kv: kv[1], reverse=True)
                ),
                "api_key_used":     bool(self._api_key),
                "human_review_required": True,
            },
            "cves": cves,
        }

        if not dry_run:
            date_tag = now.strftime("%Y-%m-%d")
            out_path = _CANONICAL_DIR / f"nvd-cve-{date_tag}.json"
            _CANONICAL_DIR.mkdir(parents=True, exist_ok=True)

            # Append mode: if file exists for today, merge (extend) CVE list
            if out_path.exists():
                try:
                    existing = json.loads(out_path.read_text(encoding="utf-8"))
                    existing_ids = {c["cve_id"] for c in existing.get("cves", [])}
                    new_cves = [c for c in cves if c["cve_id"] not in existing_ids]
                    if new_cves:
                        print(
                            f"  Appending {len(new_cves)} new CVEs to existing file ({out_path.name})"
                        )
                        existing["cves"].extend(new_cves)
                        existing["metadata"]["total_cves"] = len(existing["cves"])
                        existing["metadata"]["generated_at"] = now.isoformat()
                        result = existing
                    else:
                        print(f"  No new CVEs to add to {out_path.name}")
                except Exception as exc:
                    print(f"  [warn] Could not read existing file for merge: {exc}", file=sys.stderr)

            out_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  Saved → {out_path}")
        else:
            print("  [dry-run] Skipping file write.")

        return result


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pull CVE data from NVD API 2.0 and map to NIST 800-53 control families."
    )
    p.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of CVE data to fetch (default: 30)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse without writing output file",
    )
    p.add_argument(
        "--format",
        choices=["json", "summary"],
        default="summary",
        help="Output format for stdout (default: summary)",
    )
    p.add_argument(
        "--api-key",
        default=None,
        help="NVD API key (overrides NVD_API_KEY env var)",
    )
    return p


def main() -> None:
    args   = _build_parser().parse_args()
    loader = NVDLoader(api_key=args.api_key)
    result = loader.run(days=args.days, dry_run=args.dry_run)

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        meta = result["metadata"]
        print(
            f"\nSummary: {meta['total_cves']} CVEs loaded, "
            f"CVSS >= 7.0: {meta['high_cvss_count']}, "
            f"CRITICAL: {meta['critical_count']}"
        )
        if meta.get("nist_family_freq"):
            top = list(meta["nist_family_freq"].items())[:5]
            top_str = ", ".join(f"{k}={v}" for k, v in top)
            print(f"Top NIST families: {top_str}")


if __name__ == "__main__":
    fetchkit.run_cli(main, "nvd_api_loader")
