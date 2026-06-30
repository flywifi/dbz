"""
kev_loader.py — CISA Known Exploited Vulnerabilities (KEV) catalog loader.

Downloads the KEV JSON from the CISA direct URL (or local cache) and maps each
CVE to NIST 800-53 control families via a CWE/keyword heuristic.

NOTE: CISA RSS feeds were DEPRECATED May 12, 2025. This loader uses the JSON
direct download URL. For update monitoring, prefer the cisagov/kev-data GitHub
mirror (see feed_registry.json entry 'cisa-kev').

Output: canonical-sources/known_exploited_vulnerabilities.json (pass-through
        of CISA file + nist_families field added per vulnerability)
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
OUTPUT_PATH = _REPO_ROOT / "canonical-sources" / "known_exploited_vulnerabilities.json"

# Heuristic mapping from vulnerability type keywords → NIST 800-53 families
_KEYWORD_FAMILY_MAP = {
    "authentication": ["IA"],
    "bypass": ["AC", "IA"],
    "privilege escalation": ["AC"],
    "privilege": ["AC"],
    "injection": ["SI"],
    "sql injection": ["SI"],
    "code execution": ["SI", "SC"],
    "remote code": ["SI", "SC"],
    "arbitrary code": ["SI", "SC"],
    "buffer overflow": ["SI"],
    "memory": ["SI"],
    "cross-site": ["SI", "SC"],
    "xss": ["SI"],
    "csrf": ["SC"],
    "disclosure": ["SC", "AC"],
    "information disclosure": ["SC"],
    "denial": ["SC", "CP"],
    "dos": ["SC", "CP"],
    "path traversal": ["AC", "SI"],
    "directory traversal": ["AC", "SI"],
    "deserialization": ["SI"],
    "xml": ["SI"],
    "ssrf": ["SC"],
    "open redirect": ["SC"],
    "upload": ["SI"],
    "file inclusion": ["SI"],
    "command injection": ["SI"],
    "race condition": ["SC"],
    "null pointer": ["SI"],
    "use after free": ["SI"],
    "format string": ["SI"],
    "crypto": ["SC"],
    "weak password": ["IA"],
    "default credential": ["IA", "CM"],
    "hardcoded": ["IA", "CM"],
}


def _get_session():
    try:
        import requests
        s = requests.Session()
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            s.proxies = {"https": proxy, "http": proxy}
        s.headers["User-Agent"] = "dbz-grc-engine/1.0 (kev-loader; compliance research)"
        return s
    except ImportError:
        raise RuntimeError("requests library required: pip install requests")


def _fetch_kev(session, url: str) -> dict:
    """Download KEV JSON from CISA."""
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            if attempt < 2:
                time.sleep(4 * (attempt + 1))
            else:
                raise RuntimeError(f"Failed to download KEV: {exc}")


def map_to_nist_families(vuln: dict) -> list:
    """
    Heuristic: map a KEV vulnerability entry to NIST 800-53 control families.
    Uses vulnerability name + short_description keywords.
    """
    text = " ".join([
        (vuln.get("vulnerabilityName") or "").lower(),
        (vuln.get("shortDescription") or "").lower(),
    ])
    families = set()
    for keyword, fams in _KEYWORD_FAMILY_MAP.items():
        if keyword in text:
            families.update(fams)
    # Default: any exploitation → IR (incident response) + SI (system integrity)
    families.update(["IR", "SI"])
    return sorted(families)


def load_kev(dry_run: bool = False,
             url: str = KEV_URL,
             output_path: Optional[Path] = None,
             local_file: Optional[str] = None) -> dict:
    """
    Load KEV catalog and enrich with NIST family mappings.

    Parameters
    ----------
    dry_run     : Print stats without writing output.
    url         : Override KEV download URL.
    output_path : Override output file path.
    local_file  : Load from local file instead of downloading.
    """
    if local_file:
        print(f"Loading KEV from local file: {local_file}")
        with open(local_file) as f:
            raw = json.load(f)
    else:
        session = _get_session()
        print(f"Downloading KEV catalog from CISA...")
        raw = _fetch_kev(session, url)

    vulns = raw.get("vulnerabilities", [])
    catalog_version = raw.get("catalogVersion", "unknown")
    date_released = raw.get("dateReleased", "")

    print(f"  KEV catalog v{catalog_version}, {date_released}: {len(vulns)} entries")

    # Enrich each vulnerability with NIST family mapping
    enriched = []
    for v in vulns:
        entry = dict(v)
        entry["nist_families"] = map_to_nist_families(v)
        enriched.append(entry)

    # Stats by NIST family
    family_counts: dict = {}
    for e in enriched:
        for fam in e["nist_families"]:
            family_counts[fam] = family_counts.get(fam, 0) + 1

    result = {
        "_source": "CISA Known Exploited Vulnerabilities Catalog",
        "_url": url,
        "_catalog_version": catalog_version,
        "_date_released": date_released,
        "_total": len(enriched),
        "_nist_family_distribution": dict(sorted(family_counts.items())),
        "human_review_required": True,
        "vulnerabilities": enriched,
    }

    if not dry_run:
        out = output_path or OUTPUT_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Saved {len(enriched)} KEV entries → {out}")
    else:
        print("  [dry-run] No file written.")

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Load CISA KEV catalog with NIST 800-53 family enrichment")
    parser.add_argument("--url", default=KEV_URL, help="Override KEV download URL")
    parser.add_argument("--local", help="Load from local file instead of downloading")
    parser.add_argument("--output", help="Override output path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    args = parser.parse_args()

    result = load_kev(
        dry_run=args.dry_run,
        url=args.url,
        output_path=Path(args.output) if args.output else None,
        local_file=args.local,
    )

    if args.format == "json":
        out = {k: v for k, v in result.items() if k != "vulnerabilities"}
        print(json.dumps(out, indent=2))
    else:
        print(f"\nKEV Load Summary")
        print(f"  Total CVEs:          {result['_total']}")
        print(f"  Catalog version:     {result['_catalog_version']}")
        print(f"  Date released:       {result['_date_released']}")
        print(f"  NIST family dist:    {result['_nist_family_distribution']}")
        print(f"  Human review needed: {result['human_review_required']}")


if __name__ == "__main__":
    main()
