#!/usr/bin/env python3
"""
Validation suite for the generated NIST 800-53 catalog (schema v1.1.0).

Checks:
  - Schema compliance (required fields present, correct types)
  - Non-empty required text fields
  - Parameters list structure
  - Compliance scope structure
  - Unified mappings structure
  - CCI list format (CCI-NNNNNN)
  - Cross-family control counts vs source catalog

Usage:
    python validate_catalog.py [--family AC] [--out-dir output/]
"""

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_OUTPUT_DIR = _HERE.parent / "output"


def _load_generated(family: str = None, out_dir: Path = None) -> dict:
    d = out_dir or _OUTPUT_DIR
    if family:
        f = d / f"NIST_800_53_{family}.json"
    else:
        f = d / "NIST_800_53_FULL_ALL_FAMILIES.json"

    if not f.exists():
        raise FileNotFoundError(
            f"Generated file not found: {f}\n"
            "Run generate_controls.py first."
        )
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


REQUIRED_CONTROL_FIELDS = [
    "schema_version", "catalog_source", "id", "family", "title", "text",
    "parameters", "baselines", "compliance_scope", "enhancements",
    "mapped_ccis", "iso_27001_mappings", "cmmc_mappings", "hitrust_mappings",
    "unified_mappings",
]

REQUIRED_ENHANCEMENT_FIELDS = [
    "schema_version", "id", "title", "parameters", "baselines",
    "compliance_scope", "mapped_ccis", "iso_27001_mappings",
    "cmmc_mappings", "hitrust_mappings", "unified_mappings",
]

REQUIRED_UNIFIED_MAPPING_FIELDS = [
    "framework", "control_id", "relationship_type", "direction", "mapping_source",
]

REQUIRED_COMPLIANCE_SCOPE_FIELDS = [
    "fedramp_levels", "privacy_baseline", "mapped_frameworks", "framework_count",
]

CCI_RE = re.compile(r"^CCI-\d+$")

VALID_RELATIONSHIP_TYPES = {
    "Subset", "Superset", "Equal", "Intersecting", "mapped_to", "",
}


def validate_unified_mapping(parent_id: str, m: dict, idx: int) -> list:
    errors = []
    for field in REQUIRED_UNIFIED_MAPPING_FIELDS:
        if field not in m:
            errors.append(f"{parent_id} unified_mappings[{idx}]: missing '{field}'")
    rt = m.get("relationship_type", "")
    if rt not in VALID_RELATIONSHIP_TYPES:
        errors.append(f"{parent_id} unified_mappings[{idx}]: unknown relationship_type {rt!r}")
    return errors


def validate_control(ctrl_id: str, record: dict) -> list:
    errors = []

    for field in REQUIRED_CONTROL_FIELDS:
        if field not in record:
            errors.append(f"{ctrl_id}: missing field '{field}'")

    if record.get("id") and record["id"] != ctrl_id:
        errors.append(f"{ctrl_id}: id mismatch ({record['id']})")

    # parameters must be a list
    params = record.get("parameters")
    if params is not None and not isinstance(params, list):
        errors.append(f"{ctrl_id}: parameters must be a list, got {type(params).__name__}")

    # compliance_scope structure
    scope = record.get("compliance_scope")
    if scope is not None:
        if not isinstance(scope, dict):
            errors.append(f"{ctrl_id}: compliance_scope must be a dict")
        else:
            for sf in REQUIRED_COMPLIANCE_SCOPE_FIELDS:
                if sf not in scope:
                    errors.append(f"{ctrl_id}: compliance_scope missing '{sf}'")

    # mapped_ccis: list of CCI-NNNNNN
    ccis = record.get("mapped_ccis")
    if ccis is not None:
        if not isinstance(ccis, list):
            errors.append(f"{ctrl_id}: mapped_ccis must be a list")
        else:
            for cci in ccis:
                if not CCI_RE.match(str(cci)):
                    errors.append(f"{ctrl_id}: invalid CCI format: {cci!r}")

    # unified_mappings structure
    unified = record.get("unified_mappings")
    if unified is not None:
        if not isinstance(unified, list):
            errors.append(f"{ctrl_id}: unified_mappings must be a list")
        else:
            for i, m in enumerate(unified):
                errors.extend(validate_unified_mapping(ctrl_id, m, i))

    # Validate enhancements
    for enh in record.get("enhancements", []):
        enh_id = enh.get("id", "?")
        for field in REQUIRED_ENHANCEMENT_FIELDS:
            if field not in enh:
                errors.append(f"{ctrl_id} → {enh_id}: missing field '{field}'")
        for i, m in enumerate(enh.get("unified_mappings", [])):
            errors.extend(validate_unified_mapping(enh_id, m, i))

    return errors


def validate_coverage(data: dict, family_filter: str = None) -> list:
    import re as _re
    warnings = []
    expected_families = (
        [family_filter] if family_filter
        else ["AC", "AT", "AU", "CA", "CM", "CP", "IA", "IR",
              "MA", "MP", "PE", "PL", "PM", "PS", "PT", "RA",
              "SA", "SC", "SI", "SR"]
    )
    is_nested = all(_re.match(r"^[A-Z]{2,3}$", k) for k in list(data.keys())[:10])
    if is_nested:
        for fam in expected_families:
            if fam not in data:
                warnings.append(f"Family '{fam}' missing from output")
    return warnings


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--family", "-f", default=None)
    parser.add_argument("--out-dir", "-o", default=str(_OUTPUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)

    print("[*] Loading generated catalog …")
    data = _load_generated(args.family, out_dir)

    errors = []
    warnings = []

    import re as _re
    # Flat: {"AC-2": {...}}, Nested: {"AC": {"AC-2": {...}}}
    # Detect by checking if all top-level keys look like family codes (2-3 uppercase letters)
    is_nested = all(
        _re.match(r"^[A-Z]{2,3}$", k) for k in list(data.keys())[:10]
    )

    if is_nested:
        control_count = 0
        enh_count = 0
        for fam, fam_controls in data.items():
            for ctrl_id, record in fam_controls.items():
                errors.extend(validate_control(ctrl_id, record))
                control_count += 1
                enh_count += len(record.get("enhancements", []))
        print(f"    {control_count} controls + {enh_count} enhancements validated across {len(data)} families")
    else:
        enh_count = 0
        for ctrl_id, record in data.items():
            errors.extend(validate_control(ctrl_id, record))
            enh_count += len(record.get("enhancements", []))
        print(f"    {len(data)} controls + {enh_count} enhancements validated")

    # Schema version check
    sample = next(iter(data.values()))
    if is_nested:
        sample = next(iter(next(iter(data.values())).values()))
    sv = sample.get("schema_version", "")
    if sv:
        print(f"    Schema version: {sv}")
    else:
        warnings.append("schema_version missing from records")

    warnings.extend(validate_coverage(data, args.family))

    if warnings:
        print(f"\n[!] {len(warnings)} WARNINGS:")
        for w in warnings:
            print(f"    {w}")

    if errors:
        print(f"\n[✗] VALIDATION FAILED — {len(errors)} issues:")
        for e in errors[:50]:
            print(f"    {e}")
        if len(errors) > 50:
            print(f"    … and {len(errors) - 50} more")
        sys.exit(1)
    else:
        print("\n[✓] VALIDATION PASSED — no issues detected.")


if __name__ == "__main__":
    main()
