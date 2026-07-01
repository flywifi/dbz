"""
fips_cmvp_loader.py — NIST FIPS 140-3 Cryptographic Module Validation Program loader

Fetches the CMVP validated module list from the NIST CSRC search API and stores
records in canonical-sources/fips-cmvp-validations.json.

Each record: {module_id, vendor, module_name, validation_date, level, status,
              algorithm_capabilities, nist_800_53_controls, cci_provenance, fetched_at}

CMVP API:
  https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules/search

Run:
  python3 cross-mapping/engine/fips_cmvp_loader.py
  python3 cross-mapping/engine/fips_cmvp_loader.py --dry-run
  python3 cross-mapping/engine/fips_cmvp_loader.py --max-results 100
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_PATH = REPO_ROOT / "canonical-sources" / "fips-cmvp-validations.json"

# CMVP search API — returns JSON for Active + Historical validations
CMVP_API_URL = "https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules/search/api"

# Controls that require FIPS-validated cryptography
FIPS_NIST_CONTROLS = ["SC-13", "IA-7", "SC-8(1)", "SC-28(1)"]

# CCI provenance for FIPS 140-3 controls (see plan Part 7 Section 7.10)
FIPS_CCI_PROVENANCE = {
    "SC-13":    "Confirmed-Subject",  # CCI-002450–002453: "FIPS-validated cryptography"
    "IA-7":     "Confirmed-Subject",  # CCI-000803–000804: "cryptographic module authentication"
    "SC-8(1)":  "Confirmed-Subject",  # CCI-002469: "FIPS-validated cryptographic mechanisms"
    "SC-28(1)": "Confirmed-Subject",  # CCI-001199: "cryptographic mechanisms" for storage
    "SC-12":    "Implied-Bridge",     # Key management chain
}


def _fetch(url: str, params: dict | None = None, retries: int = 3) -> dict | list | None:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "dbz-grc-loader/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 405):
                return None
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    return None


def _normalize_status(raw: str) -> str:
    raw = (raw or "").lower()
    if "active" in raw:
        return "active"
    if "historical" in raw or "retired" in raw:
        return "historical"
    if "revoked" in raw:
        return "revoked"
    return raw or "unknown"


def _parse_module(raw: dict) -> dict:
    """Normalize a raw CMVP API record into the canonical output schema."""
    module_id = str(raw.get("moduleId") or raw.get("id") or raw.get("certNum") or "")
    vendor = raw.get("vendorName") or raw.get("vendor") or ""
    module_name = raw.get("moduleName") or raw.get("name") or ""
    level = raw.get("securityLevel") or raw.get("level") or ""
    status = _normalize_status(raw.get("status") or raw.get("validationStatus") or "")
    validation_date = (raw.get("validationDate") or raw.get("certDate")
                       or raw.get("submissionDate") or "")

    # Algorithm capabilities may be a list or a semicolon-delimited string
    algs = raw.get("algorithmCapabilities") or raw.get("algorithms") or []
    if isinstance(algs, str):
        algs = [a.strip() for a in algs.split(";") if a.strip()]

    return {
        "module_id": module_id,
        "vendor": vendor,
        "module_name": module_name,
        "validation_date": str(validation_date),
        "level": str(level),
        "status": status,
        "algorithm_capabilities": json.dumps(algs),
        "nist_800_53_controls": json.dumps(FIPS_NIST_CONTROLS),
        "cci_provenance": json.dumps(FIPS_CCI_PROVENANCE),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_modules(max_results: int = 500, dry_run: bool = False) -> list[dict]:
    """Fetch validated modules from the CMVP API."""
    print("Fetching FIPS 140-3 CMVP validated modules …")

    # Try paginated API
    modules = []
    page = 1
    page_size = 100

    while len(modules) < max_results:
        params = {
            "status": "Active,Historical",
            "standard": "FIPS 140-3,FIPS 140-2",
            "page": page,
            "pageSize": min(page_size, max_results - len(modules)),
        }
        data = _fetch(CMVP_API_URL, params)

        if not data:
            if page == 1:
                print("  CMVP API unavailable — no records fetched", file=sys.stderr)
            break

        # Response may be a list or {modules: [...], total: N}
        if isinstance(data, list):
            batch = data
        elif isinstance(data, dict):
            batch = (data.get("modules") or data.get("data") or data.get("results") or [])
        else:
            break

        if not batch:
            break

        for raw in batch:
            modules.append(_parse_module(raw))

        print(f"  Page {page}: {len(batch)} modules (total so far: {len(modules)})")

        if len(batch) < page_size:
            break  # last page
        page += 1

    if not modules:
        print("  No modules retrieved — output will be empty stub", file=sys.stderr)

    return modules


def run(max_results: int = 500, dry_run: bool = False) -> None:
    modules = fetch_modules(max_results=max_results, dry_run=dry_run)

    output = {
        "_source": "NIST FIPS 140-3 / FIPS 140-2 Cryptographic Module Validation Program (CMVP)",
        "_cmvp_url": CMVP_API_URL,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_module_count": len(modules),
        "_nist_800_53_controls": FIPS_NIST_CONTROLS,
        "_cci_provenance_note": (
            "SC-13/IA-7/SC-8(1)/SC-28(1): Confirmed-Subject (FIPS-validated cryptography language "
            "in CCI text predates FIPS 140-3 transition; applies to both 140-2 and 140-3). "
            "SC-12: Implied-Bridge via key management chain."
        ),
        "modules": modules,
    }

    if dry_run:
        print(f"\n[dry-run] Would write {len(modules)} CMVP modules to {OUTPUT_PATH.name}")
        if modules:
            m = modules[0]
            print(f"  Sample: {m['module_id']} — {m['vendor']} {m['module_name']} (Level {m['level']})")
        else:
            print("  No modules retrieved (API may be unavailable in this environment)")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(modules)} CMVP modules → {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch NIST FIPS CMVP validated module list")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--max-results", type=int, default=500,
                        help="Maximum number of modules to fetch (default: 500)")
    args = parser.parse_args()
    run(max_results=args.max_results, dry_run=args.dry_run)
