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

# NIST 800-53 Rev 5 controls most directly relevant to 800-63B by section topic.
# Source: NIST SP 800-63B Sec 4 (AAL requirements) and Appendix A (strength).
SECTION_CONTROL_MAP = {
    "4":    ["IA-2", "IA-5"],           # AAL overview
    "4.1":  ["IA-2", "IA-2(1)", "IA-5"],  # AAL1
    "4.2":  ["IA-2", "IA-2(1)", "IA-2(2)", "IA-5"],  # AAL2 (MFA required)
    "4.3":  ["IA-2", "IA-2(1)", "IA-2(2)", "IA-5", "SC-8"],  # AAL3 (hardware authenticator)
    "5":    ["IA-5"],                   # Authenticator types
    "5.1":  ["IA-5", "IA-5(1)"],        # Memorized secrets
    "5.1.1": ["IA-5", "IA-5(1)"],       # Memorized secret authenticators
    "5.1.2": ["IA-5"],                  # Look-up secrets
    "5.1.3": ["IA-5", "SC-28"],         # OOB authenticators
    "5.1.4": ["IA-5", "SC-28"],         # Single-factor OTP
    "5.1.5": ["IA-5", "SC-28"],         # Multi-factor OTP
    "5.1.6": ["IA-5", "SC-8"],          # Single-factor crypto software
    "5.1.7": ["IA-5", "SC-12", "SC-8"], # Single-factor crypto device
    "5.1.8": ["IA-5", "SC-12", "SC-8"], # Multi-factor crypto software
    "5.1.9": ["IA-5", "SC-12", "SC-8"], # Multi-factor crypto device
    "6":    ["IA-5", "IA-11"],          # Authenticator lifecycle
    "6.1":  ["IA-5"],                   # Binding at enrollment
    "6.2":  ["IA-5", "SC-28"],          # Lost/stolen authenticators
    "6.3":  ["IA-5"],                   # Authenticator expiration
    "7":    ["IA-2", "IA-11"],          # Session management
    "7.1":  ["IA-11"],                  # Session bindings
    "8":    ["SC-8", "SC-13"],          # Threat resistance
    "8.2":  ["SC-8"],                   # Verifier impersonation resistance
    "8.3":  ["SC-13"],                  # Verifier compromise resistance
    "9":    ["SC-8", "SC-28"],          # Privacy requirements
    "10":   ["IA-5", "SC-28"],          # Usability considerations
}

# CCI provenance per control — see plan Part 7 Section 7.10 for sourcing.
CCI_PROVENANCE_MAP = {
    "IA-2":     "Confirmed-Subject",
    "IA-2(1)":  "Confirmed-Subject",
    "IA-2(2)":  "Confirmed-Subject",
    "IA-2(6)":  "Confirmed-Subject",
    "IA-2(12)": "Confirmed-Direct",
    "IA-5":     "Confirmed-Subject",
    "IA-5(1)":  "Confirmed-Subject",
    "IA-8":     "Confirmed-Direct",
    "IA-8(1)":  "Confirmed-Direct",
    "IA-9":     "Implied-Bridge",
    "IA-11":    "Implied-Bridge",
    "MA-4(6)":  "Implied-Bridge",
    "SC-8":     "Implied-Bridge",
    "SC-12":    "Implied-Bridge",
    "SC-13":    "Confirmed-Subject",
    "SC-28":    "Implied-Bridge",
}


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


def _controls_for_section(section: str) -> list[str]:
    """Return mapped 800-53 controls for this section, checking most-specific prefix first."""
    for prefix_len in range(len(section), 0, -1):
        prefix = section[:prefix_len]
        if prefix in SECTION_CONTROL_MAP:
            return SECTION_CONTROL_MAP[prefix]
    return ["IA-2", "IA-5"]  # default: authentication / authenticator management


def _provenance_for_controls(controls: list[str]) -> str:
    """Return highest-confidence CCI provenance tier across the mapped controls."""
    tier_order = ["Confirmed-Direct", "Confirmed-Subject", "Implied-Bridge", "Implied-Heuristic"]
    best = "Implied-Heuristic"
    for ctrl in controls:
        prov = CCI_PROVENANCE_MAP.get(ctrl, "Implied-Heuristic")
        if tier_order.index(prov) < tier_order.index(best):
            best = prov
    return best


def _walk_elements(elements: list, section_prefix: str = "") -> list[dict]:
    """Recursively walk CPRT element tree and extract requirements."""
    requirements = []
    for elem in elements:
        section = elem.get("section", "") or section_prefix
        title = elem.get("title", "") or elem.get("name", "")
        text = elem.get("description", "") or elem.get("text", "") or title

        if text and section:
            controls = _controls_for_section(section)
            requirements.append({
                "requirement_id": f"800-63b-{section.replace('.', '-')}",
                "section": section,
                "title": title,
                "aal_level": _derive_aal(section, text),
                "text": text,
                "nist_800_53_controls": controls,
                "cci_provenance": _provenance_for_controls(controls),
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


def _fallback_requirements() -> list[dict]:
    """Produce minimal requirements from SECTION_CONTROL_MAP when API is unavailable."""
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
        controls = _controls_for_section(section)
        reqs.append({
            "requirement_id": f"800-63b-{section.replace('.', '-')}",
            "section": section,
            "title": title,
            "aal_level": _derive_aal(section, title),
            "text": title,
            "nist_800_53_controls": controls,
            "cci_provenance": _provenance_for_controls(controls),
        })
    print(f"  {len(reqs)} requirements from fallback section map")
    return reqs


def run(dry_run: bool = False) -> None:
    reqs = fetch_requirements(dry_run)

    output = {
        "_source": "NIST SP 800-63B Rev 3 — Digital Identity Guidelines: Authentication and Lifecycle Management",
        "_cprt_url": CPRT_URL,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_requirement_count": len(reqs),
        "_nist_800_53_version": "Rev 5",
        "requirements": reqs,
    }

    if dry_run:
        print(f"\n[dry-run] Would write {len(reqs)} requirements to {OUTPUT_PATH.name}")
        print(f"  Sample: {reqs[0]['requirement_id']} — {reqs[0]['title']}")
        print(f"  Controls: {reqs[0]['nist_800_53_controls']}")
        print(f"  CCI provenance: {reqs[0]['cci_provenance']}")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nWrote {len(reqs)} requirements → {OUTPUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch NIST SP 800-63B requirements from NIST CPRT")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing output file")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
