"""
compliance-crosswalk atom — runtime script.

Queries the grc.db SQLite database for cross-framework mappings for a given
NIST control. Falls back to loading the enriched catalog JSON if the DB is
not available (e.g. first run before build_db.py has been executed).
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent.parent  # scripts/→crosswalk/→atoms/→skills/→dbz


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


def _find_db(override: Optional[str] = None) -> Optional[Path]:
    if override:
        p = Path(override)
        return p if p.exists() else None

    candidates = [_REPO_ROOT / "cross-mapping" / "output" / "grc.db"]
    search = Path.cwd()
    for _ in range(6):
        candidates.append(search / "cross-mapping" / "output" / "grc.db")
        if search.parent == search:
            break
        search = search.parent

    for p in candidates:
        if p.exists():
            return p
    return None


def _open_db(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _crosswalk_from_db(
    control_id: str,
    db_path: Path,
    target_frameworks: Optional[List[str]] = None,
) -> Optional[dict]:
    try:
        conn = _open_db(db_path)
    except Exception:
        return None

    # Look up base control or enhancement
    row = conn.execute(
        "SELECT nist_id, family, title, baseline_low, baseline_moderate, "
        "baseline_high, privacy_baseline FROM controls WHERE nist_id = ?",
        (control_id,),
    ).fetchone()
    is_enhancement = False
    if row is None:
        row = conn.execute(
            "SELECT e.id AS nist_id, c.family, e.title, "
            "e.baseline_low, e.baseline_moderate, e.baseline_high, e.privacy_baseline "
            "FROM enhancements e JOIN controls c ON e.base_id = c.nist_id "
            "WHERE e.id = ?",
            (control_id,),
        ).fetchone()
        is_enhancement = True

    if row is None:
        conn.close()
        return None

    fedramp_levels = []
    if row["baseline_low"]:
        fedramp_levels.append("low")
    if row["baseline_moderate"]:
        fedramp_levels.append("moderate")
    if row["baseline_high"]:
        fedramp_levels.append("high")

    # Fetch mappings
    mapping_rows = conn.execute(
        "SELECT framework, framework_version, target_id, relationship_type, "
        "strength, direction, mapping_source, notes "
        "FROM unified_mappings WHERE control_id = ?",
        (control_id,),
    ).fetchall()
    conn.close()

    targets_canonical = (
        [_canonical_framework(f) for f in target_frameworks]
        if target_frameworks else None
    )

    seen_frameworks: set = set()
    mappings = []
    for m in mapping_rows:
        fw = m["framework"] or ""
        seen_frameworks.add(fw)
        if targets_canonical is None or fw in targets_canonical:
            mappings.append({
                "framework": fw,
                "framework_version": m["framework_version"],
                "control_id": m["target_id"],
                "relationship_type": m["relationship_type"],
                "strength": m["strength"],
                "direction": m["direction"],
                "mapping_source": m["mapping_source"],
                "notes": m["notes"],
                "confidence": "high" if m["mapping_source"] else "medium",
            })

    gaps = []
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

    return {
        "source_control": {
            "id": control_id,
            "framework": "NIST 800-53 Rev 5",
            "title": row["title"] or "",
            "family": row["family"] or "",
            "fedramp_levels": fedramp_levels,
            "privacy_baseline": bool(row["privacy_baseline"]),
            "is_enhancement": is_enhancement,
        },
        "mappings": mappings,
        "gaps": gaps,
        "_source": "grc.db",
    }


def crosswalk_control(
    source_control_id: str,
    catalog_path: Optional[Path] = None,
    target_frameworks: Optional[List[str]] = None,
    include_enhancements: bool = False,
    db_path: Optional[str] = None,
) -> dict:
    """
    Return crosswalk records for `source_control_id`.

    Queries grc.db first; falls back to loading catalog JSON if the DB is absent.

    Parameters
    ----------
    source_control_id  : e.g. "AC-2"
    catalog_path       : path to NIST_800_53_FULL_ALL_FAMILIES.json (fallback)
    target_frameworks  : list of framework names to filter; None = all
    include_enhancements: if True, also return enhancement mappings (JSON fallback only)
    db_path            : explicit path to grc.db (optional; auto-discovered if omitted)
    """
    found_db = _find_db(db_path)

    if found_db:
        db_result = _crosswalk_from_db(source_control_id, found_db, target_frameworks)
        if db_result is not None:
            return {
                "tool": "compliance-crosswalk",
                "schema_version": "3.0",
                **db_result,
                "human_review_required": True,
            }

    # Fallback: load JSON catalog
    if catalog_path is None:
        return {
            "tool": "compliance-crosswalk",
            "error": (
                f"grc.db not found and no --catalog path provided. "
                "Run: python3 cross-mapping/engine/build_db.py"
            ),
            "human_review_required": True,
        }

    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    if source_control_id in catalog:
        record = catalog[source_control_id]
    else:
        family = source_control_id.split("-")[0]
        record = catalog.get(family, {}).get(source_control_id)

    if record is None:
        return {
            "tool": "compliance-crosswalk",
            "error": f"Control '{source_control_id}' not found in catalog",
            "human_review_required": True,
        }

    unified = record.get("unified_mappings", [])
    baselines = record.get("baselines", {})
    scope = record.get("compliance_scope", {})

    targets_canonical = (
        [_canonical_framework(f) for f in target_frameworks]
        if target_frameworks else None
    )

    mappings = []
    gaps = []
    seen_frameworks: set = set()

    for m in unified:
        fw = m.get("framework", "")
        seen_frameworks.add(fw)
        if targets_canonical is None or fw in targets_canonical:
            mappings.append({**m, "confidence": "high" if m.get("mapping_source") else "medium"})

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
        "_source": "catalog_json",
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
    import argparse

    parser = argparse.ArgumentParser(description="Compliance crosswalk for a NIST control")
    parser.add_argument("control_id", help="NIST control ID (e.g. AC-2)")
    parser.add_argument("--catalog", "-c", help="Path to catalog JSON (fallback if DB absent)")
    parser.add_argument("--db", help="Path to grc.db (auto-discovered if omitted)")
    parser.add_argument("--target", "-t", nargs="+", help="Target framework names")
    parser.add_argument("--enhancements", "-e", action="store_true")
    args = parser.parse_args()

    result = crosswalk_control(
        source_control_id=args.control_id,
        catalog_path=Path(args.catalog) if args.catalog else None,
        target_frameworks=args.target,
        include_enhancements=args.enhancements,
        db_path=args.db,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
