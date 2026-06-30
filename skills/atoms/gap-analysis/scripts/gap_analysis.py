"""
gap-analysis atom — runtime script.

Uses grc.db to identify NIST 800-53 controls that are not covered (or only
partially covered) by a target framework. Avoids loading the 29 MB JSON catalog.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent.parent  # scripts/→gap-analysis/→atoms/→skills/→dbz

FULLY_COVERED = {"Equal", "Subset"}
# mapped_to (direct reference) and transitive_via_hitrust (bridged) count as partial coverage;
# OLIR STRM types (Equal/Subset/Superset/Intersecting) are used when catalog data supports them.
PARTIALLY_COVERED = {"Superset", "Intersecting", "mapped_to", "transitive_via_hitrust"}


def _find_db(override: Optional[str] = None) -> Path:
    if override:
        p = Path(override)
        if p.exists():
            return p
        raise FileNotFoundError(f"DB not found: {override}")

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
    raise FileNotFoundError(
        "grc.db not found. Run: python3 cross-mapping/engine/build_db.py"
    )


def _open_db(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_framework(conn: sqlite3.Connection, name: str) -> str:
    """Return the exact framework string stored in unified_mappings (LIKE match)."""
    row = conn.execute(
        "SELECT DISTINCT framework FROM unified_mappings WHERE framework LIKE ? LIMIT 1",
        (f"%{name}%",),
    ).fetchone()
    return row["framework"] if row else name


def _build_scope_sql(fedramp_level: Optional[str], families: Optional[List[str]]) -> tuple:
    """Return (WHERE_clause, params) for scoping controls."""
    clauses = []
    params: list = []

    if fedramp_level:
        col_map = {"low": "baseline_low", "moderate": "baseline_moderate", "high": "baseline_high"}
        col = col_map.get(fedramp_level.lower())
        if col:
            clauses.append(f"c.{col} = 1")

    if families:
        placeholders = ", ".join("?" * len(families))
        clauses.append(f"c.family IN ({placeholders})")
        params.extend(f.upper() for f in families)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def analyze_gaps(
    target_framework: str,
    fedramp_level: Optional[str] = None,
    families: Optional[List[str]] = None,
    db_path: Optional[str] = None,
) -> dict:
    """
    Identify NIST 800-53 controls that are not covered by target_framework.

    Parameters
    ----------
    target_framework : Framework name (or substring) to check coverage against.
    fedramp_level    : "low", "moderate", or "high" — filters controls by baseline.
    families         : List of control families (e.g. ["AC", "IA"]) to restrict scope.
    db_path          : Explicit path to grc.db; auto-discovered if omitted.
    """
    db = _find_db(db_path)
    conn = _open_db(db)

    resolved_fw = _resolve_framework(conn, target_framework)

    scope_where, scope_params = _build_scope_sql(fedramp_level, families)

    # Left-join controls with their best mapping to target_framework
    sql = f"""
        SELECT c.nist_id, c.family, c.title,
               m.target_id, m.relationship_type, m.strength, m.mapping_source
        FROM controls c
        LEFT JOIN unified_mappings m
               ON m.control_id = c.nist_id AND m.framework = ?
        {scope_where}
        ORDER BY c.nist_id
    """
    rows = conn.execute(sql, [resolved_fw] + scope_params).fetchall()
    conn.close()

    fully_covered = []
    partially_covered = []
    gaps = []

    ctrl_seen: dict = {}  # nist_id → best row (prefer fully_covered > partial > gap)

    for row in rows:
        nid = row["nist_id"]
        rtype = row["relationship_type"] or ""
        existing = ctrl_seen.get(nid)
        priority = (
            2 if rtype in FULLY_COVERED
            else 1 if rtype in PARTIALLY_COVERED
            else 0
        )
        if existing is None or priority > existing["_priority"]:
            ctrl_seen[nid] = {**dict(row), "_priority": priority}

    for nid, row in ctrl_seen.items():
        rtype = row["relationship_type"] or ""
        entry = {
            "source_control_id": nid,
            "source_title": row["title"] or "",
            "family": row["family"] or "",
            "target_equivalents": [row["target_id"]] if row["target_id"] else [],
            "relationship_type": rtype or None,
        }
        if rtype in FULLY_COVERED:
            fully_covered.append(entry)
        elif rtype in PARTIALLY_COVERED:
            entry["gap_type"] = "partially_covered"
            partially_covered.append(entry)
        else:
            entry["gap_type"] = "not_covered"
            entry["target_equivalents"] = []
            gaps.append(entry)

    total = len(ctrl_seen)
    covered_count = len(fully_covered)
    coverage_pct = round(covered_count / total * 100, 1) if total else 0.0

    scope_applied: dict = {}
    if fedramp_level:
        scope_applied["fedramp_level"] = fedramp_level
    if families:
        scope_applied["families"] = families

    return {
        "tool": "gap-analysis",
        "source_framework": "NIST 800-53 Rev 5",
        "target_framework": resolved_fw,
        "scope_applied": scope_applied,
        "coverage_summary": {
            "total_source_controls": total,
            "with_target_mapping": covered_count + len(partially_covered),
            "coverage_pct": coverage_pct,
            "fully_covered": covered_count,
            "partially_covered": len(partially_covered),
            "not_covered": len(gaps),
        },
        "gaps": gaps,
        "partial_coverage": partially_covered,
        "human_review_required": True,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Gap analysis: NIST 800-53 vs target framework")
    parser.add_argument("target_framework", help='Target framework (e.g. "CMMC 2.0 / NIST 800-171")')
    parser.add_argument("--fedramp", "-l", help="FedRAMP baseline: low|moderate|high")
    parser.add_argument("--family", "-F", nargs="+", help="Control families (e.g. AC IA SC)")
    parser.add_argument("--db", help="Path to grc.db")
    parser.add_argument("--format", choices=["json", "summary"], default="json")
    args = parser.parse_args()

    result = analyze_gaps(
        target_framework=args.target_framework,
        fedramp_level=args.fedramp,
        families=args.family,
        db_path=args.db,
    )

    if args.format == "summary":
        s = result["coverage_summary"]
        print(f"Target: {result['target_framework']}")
        print(f"Scope:  {result['scope_applied'] or 'all controls'}")
        print(f"Total controls: {s['total_source_controls']}")
        print(f"Fully covered:  {s['fully_covered']} ({s['coverage_pct']}%)")
        print(f"Partial:        {s['partially_covered']}")
        print(f"Gaps:           {s['not_covered']}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
