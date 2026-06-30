"""
overlap-query atom — runtime script.

Uses grc.db (er_overlap_pairs view + er_mappings table) to compute
the ER-level overlap between two frameworks without loading CSV files.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent.parent  # scripts/→overlap-query/→atoms/→skills/→dbz


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


def _list_er_frameworks(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        "SELECT DISTINCT framework FROM er_mappings ORDER BY framework"
    ).fetchall()
    return [r["framework"] for r in rows]


def _resolve_er_framework(conn: sqlite3.Connection, name: str) -> Optional[str]:
    """Match by exact name first, then substring."""
    row = conn.execute(
        "SELECT DISTINCT framework FROM er_mappings WHERE framework = ? LIMIT 1",
        (name,),
    ).fetchone()
    if row:
        return row["framework"]
    row = conn.execute(
        "SELECT DISTINCT framework FROM er_mappings WHERE framework LIKE ? LIMIT 1",
        (f"%{name}%",),
    ).fetchone()
    return row["framework"] if row else None


def compute_overlap(
    framework_a: str,
    framework_b: str,
    db_path: Optional[str] = None,
    include_er_lists: bool = False,
) -> dict:
    """
    Compute ER-level overlap between two frameworks.

    Parameters
    ----------
    framework_a      : First framework name (e.g. "SOC 2").
    framework_b      : Second framework name (e.g. "ISO 27001/2 (2022)").
    db_path          : Explicit path to grc.db; auto-discovered if omitted.
    include_er_lists : If True, include shared/a_only/b_only ER ID lists in output.
    """
    db = _find_db(db_path)
    conn = _open_db(db)

    resolved_a = _resolve_er_framework(conn, framework_a)
    resolved_b = _resolve_er_framework(conn, framework_b)

    if not resolved_a or not resolved_b:
        known = _list_er_frameworks(conn)
        conn.close()
        missing = []
        if not resolved_a:
            missing.append(framework_a)
        if not resolved_b:
            missing.append(framework_b)
        return {
            "tool": "overlap-query",
            "error": f"Framework(s) not found in ER crosswalk: {missing}",
            "known_er_frameworks": known,
            "human_review_required": True,
        }

    # Total ERs per framework
    count_a = conn.execute(
        "SELECT COUNT(DISTINCT er_id) FROM er_mappings WHERE framework = ?",
        (resolved_a,),
    ).fetchone()[0]
    count_b = conn.execute(
        "SELECT COUNT(DISTINCT er_id) FROM er_mappings WHERE framework = ?",
        (resolved_b,),
    ).fetchone()[0]

    # Shared ERs via er_overlap_pairs (view enforces framework_a < framework_b lexicographically)
    fa, fb = (resolved_a, resolved_b) if resolved_a < resolved_b else (resolved_b, resolved_a)
    shared_rows = conn.execute(
        "SELECT DISTINCT er_id FROM er_overlap_pairs WHERE framework_a = ? AND framework_b = ?",
        (fa, fb),
    ).fetchall()
    shared_er_ids = [r["er_id"] for r in shared_rows]
    shared_count = len(shared_er_ids)

    union_count = count_a + count_b - shared_count
    jaccard = round(shared_count / union_count * 100, 1) if union_count else 0.0
    a_covers_b = round(shared_count / count_b * 100, 1) if count_b else 0.0
    b_covers_a = round(shared_count / count_a * 100, 1) if count_a else 0.0

    incremental_b_pct = round(100.0 - a_covers_b, 1)
    incremental_a_pct = round(100.0 - b_covers_a, 1)

    result: dict = {
        "tool": "overlap-query",
        "framework_a": resolved_a,
        "framework_b": resolved_b,
        "metrics": {
            "framework_a_er_count": count_a,
            "framework_b_er_count": count_b,
            "shared_er_count": shared_count,
            "jaccard_overlap_pct": jaccard,
            "a_covers_b_pct": a_covers_b,
            "b_covers_a_pct": b_covers_a,
        },
        "interpretation": (
            f"{resolved_a} certification covers {a_covers_b}% of {resolved_b} requirements "
            f"at the ER level. Incremental work to add {resolved_b}: "
            f"~{incremental_b_pct}% of ER set ({count_b - shared_count} ERs)."
        ),
        "human_review_required": True,
    }

    if include_er_lists:
        all_a = {r["er_id"] for r in conn.execute(
            "SELECT DISTINCT er_id FROM er_mappings WHERE framework = ?", (resolved_a,)
        ).fetchall()}
        all_b = {r["er_id"] for r in conn.execute(
            "SELECT DISTINCT er_id FROM er_mappings WHERE framework = ?", (resolved_b,)
        ).fetchall()}
        shared_set = set(shared_er_ids)
        result["shared_er_ids"] = sorted(shared_set)
        result["a_only_er_ids"] = sorted(all_a - shared_set)
        result["b_only_er_ids"] = sorted(all_b - shared_set)

    conn.close()
    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ER-level overlap between two frameworks")
    parser.add_argument("--framework-a", "-a", required=True, help='First framework (e.g. "SOC 2")')
    parser.add_argument("--framework-b", "-b", required=True, help="Second framework")
    parser.add_argument("--db", help="Path to grc.db")
    parser.add_argument("--er-lists", action="store_true", help="Include shared/unique ER ID lists")
    parser.add_argument("--format", choices=["json", "summary"], default="json")
    args = parser.parse_args()

    result = compute_overlap(
        framework_a=args.framework_a,
        framework_b=args.framework_b,
        db_path=args.db,
        include_er_lists=args.er_lists,
    )

    if args.format == "summary":
        if "error" in result:
            print(f"Error: {result['error']}")
            if "known_er_frameworks" in result:
                print("Known frameworks:", result["known_er_frameworks"])
        else:
            m = result["metrics"]
            print(f"Framework A: {result['framework_a']}  ({m['framework_a_er_count']} ERs)")
            print(f"Framework B: {result['framework_b']}  ({m['framework_b_er_count']} ERs)")
            print(f"Shared ERs:  {m['shared_er_count']}")
            print(f"Jaccard:     {m['jaccard_overlap_pct']}%")
            print(f"A covers B:  {m['a_covers_b_pct']}%")
            print(f"B covers A:  {m['b_covers_a_pct']}%")
            print(result["interpretation"])
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
