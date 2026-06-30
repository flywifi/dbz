"""
cci_trackr_loader.py — CCI Trackr public REST API loader.

Fetches all 3,551 DISA CCIs with their NIST 800-53 mappings from the public
CCI Trackr API (https://cyber.trackr.live/cci). No CAC or SAML authentication
required. Replaces the SAML-gated DISA portal for programmatic CCI access.

Output: canonical-sources/disa-cci-trackr.json
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent

CCI_TRACKR_BASE = "https://cyber.trackr.live/cci"
OUTPUT_PATH = _REPO_ROOT / "canonical-sources" / "disa-cci-trackr.json"


def _get_session():
    try:
        import requests
        s = requests.Session()
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            s.proxies = {"https": proxy, "http": proxy}
        s.headers["User-Agent"] = "dbz-grc-engine/1.0 (cci-trackr-loader; compliance research)"
        return s
    except ImportError:
        raise RuntimeError("requests library required: pip install requests")


def _fetch_with_retry(session, url: str, retries: int = 3, backoff: float = 2.0):
    """Fetch URL with retry on network error."""
    last_exc = None
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                delay = backoff * (2 ** attempt)
                print(f"  Retry {attempt+1}/{retries} after {delay:.0f}s ({exc})", file=sys.stderr)
                time.sleep(delay)
    raise RuntimeError(f"Failed after {retries} attempts: {last_exc}")


def fetch_all_ccis(session) -> list:
    """
    Fetch all CCIs from the CCI Trackr API.
    Returns a list of CCI dicts with NIST 800-53 mappings.
    """
    print("Fetching CCI list from cyber.trackr.live...")
    data = _fetch_with_retry(session, CCI_TRACKR_BASE)

    # API returns either a list or a dict with a 'cci' / 'data' key
    if isinstance(data, list):
        ccis = data
    elif isinstance(data, dict):
        ccis = data.get("cci", data.get("data", data.get("results", [])))
    else:
        raise ValueError(f"Unexpected API response type: {type(data)}")

    print(f"  {len(ccis)} CCIs received.")
    return ccis


def normalize_cci(raw: dict) -> dict:
    """Normalize a raw CCI Trackr entry into our canonical format."""
    cci_id = raw.get("cci_id") or raw.get("id") or raw.get("CCI") or ""
    if not cci_id.startswith("CCI-"):
        cci_id = f"CCI-{cci_id.lstrip('CCI-').zfill(6)}"

    # Extract NIST 800-53 control references
    nist_refs = raw.get("nist_controls") or raw.get("nist_800_53") or raw.get("controls") or []
    if isinstance(nist_refs, str):
        nist_refs = [c.strip() for c in nist_refs.split(",") if c.strip()]

    return {
        "cci_id": cci_id,
        "definition": raw.get("definition") or raw.get("description") or "",
        "status": raw.get("status") or "active",
        "type": raw.get("type") or "",
        "nist_800_53_controls": nist_refs,
        "nist_800_53_rev": raw.get("nist_revision") or "Rev 5",
        "contributor": raw.get("contributor") or "DISA",
        "publishdate": raw.get("publishdate") or raw.get("publish_date") or "",
    }


def load_ccis(dry_run: bool = False, output_path: Optional[Path] = None) -> dict:
    """
    Main loader: fetch, normalize, and (optionally) save all CCIs.

    Parameters
    ----------
    dry_run : If True, prints stats without writing output.
    output_path : Override default output path.
    """
    session = _get_session()
    raw_ccis = fetch_all_ccis(session)
    normalized = [normalize_cci(c) for c in raw_ccis]

    # Stats
    with_nist = sum(1 for c in normalized if c["nist_800_53_controls"])
    print(f"  Normalized: {len(normalized)} CCIs, {with_nist} have NIST 800-53 mappings")

    result = {
        "_source": "CCI Trackr public API",
        "_url": CCI_TRACKR_BASE,
        "_loaded_date": __import__("datetime").date.today().isoformat(),
        "_cci_count": len(normalized),
        "_with_nist_mapping": with_nist,
        "human_review_required": True,
        "ccis": normalized,
    }

    if not dry_run:
        out = output_path or OUTPUT_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Saved {len(normalized)} CCIs → {out}")
    else:
        print("  [dry-run] No file written.")

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Load DISA CCIs from CCI Trackr public API")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--output", help="Override output path")
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    args = parser.parse_args()

    result = load_ccis(dry_run=args.dry_run, output_path=Path(args.output) if args.output else None)

    if args.format == "json":
        print(json.dumps({k: v for k, v in result.items() if k != "ccis"}, indent=2))
    else:
        print(f"\nCCI Trackr Load Summary")
        print(f"  Total CCIs:          {result['_cci_count']}")
        print(f"  With NIST mappings:  {result['_with_nist_mapping']}")
        print(f"  Human review needed: {result['human_review_required']}")


if __name__ == "__main__":
    main()
