"""
generate_controls_800_63b.py — NIST SP 800-63B Digital Identity Authentication loader

Fetches SP 800-63B Rev 3 requirements from the NIST CPRT API and structures them
as {requirement_id, section, aal_level, text, nist_800_53_controls, cci_provenance}.

Output: canonical-sources/nist-800-63b-requirements.json

CPRT API endpoint (SP 800-63B Rev 3):
  https://csrc.nist.gov/extensions/nudp/services/json/nudp/framework/version/sp_800_63b_3/element/ALL/structure/default

Run:
  python3 cross-mapping/nist-catalog/ingestion/generate_controls_800_63b.py
  python3 cross-mapping/nist-catalog/ingestion/generate_controls_800_63b.py --dry-run
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_PATH = REPO_ROOT / "canonical-sources" / "nist-800-63b-requirements.json"
CPRT_URL = (
    "https://csrc.nist.gov/extensions/nudp/services/json/nudp/framework/version/"
    "sp_800_63b_3/element/ALL/structure/default"
)



def _fetch(url: str, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                        "User-Agent": "dbz-grc-loader/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
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


def _derive_aal(section: str, text: str) -> str:
    """Infer AAL from section number or requirement text."""
    text_lower = text.lower()
    if "4.1" in section or "aal1" in text_lower:
        return "AAL1"
    if "4.3" in section or "aal3" in text_lower:
        return "AAL3"
    if "4.2" in section or "aal2" in text_lower or "multifactor" in text_lower or "multi-factor" in text_lower:
        return "AAL2"
    return "all"




def _walk_elements(elements: list, section_prefix: str = "") -> list[dict]:
    """Recursively walk CPRT element tree and extract requirements."""
    requirements = []
    for elem in elements:
        section = elem.get("section", "") or section_prefix
        title = elem.get("title", "") or elem.get("name", "")
        text = elem.get("description", "") or elem.get("text", "") or title

        if text and section:
            requirements.append({
                "requirement_id": f"800-63b-{section.replace('.', '-')}",
                "section": section,
                "title": title,
                "aal_level": _derive_aal(section, text),
                "text": text,
                "nist_800_53_controls": [],   # phase 52: no issuer mapping; never guessed
            })

        children = elem.get("elements", []) or elem.get("children", [])
        if children:
            requirements.extend(_walk_elements(children, section))

    return requirements


def fetch_requirements(dry_run: bool = False) -> list[dict]:
    """Fetch SP 800-63B requirements from NIST CPRT API."""
    print(f"Fetching SP 800-63B from CPRT API …")
    data = _fetch(CPRT_URL)

    if not data:
        print("  CPRT API unavailable or returned empty — using section map only", file=sys.stderr)
        return _fallback_requirements()

    # CPRT response structure varies; try common root keys
    elements = (data.get("response", {}).get("elements")
                or data.get("elements")
                or data.get("data", {}).get("elements")
                or [])

    if not elements:
        print("  No elements found in CPRT response — using section map only", file=sys.stderr)
        return _fallback_requirements()

    reqs = _walk_elements(elements)
    print(f"  {len(reqs)} requirements extracted from CPRT")
    return reqs


_FALLBACK_USED = False


def build_output(reqs):
    out = {"_source": "NIST SP 800-63B Rev 3 — Digital Identity Guidelines: Authentication and Lifecycle Management"}
    if _FALLBACK_USED:
        out["_source_note"] = ("Built-in Rev 3 section map: the CPRT endpoint answered nothing (retired), so these rows "
                               "are section titles, not fetched text; no control links. SP 800-63B-4 supersedes Rev 3 "
                               "(regeneration is its own phase).")
    else:
        out["_cprt_url"] = CPRT_URL
        out["_fetched_at"] = datetime.now(timezone.utc).isoformat()
    out.update({"_requirement_count": len(reqs), "_nist_800_53_version": "Rev 5", "requirements": reqs})
    return out


def _fallback_requirements() -> list[dict]:
    """Produce minimal requirements from the built-in section map when the API is unavailable. Phase 52:
    these rows carry NO control links (the old hand-assigned list was a guess, not NIST's mapping)."""
    global _FALLBACK_USED
    _FALLBACK_USED = True
    reqs = []
    section_titles = {
        "4":    "Authenticator Assurance Levels — Overview",
        "4.1":  "Authenticator Assurance Level 1",
        "4.2":  "Authenticator Assurance Level 2",
        "4.3":  "Authenticator Assurance Level 3",
        "5":    "Authenticator Types",
        "5.1":  "Requirements by Authenticator Type",
        "5.1.1": "Memorized Secrets",
        "5.1.2": "Look-Up Secrets",
        "5.1.3": "Out-of-Band Devices",
        "5.1.4": "Single-Factor OTP Devices",
        "5.1.5": "Multi-Factor OTP Devices",
        "5.1.6": "Single-Factor Cryptographic Software",
        "5.1.7": "Single-Factor Cryptographic Devices",
        "5.1.8": "Multi-Factor Cryptographic Software",
        "5.1.9": "Multi-Factor Cryptographic Devices",
        "6":    "Authenticator Lifecycle Management",
        "6.1":  "Authenticator Binding",
        "6.2":  "Loss, Theft, and Unauthorized Duplication",
        "6.3":  "Expiration",
        "7":    "Session Management",
        "7.1":  "Session Bindings",
        "8":    "Threat Resistance",
        "8.2":  "Verifier-Impersonation Resistance",
        "8.3":  "Verifier-Compromise Resistance",
        "9":    "Privacy Requirements",
        "10":   "Usability Considerations",
    }
    for section, title in section_titles.items():
        reqs.append({
            "requirement_id": f"800-63b-{section.replace('.', '-')}",
            "section": section,
            "title": title,
            "aal_level": _derive_aal(section, title),
            "text": title,
            "nist_800_53_controls": [],
        })
    print(f"  {len(reqs)} requirements from fallback section map")
    return reqs


def run(dry_run: bool = False) -> None:
    reqs = fetch_requirements(dry_run)

    output = build_output(reqs)

    if dry_run:
        print(f"\n[dry-run] Would write {len(reqs)} requirements to {OUTPUT_PATH.name}")
        print(f"  Sample: {reqs[0]['requirement_id']} — {reqs[0]['title']}")
        print(f"  Controls: {reqs[0]['nist_800_53_controls']}")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(reqs)} requirements → {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch NIST SP 800-63B requirements from NIST CPRT")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing output file")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
