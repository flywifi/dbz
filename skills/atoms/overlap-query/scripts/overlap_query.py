"""
overlap-query atom — runtime script.

Computes CCI / sub-part-anchored overlap between two frameworks from grc.db.  The
primary metric is spine-based (shared CCIs or 800-53 sub-parts) with per-control
full/partial/none breakdown; when a pair has no spine path it degrades gracefully
(inferred ER co-occurrence, then a basis="none" zero) — it never raises on a
cross-framework comparison.  Only an unknown framework NAME returns an input error.

Delegates the algorithm to cross-mapping/engine/spine_overlap.py.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent.parent  # scripts/→overlap-query/→atoms/→skills/→dbz
_ENGINE = _REPO_ROOT / "cross-mapping" / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

import spine_overlap  # type: ignore


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
    raise FileNotFoundError("grc.db not found. Run: python3 cross-mapping/engine/build_db.py")


def _open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    return conn


def compute_overlap(
    framework_a: str,
    framework_b: str,
    db_path: Optional[str] = None,
    per_control: bool = False,
    basis: str = "auto",
) -> dict:
    """
    Spine-anchored overlap between two frameworks.  Returns the full result object
    (never raises on cross-framework); `overlap_pct` is None only when a framework
    NAME cannot be resolved.  Always carries `human_review_required: true`.
    """
    db = _find_db(db_path)
    conn = _open_db(db)
    try:
        return spine_overlap.compute(conn, framework_a, framework_b,
                                     want_per_control=per_control, basis_pref=basis)
    finally:
        conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CCI / sub-part-anchored overlap between two frameworks")
    parser.add_argument("--framework-a", "-a", required=True, help='First framework (e.g. "SOC 2")')
    parser.add_argument("--framework-b", "-b", required=True, help="Second framework")
    parser.add_argument("--db", help="Path to grc.db")
    parser.add_argument("--per-control", action="store_true", help="Include per-control breakdown")
    parser.add_argument("--basis", choices=["auto", "cci", "subpart", "control"], default="auto")
    parser.add_argument("--format", choices=["json", "summary"], default="json")
    args = parser.parse_args()

    result = compute_overlap(
        framework_a=args.framework_a, framework_b=args.framework_b,
        db_path=args.db, per_control=args.per_control, basis=args.basis,
    )

    if args.format == "summary":
        if result.get("overlap_pct") is None:
            print(f"Input error: {result.get('error')}")
            print("Known frameworks:", ", ".join(result.get("known_frameworks", [])[:20]))
            return
        print(f"Framework A: {result['framework_a']}")
        print(f"Framework B: {result['framework_b']}")
        print(f"Basis:       {result['basis']}  (provenance: {result.get('provenance')})")
        print(f"Overlap:     {result['overlap_pct']}%  (A covers B {result.get('a_covers_b_pct')}%, "
              f"B covers A {result.get('b_covers_a_pct')}%)")
        print(f"Confidence:  {result.get('confidence')}  needs_confirmation={result.get('needs_confirmation')}")
        for c in result.get("caveats", []):
            print(f"  ! {c}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
