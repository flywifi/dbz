"""
edgar_loader.py — SEC EDGAR 8-K Item 1.05 cybersecurity incident disclosure loader.

Fetches 8-K filings with Item 1.05 (material cybersecurity incident disclosures)
via the SEC EDGAR full-text search API and maps incident types to NIST 800-53
control families. Effective Dec 15, 2023 (SEC rule 33-11216).

APIs used:
  - Full-text search: https://efts.sec.gov/LATEST/search-index
  - Submissions:      https://data.sec.gov/submissions/CIK{10digits}.json

Output: canonical-sources/edgar-8k-cyber.json
        grc.db edgar_cyber_incidents table (via build_db.py)
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
OUTPUT_PATH = _REPO_ROOT / "canonical-sources" / "edgar-8k-cyber.json"

# Map incident keywords (from 8-K text) → NIST 800-53 families
_INCIDENT_NIST_MAP = {
    "ransomware": ["IR", "SC", "CP"],
    "ransom": ["IR", "SC", "CP"],
    "extortion": ["IR", "SC"],
    "unauthorized access": ["IA", "AC", "IR"],
    "unauthorized": ["IA", "AC", "IR"],
    "data breach": ["AC", "AU", "IR"],
    "breach": ["AC", "AU", "IR"],
    "phishing": ["IA", "AT", "IR"],
    "credential": ["IA", "AC"],
    "malware": ["SI", "IR"],
    "denial of service": ["SC", "CP", "IR"],
    "disruption": ["CP", "IR"],
    "exfiltration": ["AC", "SC", "AU"],
    "data theft": ["AC", "SC"],
    "supply chain": ["SA", "IR"],
    "third-party": ["SA", "IR"],
    "vulnerability": ["RA", "SI"],
    "exploitation": ["RA", "SI"],
}


def _build_edgar_url(accession: str, file_num: str = "") -> str:
    """Build a valid EDGAR filing index URL from the accession number.

    Accession format: XXXXXXXXXX-YY-NNNNNN (first 10 digits = filer CIK, zero-padded).
    Index URL: https://www.sec.gov/Archives/edgar/data/{CIK}/{accessionNoDash}/
    """
    parts = accession.split("-")
    if len(parts) >= 1 and parts[0].isdigit():
        filer_cik = str(int(parts[0]))  # strip leading zeros
        accession_nodash = accession.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{filer_cik}/{accession_nodash}/"
    return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=8-K"


def _get_session():
    try:
        import requests
        s = requests.Session()
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            s.proxies = {"https": proxy, "http": proxy}
        s.headers.update({
            "User-Agent": "dbz-grc-engine/1.0 (edgar-loader; compliance research matthew@example.com)",
            "Accept": "application/json",
        })
        return s
    except ImportError:
        raise RuntimeError("requests library required: pip install requests")


def _fetch_json(session, url: str, params: dict = None, retries: int = 3) -> dict:
    last_exc = None
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"Request failed after {retries} attempts: {last_exc}")


def search_8k_item105(session, start_date: str, end_date: str = "", max_results: int = 200) -> list:
    """
    Search EDGAR full-text for 8-K filings mentioning Item 1.05.
    Returns list of filing metadata dicts.
    """
    params = {
        "q": '"Item 1.05" OR "1.05 Cybersecurity"',
        "dateRange": "custom",
        "startdt": start_date,
        "forms": "8-K",
        "hits.hits.total.value": "true",
        "_source": "period_of_report,entity_name,file_num,period_of_report,period_of_report,form_type,filed_at,id",
    }
    if end_date:
        params["enddt"] = end_date

    print(f"  Searching EDGAR for 8-K Item 1.05 filings since {start_date}...")
    data = _fetch_json(session, EDGAR_SEARCH_URL, params=params)
    time.sleep(2)

    hits = data.get("hits", {}).get("hits", [])
    total = data.get("hits", {}).get("total", {}).get("value", 0)
    print(f"  Found {total} total filings (fetched {len(hits)})")
    return hits


def classify_incident(source_text: str) -> dict:
    """
    Classify incident type from 8-K text excerpt.
    Returns {incident_type, nist_families, confidence}.
    """
    text_lower = source_text.lower()
    matched = {}
    for keyword, families in _INCIDENT_NIST_MAP.items():
        if keyword in text_lower:
            matched[keyword] = families

    if not matched:
        return {
            "incident_type": "cybersecurity_incident",
            "nist_families": ["IR"],
            "confidence": "low",
        }

    # Most specific match wins (longest keyword)
    best_keyword = max(matched.keys(), key=len)
    all_families = set()
    for fams in matched.values():
        all_families.update(fams)

    incident_type = best_keyword.replace(" ", "_")
    return {
        "incident_type": incident_type,
        "nist_families": sorted(all_families),
        "confidence": "medium" if len(matched) > 1 else "low",
    }


def normalize_hit(hit: dict) -> dict:
    """Normalize an EDGAR search hit to our canonical format."""
    src = hit.get("_source", {})
    accession = hit.get("_id", "")

    # Try to extract disclosure text snippet for classification
    snippet = hit.get("highlight", {}).get("*", [""])[0] if hit.get("highlight") else ""
    classification = classify_incident(snippet or src.get("form_type", ""))

    return {
        "accession_no": accession,
        "company_name": src.get("entity_name") or src.get("company_name") or "",
        "cik": src.get("file_num", "").split("-")[1] if "-" in src.get("file_num", "") else "",
        "form_type": src.get("form_type", "8-K"),
        "filed_at": src.get("filed_at") or src.get("period_of_report") or "",
        "period_of_report": src.get("period_of_report") or "",
        "incident_type": classification["incident_type"],
        "nist_families": classification["nist_families"],
        "classification_confidence": classification["confidence"],
        "text_snippet": snippet[:500] if snippet else "",
        "edgar_url": _build_edgar_url(accession, src.get("file_num", "")),
    }


def load_edgar_disclosures(
    start_date: str = "2023-12-15",
    end_date: str = "",
    dry_run: bool = False,
    output_path: Optional[Path] = None,
    max_results: int = 500,
) -> dict:
    """
    Load SEC EDGAR 8-K Item 1.05 cybersecurity incident disclosures.

    Parameters
    ----------
    start_date  : ISO date string (default: Dec 15 2023, when rule took effect)
    end_date    : ISO date string (default: today)
    dry_run     : Print stats without writing output.
    output_path : Override default output path.
    max_results : Max disclosures to fetch.
    """
    session = _get_session()
    hits = search_8k_item105(session, start_date, end_date, max_results)
    disclosures = [normalize_hit(h) for h in hits]

    # Aggregate stats
    by_type: dict = {}
    by_family: dict = {}
    for d in disclosures:
        itype = d["incident_type"]
        by_type[itype] = by_type.get(itype, 0) + 1
        for fam in d["nist_families"]:
            by_family[fam] = by_family.get(fam, 0) + 1

    # Version anchors for incremental re-runs
    filed_dates = [d["filed_at"] for d in disclosures if d.get("filed_at")]
    last_filed_date = max(filed_dates) if filed_dates else start_date
    accession_nos = [d["accession_no"] for d in disclosures if d.get("accession_no")]
    last_accession = max(accession_nos) if accession_nos else ""

    result = {
        "_source": "SEC EDGAR — 8-K Item 1.05 cybersecurity incident disclosures",
        "_search_url": EDGAR_SEARCH_URL,
        "_start_date": start_date,
        "_end_date": end_date or "today",
        "_last_filed_date": last_filed_date,
        "_last_accession_number": last_accession,
        "_total": len(disclosures),
        "_by_incident_type": dict(sorted(by_type.items(), key=lambda x: -x[1])),
        "_by_nist_family": dict(sorted(by_family.items())),
        "human_review_required": True,
        "disclosures": disclosures,
    }

    if not dry_run:
        out = output_path or OUTPUT_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Saved {len(disclosures)} EDGAR disclosures → {out}")
    else:
        print("  [dry-run] No file written.")

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Load SEC EDGAR 8-K Item 1.05 cyber disclosures")
    parser.add_argument("--start-date", default="2023-12-15", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="", help="End date (YYYY-MM-DD)")
    parser.add_argument("--max-results", type=int, default=500)
    parser.add_argument("--output", help="Override output path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    args = parser.parse_args()

    result = load_edgar_disclosures(
        start_date=args.start_date,
        end_date=args.end_date,
        dry_run=args.dry_run,
        output_path=Path(args.output) if args.output else None,
        max_results=args.max_results,
    )

    if args.format == "json":
        print(json.dumps({k: v for k, v in result.items() if k != "disclosures"}, indent=2))
    else:
        print(f"\nEDGAR 8-K Cyber Disclosure Summary")
        print(f"  Total disclosures:    {result['_total']}")
        print(f"  Date range:           {result['_start_date']} → {result['_end_date']}")
        print(f"  By incident type:     {result['_by_incident_type']}")
        print(f"  By NIST family:       {result['_by_nist_family']}")
        print(f"  Human review needed:  {result['human_review_required']}")


if __name__ == "__main__":
    main()
