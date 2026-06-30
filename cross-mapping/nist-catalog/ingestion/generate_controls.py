#!/usr/bin/env python3
"""
NIST 800-53 catalog generator — enriched handoff contract.

Assembles per-control JSON records by joining:
  1. Catalog text (r5.0 preferred, r5.1.1 fallback)
  2. FedRAMP baselines (from 800-53B)
  3. CCI mappings (DISA CCI → r4 → r5 bridge)
  4. ISO 27001 STRM OLIR mapping
  5. CMMC / 800-171 crosswalk
  6. HITRUST CSF v11.4 cross-reference (inverted)

Each control record is a self-contained handoff contract usable across:
  - Assessment / audit workflows (CCIs, parameters, discussion)
  - FedRAMP authorization packages (baselines, impact levels)
  - Gap analysis (unified_mappings, compliance_scope)
  - Sales / CS overlap ("shared audit work %")
  - Compliance mapping (all cross-framework relationships unified)

Output: one JSON file per family + a combined master file.

Usage:
    python generate_controls.py [--family AC] [--out-dir output/]
    python generate_controls.py --family AC --skip-cci --skip-crosswalks  # fast dev
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

SCHEMA_VERSION = "1.1.0"
CATALOG_SOURCE = "NIST 800-53 Rev 5.0"

# ── Assignment/Selection parameter extraction ──────────────────────────────────

_PARAM_RE = re.compile(
    r"\[(Assignment|Selection(?:\s+\(one or more\))?|Selection):\s*([^\]]+)\]",
    re.IGNORECASE,
)


def _extract_parameters(text: str) -> List[dict]:
    """
    Extract [Assignment: ...] and [Selection: ...] blocks from control text.
    Returns list of {type, label, position} dicts.
    """
    params = []
    for i, m in enumerate(_PARAM_RE.finditer(text or ""), start=1):
        param_type = "assignment" if "assignment" in m.group(1).lower() else "selection"
        params.append({
            "id": f"param-{i}",
            "type": param_type,
            "label": m.group(2).strip(),
            "position": m.start(),
        })
    return params


# ── Unified cross-framework mapping record ─────────────────────────────────────

def _build_unified_mappings(
    ctrl_id: str,
    cci_ids: List[str],
    iso_records: List[dict],
    cmmc_records: List[dict],
    hitrust_ids: List[str],
) -> List[dict]:
    """
    Consolidate all cross-framework mappings into a single typed list.

    Each record:
      framework         : canonical framework name
      framework_version : version string (when known)
      control_id        : native ID in the target framework
      relationship_type : "Subset" | "Superset" | "Equal" | "Intersecting" | "mapped_to"
      strength          : "High" | "Medium" | "Low" | "" (when available)
      direction         : "NIST→{framework}" or "{framework}→NIST"
      mapping_source    : provenance of the mapping
      notes             : freeform metadata
    """
    unified: List[dict] = []

    for cci in cci_ids:
        unified.append({
            "framework": "DISA CCI",
            "framework_version": "Rev 5",
            "control_id": cci,
            "relationship_type": "mapped_to",
            "strength": "",
            "direction": f"NIST→DISA CCI",
            "mapping_source": "DISA CCI List Rev 5 + NIST r4→r5 bridge",
            "notes": "",
        })

    for rec in iso_records:
        unified.append({
            "framework": "ISO/IEC 27001:2022",
            "framework_version": "2022",
            "control_id": rec.get("iso_id", ""),
            "relationship_type": rec.get("relationship_type", "") or "mapped_to",
            "strength": rec.get("strength", ""),
            "direction": "NIST→ISO 27001",
            "mapping_source": "NIST OLIR STRM (sp800-53r5-to-iso-27001-mapping-2022)",
            "notes": rec.get("fulfilled_by", ""),
        })

    for rec in cmmc_records:
        # Derive 800-171 control ID from CMMC practice: "AC.L1-3.1.1(a.)" → "3.1.1"
        practice = rec.get("cmmc_practice", "")
        nist171_ref = re.search(r"(\d+\.\d+\.\d+)", practice)
        nist171_id = nist171_ref.group(1) if nist171_ref else ""
        rel_strength = rec.get("relationship_strength", "")
        unified.append({
            "framework": "CMMC 2.0 / NIST 800-171",
            "framework_version": "800-171 Rev 2 (CMMC 2.0)",
            "control_id": practice,
            "relationship_type": "mapped_to",
            "strength": rel_strength,
            "direction": "NIST→CMMC",
            "mapping_source": "NIST CMMC/800-171/800-53 Crosswalk",
            "notes": rec.get("nist_171a_objective", ""),
        })
        if nist171_id:
            unified.append({
                "framework": "NIST SP 800-171",
                "framework_version": "Rev 2",
                "control_id": f"3.{nist171_id}" if not nist171_id.startswith("3.") else nist171_id,
                "relationship_type": "mapped_to",
                "strength": "",
                "direction": "NIST→800-171",
                "mapping_source": "NIST CMMC/800-171/800-53 Crosswalk (derived)",
                "notes": "",
            })

    for hitrust_id in hitrust_ids:
        unified.append({
            "framework": "HITRUST CSF",
            "framework_version": "v11.4.0",
            "control_id": hitrust_id,
            "relationship_type": "mapped_to",
            "strength": "",
            "direction": "NIST→HITRUST",
            "mapping_source": "HITRUST CSF v11.4 Authoritative Sources Cross-Reference (March 2025)",
            "notes": "",
        })

    return unified


def _compliance_scope(baselines: dict, unified_mappings: List[dict]) -> dict:
    """
    Summary of which compliance frameworks / tiers this control applies to.
    Used by the sales/CS overlap engine for quick filtering.
    """
    frameworks = sorted({m["framework"] for m in unified_mappings if m["control_id"]})
    fedramp_levels = [lvl for lvl in ("low", "moderate", "high")
                      if baselines.get(lvl)]
    return {
        "fedramp_levels": fedramp_levels,
        "privacy_baseline": bool(baselines.get("privacy")),
        "mapped_frameworks": frameworks,
        "framework_count": len(frameworks),
    }


# ── lazy loaders ───────────────────────────────────────────────────────────────

def _load_catalog(family: Optional[str]):
    from load_catalog import load_catalog
    return load_catalog(family_filter=family)


def _load_cci_index():
    from load_cci import build_nist_to_cci_index
    return build_nist_to_cci_index()


def _load_iso():
    from load_crosswalks import load_iso_27001_mapping
    return load_iso_27001_mapping()


def _load_cmmc():
    from load_crosswalks import load_cmmc_mapping
    return load_cmmc_mapping()


def _load_hitrust():
    from load_crosswalks import load_hitrust_mapping
    return load_hitrust_mapping()


# ── assembly ───────────────────────────────────────────────────────────────────

def assemble_control(
    ctrl_id: str,
    catalog_record: dict,
    cci_idx: dict,
    iso_map: dict,
    cmmc_map: dict,
    hitrust_map: dict,
    generated_at: str = "",
) -> dict:
    """
    Build the full enriched handoff-contract record for one base control.

    Schema version: SCHEMA_VERSION
    Handoff scenarios supported:
      - assessment   : parameters, discussion, mapped_ccis, text
      - fedramp      : baselines, compliance_scope.fedramp_levels
      - gap_analysis : unified_mappings, compliance_scope.mapped_frameworks
      - sales_cs     : compliance_scope, unified_mappings (framework coverage)
      - audit        : mapped_ccis, parameters, text, discussion
    """
    text       = catalog_record.get("text", "")
    discussion = catalog_record.get("discussion", "")
    baselines  = catalog_record.get("baselines", {})

    cci_ids     = cci_idx.get(ctrl_id, [])
    iso_records = iso_map.get(ctrl_id, [])
    cmmc_records = cmmc_map.get(ctrl_id, [])
    hitrust_ids  = hitrust_map.get(ctrl_id, [])

    unified = _build_unified_mappings(ctrl_id, cci_ids, iso_records, cmmc_records, hitrust_ids)

    record = {
        # ── Identity ──────────────────────────────────────────────────────
        "schema_version": SCHEMA_VERSION,
        "catalog_source": CATALOG_SOURCE,
        "generated_at": generated_at,
        "id": ctrl_id,
        "family": catalog_record.get("family", ""),
        "title": catalog_record.get("title", ""),

        # ── Content ───────────────────────────────────────────────────────
        "text": text,
        "discussion": discussion,
        "related_controls": catalog_record.get("related_controls", ""),

        # ── Parameters (Assignment/Selection blocks in control text) ──────
        # Critical for FedRAMP SSP and assessment-objective mapping
        "parameters": _extract_parameters(text),

        # ── FedRAMP / 800-53B Baselines ───────────────────────────────────
        "baselines": baselines,

        # ── Compliance scope summary (fast filter for overlap engine) ──────
        "compliance_scope": _compliance_scope(baselines, unified),

        # ── Enhancements (populated below) ────────────────────────────────
        "enhancements": [],

        # ── DISA CCI mappings (assessment / STIG scenario) ────────────────
        "mapped_ccis": cci_ids,

        # ── Per-framework crosswalk records (legacy, kept for compat) ─────
        "iso_27001_mappings": iso_records,
        "cmmc_mappings": cmmc_map.get(ctrl_id, []),
        "hitrust_mappings": hitrust_ids,

        # ── Unified cross-framework mapping (all scenarios) ────────────────
        # This is the primary handoff field. All downstream engines should
        # read from here, not the per-framework lists above.
        "unified_mappings": unified,
    }

    for enh in catalog_record.get("enhancements", []):
        enh_id = enh["id"]
        enh_text = enh.get("text", "")
        enh_cci    = cci_idx.get(enh_id, [])
        enh_iso    = iso_map.get(enh_id, [])
        enh_cmmc   = cmmc_map.get(enh_id, [])
        enh_hitrust = hitrust_map.get(enh_id, [])
        enh_unified = _build_unified_mappings(
            enh_id, enh_cci, enh_iso, enh_cmmc, enh_hitrust
        )
        enh_baselines = enh.get("baselines", {})

        record["enhancements"].append({
            "schema_version": SCHEMA_VERSION,
            "id": enh_id,
            "title": enh.get("title", ""),
            "text": enh_text,
            "discussion": enh.get("discussion", ""),
            "parameters": _extract_parameters(enh_text),
            "baselines": enh_baselines,
            "compliance_scope": _compliance_scope(enh_baselines, enh_unified),
            "mapped_ccis": enh_cci,
            "iso_27001_mappings": enh_iso,
            "cmmc_mappings": enh_cmmc,
            "hitrust_mappings": enh_hitrust,
            "unified_mappings": enh_unified,
        })

    return record


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate NIST 800-53 enriched control catalog")
    parser.add_argument("--family", "-f", default=None,
                        help="Only generate controls for this family (e.g. AC). "
                             "Omit for all families.")
    parser.add_argument("--out-dir", "-o",
                        default=str(_HERE.parent / "output"),
                        help="Output directory (default: nist-catalog/output/)")
    parser.add_argument("--skip-cci", action="store_true",
                        help="Skip CCI mapping (faster, for development)")
    parser.add_argument("--skip-crosswalks", action="store_true",
                        help="Skip ISO/CMMC/HITRUST crosswalks (faster, for development)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()

    print(f"[*] Loading catalog{' (family: ' + args.family + ')' if args.family else ''} …")
    catalog = _load_catalog(args.family)
    print(f"    {len(catalog)} base controls loaded")

    cci_idx    = {}
    iso_map    = {}
    cmmc_map   = {}
    hitrust_map = {}

    if not args.skip_cci:
        print("[*] Loading CCI index …")
        try:
            cci_idx = _load_cci_index()
            print(f"    {len(cci_idx)} NIST IDs with CCI mappings")
        except FileNotFoundError as e:
            print(f"    [warn] {e} — CCI mappings will be empty")

    if not args.skip_crosswalks:
        print("[*] Loading ISO 27001 STRM mapping …")
        try:
            iso_map = _load_iso()
            print(f"    {len(iso_map)} NIST IDs with ISO 27001 mappings")
        except FileNotFoundError as e:
            print(f"    [warn] {e} — ISO 27001 mappings will be empty")

        print("[*] Loading CMMC / 800-171 crosswalk …")
        try:
            cmmc_map = _load_cmmc()
            print(f"    {len(cmmc_map)} NIST IDs with CMMC mappings")
        except FileNotFoundError as e:
            print(f"    [warn] {e} — CMMC mappings will be empty")

        print("[*] Loading HITRUST cross-reference …")
        try:
            hitrust_map = _load_hitrust()
            print(f"    {len(hitrust_map)} NIST IDs with HITRUST mappings")
        except Exception as e:
            print(f"    [warn] {e} — HITRUST mappings will be empty")

    print("[*] Assembling output …")
    output: dict = {}
    for ctrl_id, catalog_record in catalog.items():
        output[ctrl_id] = assemble_control(
            ctrl_id, catalog_record, cci_idx, iso_map, cmmc_map, hitrust_map,
            generated_at=generated_at,
        )

    if args.family:
        out_file = out_dir / f"NIST_800_53_{args.family}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"[✓] Written: {out_file}  ({len(output)} controls)")
    else:
        by_family: dict = {}
        for ctrl_id, record in output.items():
            fam = record.get("family", "UNKNOWN")
            by_family.setdefault(fam, {})[ctrl_id] = record

        for fam, fam_controls in sorted(by_family.items()):
            out_file = out_dir / f"NIST_800_53_{fam}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(fam_controls, f, indent=2, ensure_ascii=False)
            print(f"    Written: {out_file}  ({len(fam_controls)} controls)")

        master_file = out_dir / "NIST_800_53_FULL_ALL_FAMILIES.json"
        with open(master_file, "w", encoding="utf-8") as f:
            json.dump(by_family, f, indent=2, ensure_ascii=False)
        print(f"[✓] Master written: {master_file}")


if __name__ == "__main__":
    main()
