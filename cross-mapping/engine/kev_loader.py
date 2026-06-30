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
# NIST 800-53 family keyword heuristics
# Maps control family → keywords that suggest a CVE falls in that family.
# Applied to: vulnerabilityName + shortDescription (lowercased).
# ---------------------------------------------------------------------------
_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "AC": [
        "access control", "privilege", "unauthorized access", "admin access",
        "remote access", "authentication bypass", "authorization", "account takeover",
        "path traversal", "directory traversal", "insecure direct object",
    ],
    "AU": [
        "log", "audit", "logging", "event log", "syslog",
    ],
    "CA": [
        "assessment", "configuration audit",
    ],
    "CM": [
        "configuration", "default credentials", "default password", "hardcoded",
        "misconfiguration", "firmware", "supply chain",
    ],
    "IA": [
        "authentication", "credential", "password", "brute force", "session",
        "token", "multifactor", "mfa", "identity", "ldap injection",
        "kerberos", "ntlm", "credential stuffing",
    ],
    "IR": [
        "incident", "ransomware", "malware", "exfiltration", "persistence",
        "lateral movement", "command and control", "c2", "backdoor", "rootkit",
        "loader", "dropper",
    ],
    "RA": [
        "vulnerability", "cve", "exploit", "zero-day", "zero day",
    ],
    "SA": [
        "software", "library", "dependency", "supply chain", "open source",
        "third-party", "vendor",
    ],
    "SC": [
        "encryption", "tls", "ssl", "cryptography", "cipher", "certificate",
        "network", "protocol", "injection", "sql injection", "command injection",
        "xxe", "ssrf", "deserialization", "memory corruption", "buffer overflow",
        "heap", "stack overflow", "use-after-free", "type confusion",
    ],
    "SI": [
        "code execution", "remote code execution", "rce", "arbitrary code",
        "overflow", "heap spray", "integer overflow", "format string",
        "xss", "cross-site scripting", "csrf", "cross-site request forgery",
        "file upload", "webshell", "web shell", "unrestricted upload",
        "server-side", "out-of-bounds",
    ],
}


def _map_to_nist_families(vuln: dict) -> list[str]:
    """Return sorted list of NIST 800-53 family codes suggested by this CVE."""
    text = " ".join([
        (vuln.get("vulnerabilityName") or ""),
        (vuln.get("shortDescription") or ""),
        (vuln.get("requiredAction") or ""),
    ]).lower()

    matched: set[str] = set()
    for family, kws in _FAMILY_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                matched.add(family)
                break

    # RA always applies — every exploited vulnerability represents a residual risk
    matched.add("RA")
    return sorted(matched)


# ---------------------------------------------------------------------------
# HTTP fetch with retry
# ---------------------------------------------------------------------------
def _fetch(url: str) -> bytes | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=TIMEOUT) as resp:
                # Read in chunks to handle large responses and IncompleteRead gracefully
                chunks: list[bytes] = []
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                return b"".join(chunks)
        except HTTPError as e:
            print(f"  [!] HTTP {e.code} on attempt {attempt}: {url}", file=sys.stderr)
            if e.code in (429, 503):
                time.sleep(BACKOFF_BASE ** attempt)
            else:
                return None
        except URLError as e:
            print(f"  [!] URL error on attempt {attempt}: {e.reason}", file=sys.stderr)
            time.sleep(BACKOFF_BASE ** attempt)
        except Exception as e:
            print(f"  [!] Unexpected error on attempt {attempt}: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE ** attempt)
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
    """Enrich each KEV entry with NIST 800-53 family mappings."""
    vulns = raw_catalog.get("vulnerabilities", [])
    if max_results is not None:
        vulns = vulns[:max_results]

    enriched: list[dict] = []
    for v in vulns:
        entry = dict(v)
        entry["nist_families"] = _map_to_nist_families(v)
        enriched.append(entry)

    catalog_version = raw_catalog.get("catalogVersion", "")
    date_released = raw_catalog.get("dateReleased", "")

    result = {
        "catalogVersion": catalog_version,
        "dateReleased": date_released,
        "_loader": "kev_loader.py",
        "_fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_vulnerability_count": len(enriched),
        "vulnerabilities": enriched,
    }
    return result


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
    main()
