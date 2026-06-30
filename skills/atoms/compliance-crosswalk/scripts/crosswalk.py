"""
compliance-crosswalk atom — runtime script.

Reads the enriched NIST catalog JSON and returns mapping records
for a given source control and set of target frameworks.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


FRAMEWORK_ALIASES: Dict[str, str] = {
    "iso 27001": "ISO/IEC 27001:2022",
    "iso27001": "ISO/IEC 27001:2022",
    "iso/iec 27001": "ISO/IEC 27001:2022",
    "cmmc": "CMMC 2.0 / NIST 800-171",
    "800-171": "NIST SP 800-171",
    "nist 800-171": "NIST SP 800-171",
    "hitrust": "HITRUST CSF",
    "cci": "DISA CCI",
    "disa cci": "DISA CCI",
}


def _canonical_framework(name: str) -> str:
    return FRAMEWORK_ALIASES.get(name.lower().strip(), name.strip())


def crosswalk_control(
    source_control_id: str,
    catalog_path: Path,
    target_frameworks: Optional[List[str]] = None,
    include_enhancements: bool = False,
) -> dict:
    """
    Return crosswalk records for `source_control_id` from the enriched catalog.

    Parameters
    ----------
    source_control_id  : e.g. "AC-2"
    catalog_path       : path to NIST_800_53_AC.json (or FULL)
    target_frameworks  : list of framework names to filter; None = all
    include_enhancements: if True, also return enhancement mappings
    """
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    # Handle nested (family → controls) or flat (controls) structure
    if source_control_id in catalog:
        record = catalog[source_control_id]
    else:
        # Try nested
        family = source_control_id.split("-")[0]
        family_data = catalog.get(family, {})
        record = family_data.get(source_control_id)

    if record is None:
        return {
            "tool": "compliance-crosswalk",
            "error": f"Control '{source_control_id}' not found in catalog",
            "human_review_required": True,
        }

    unified = record.get("unified_mappings", [])
    baselines = record.get("baselines", {})
    scope = record.get("compliance_scope", {})

    # Normalize target framework names
    targets_canonical = (
        [_canonical_framework(f) for f in target_frameworks]
        if target_frameworks else None
    )

    # Filter mappings
    mappings = []
    gaps = []
    seen_frameworks = set()

    for m in unified:
        fw = m.get("framework", "")
        seen_frameworks.add(fw)
        if targets_canonical is None or fw in targets_canonical:
            mappings.append({
                **m,
                "confidence": "high" if m.get("mapping_source") else "medium",
            })

    if targets_canonical:
        for fw in targets_canonical:
            if fw not in seen_frameworks:
                gaps.append({
                    "target_framework": fw,
                    "reason": (
                        "No direct NIST mapping in catalog. "
                        "For commercial frameworks (SOC 2, HIPAA) use ER crosswalk."
                    ),
                })

    result = {
        "tool": "compliance-crosswalk",
        "schema_version": record.get("schema_version", ""),
        "source_control": {
            "id": source_control_id,
            "framework": "NIST 800-53 Rev 5",
            "title": record.get("title", ""),
            "family": record.get("family", ""),
            "fedramp_levels": scope.get("fedramp_levels", []),
            "privacy_baseline": scope.get("privacy_baseline", False),
        },
        "mappings": mappings,
        "gaps": gaps,
        "human_review_required": True,
    }

    if include_enhancements:
        enh_results = []
        for enh in record.get("enhancements", []):
            enh_unified = enh.get("unified_mappings", [])
            enh_mappings = [
                m for m in enh_unified
                if targets_canonical is None or m.get("framework", "") in targets_canonical
            ]
            if enh_mappings:
                enh_results.append({
                    "enhancement_id": enh.get("id", ""),
                    "title": enh.get("title", ""),
                    "mappings": enh_mappings,
                })
        result["enhancement_mappings"] = enh_results

    return result


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Compliance crosswalk for a NIST control")
    parser.add_argument("control_id", help="NIST control ID (e.g. AC-2)")
    parser.add_argument("--catalog", "-c", required=True, help="Path to catalog JSON")
    parser.add_argument("--target", "-t", nargs="+", help="Target framework names")
    parser.add_argument("--enhancements", "-e", action="store_true")
    args = parser.parse_args()

    result = crosswalk_control(
        source_control_id=args.control_id,
        catalog_path=Path(args.catalog),
        target_frameworks=args.target,
        include_enhancements=args.enhancements,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
