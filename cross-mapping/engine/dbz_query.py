#!/usr/bin/env python3
"""
dbz_query.py — GRC Token-Reduction Query CLI

Answers common GRC questions with millisecond SQL lookups instead of loading
the 29 MB JSON catalog (~50k tokens). Opens grc.db immutable read-only.

Usage:
    python3 dbz_query.py reverse --framework "ISO/IEC 27001:2022" --control A.5.16
    python3 dbz_query.py forward --control AC-2 [--frameworks iso cmmc]
    python3 dbz_query.py scope --fedramp moderate [--family IA] [--cui] [--privacy]
    python3 dbz_query.py overlap --framework-a "SOC 2" --framework-b "ISO 27001/2 (2022)"
    python3 dbz_query.py search --keyword "multi-factor" [--scope moderate] [--family IA]
    python3 dbz_query.py changelog [--framework nist-800-53] [--since 2025-01-01]
    python3 dbz_query.py feeds [--framework nist-800-53] [--status changed]
    python3 dbz_query.py announcements [--days 30] [--framework fedramp] [--unreviewed]
    python3 dbz_query.py manifest

DB discovery: walks up from CWD looking for cross-mapping/output/grc.db; or --db PATH.
"""

from __future__ import annotations

import argparse
import csv as csv_module
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional


# ── DB discovery ──────────────────────────────────────────────────────────────

def _find_db(override: Optional[str] = None) -> Path:
    if override:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(f"DB not found: {p}")
        return p
    # Walk up from CWD
    here = Path.cwd()
    for ancestor in [here, *here.parents]:
        candidate = ancestor / "cross-mapping" / "output" / "grc.db"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "grc.db not found. Run: python3 cross-mapping/engine/build_db.py\n"
        "Or pass --db PATH to specify its location."
    )


def _open_db(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── Framework name fuzzy matching ─────────────────────────────────────────────

_FW_ALIASES: dict[str, list[str]] = {
    "iso": ["ISO/IEC 27001:2022", "ISO 27001/2 (2022)", "ISO/IEC 27001"],
    "iso27001": ["ISO/IEC 27001:2022", "ISO 27001/2 (2022)"],
    "cmmc": ["CMMC 2.0 / NIST 800-171", "CMMC"],
    "hitrust": ["HITRUST CSF", "HITRUST e1", "HITRUST"],
    "csf": ["NIST CSF 2.0", "NIST CSF"],
    "nist-csf": ["NIST CSF 2.0", "NIST CSF"],
    "hipaa": ["HIPAA Security", "HIPAA Privacy Rule"],
    "pci": ["PCI DSS v4.0", "PCI DSS"],
    "soc2": ["SOC 2"],
    "soc1": ["SOC 1"],
    "daapm": ["DAAPM Appendix A (DoD DCSA)"],
    "800-171": ["NIST SP 800-171", "NIST SP 800-171 Rev 3", "CMMC 2.0 / NIST 800-171"],
    "iot": ["NIST SP 800-213A (IoT)"],
    "appendix-j": ["NIST SP 800-53 Rev 4 (Appendix J)"],
}


def _resolve_fw(alias: str, conn: sqlite3.Connection) -> list[str]:
    """Resolve a framework alias/shorthand to exact DB framework name(s)."""
    # Exact match in DB first
    row = conn.execute(
        "SELECT DISTINCT framework FROM unified_mappings WHERE framework = ? LIMIT 1",
        (alias,),
    ).fetchone()
    if row:
        return [alias]
    # Try alias map
    candidates = _FW_ALIASES.get(alias.lower(), [])
    found = []
    for c in candidates:
        r = conn.execute(
            "SELECT DISTINCT framework FROM unified_mappings WHERE framework = ? LIMIT 1",
            (c,),
        ).fetchone()
        if r:
            found.append(c)
    if found:
        return found
    # Fuzzy: substring match
    rows = conn.execute(
        "SELECT DISTINCT framework FROM unified_mappings WHERE framework LIKE ? LIMIT 5",
        (f"%{alias}%",),
    ).fetchall()
    return [r[0] for r in rows]


# ── Output formatters ──────────────────────────────────────────────────────────

def _output(rows: list[dict], fmt: str, columns: list[str]) -> None:
    if not rows:
        if fmt == "json":
            print("[]")
        else:
            print("(no results)")
        return

    if fmt == "json":
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    if fmt == "csv":
        writer = csv_module.DictWriter(sys.stdout, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return

    # table (default)
    col_widths = {c: max(len(c), max(len(str(r.get(c, "") or "")) for r in rows)) for c in columns}
    col_widths = {c: min(w, 60) for c, w in col_widths.items()}  # cap at 60
    header = "  ".join(c.ljust(col_widths[c]) for c in columns)
    sep = "  ".join("-" * col_widths[c] for c in columns)
    print(header)
    print(sep)
    for row in rows:
        line = "  ".join(str(row.get(c, "") or "")[:col_widths[c]].ljust(col_widths[c]) for c in columns)
        print(line)
    print(f"\n{len(rows)} row(s)")


# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_reverse(args, conn: sqlite3.Connection) -> int:
    """Reverse lookup: framework control → NIST 800-53 control IDs."""
    frameworks = _resolve_fw(args.framework, conn)
    if not frameworks:
        print(f"[ERROR] Framework not found: {args.framework!r}", file=sys.stderr)
        print("Run: python3 dbz_query.py feeds  to see available frameworks.", file=sys.stderr)
        return 1

    placeholders = ",".join("?" * len(frameworks))
    rows = conn.execute(
        f"""
        SELECT control_id, framework, target_id, relationship_type, strength
        FROM unified_mappings
        WHERE framework IN ({placeholders}) AND target_id = ?
        ORDER BY control_id
        """,
        (*frameworks, args.control),
    ).fetchall()

    results = [dict(r) for r in rows]
    cols = ["control_id", "framework", "target_id", "relationship_type", "strength"]
    _output(results, args.format, cols)
    return 0


def cmd_forward(args, conn: sqlite3.Connection) -> int:
    """Forward mapping: NIST control → cross-framework mappings."""
    ctrl_id = args.control.upper()
    sql = """
        SELECT framework, target_id, relationship_type, strength, direction, mapping_source
        FROM unified_mappings
        WHERE control_id = ?
    """
    params: list = [ctrl_id]

    if args.frameworks:
        resolved: list[str] = []
        for fw in args.frameworks:
            resolved.extend(_resolve_fw(fw, conn))
        if resolved:
            placeholders = ",".join("?" * len(resolved))
            sql += f" AND framework IN ({placeholders})"
            params.extend(resolved)

    sql += " ORDER BY framework, target_id"
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["framework", "target_id", "relationship_type", "strength", "direction", "mapping_source"]
    _output(results, args.format, cols)
    return 0


def cmd_scope(args, conn: sqlite3.Connection) -> int:
    """Scope filter: list controls matching baseline/family/CUI/privacy criteria."""
    conditions = []
    params: list = []

    fedramp_level = getattr(args, "fedramp", None)
    if fedramp_level:
        lv = fedramp_level.lower()
        if lv in ("low", "l"):
            conditions.append("baseline_low = 1")
        elif lv in ("moderate", "mod", "m"):
            conditions.append("baseline_moderate = 1")
        elif lv in ("high", "h"):
            conditions.append("baseline_high = 1")
        else:
            print(f"[ERROR] Unknown FedRAMP level: {fedramp_level!r}. Use low/moderate/high.", file=sys.stderr)
            return 1

    if getattr(args, "privacy", False):
        conditions.append("privacy_baseline = 1")
    if getattr(args, "cui", False):
        conditions.append("cui_applicable = 1")
    if getattr(args, "family", None):
        conditions.append("family = ?")
        params.append(args.family.upper())

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"SELECT nist_id, family, title, baseline_low, baseline_moderate, baseline_high, cui_applicable, framework_count FROM controls {where} ORDER BY family, nist_id"
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["nist_id", "family", "title", "baseline_low", "baseline_moderate", "baseline_high", "cui_applicable", "framework_count"]
    _output(results, args.format, cols)
    return 0


def cmd_overlap(args, conn: sqlite3.Connection) -> int:
    """ER-based overlap between two frameworks."""
    fw_a_candidates = _resolve_fw(args.framework_a, conn) if hasattr(args, "framework_a") else []
    fw_b_candidates = _resolve_fw(args.framework_b, conn) if hasattr(args, "framework_b") else []

    # Fall back to ER framework names (different from unified_mappings frameworks)
    if not fw_a_candidates:
        er_fws = conn.execute("SELECT DISTINCT framework FROM er_mappings ORDER BY framework").fetchall()
        print("Known ER frameworks:", [r[0] for r in er_fws], file=sys.stderr)
        fw_a_candidates = [args.framework_a]
    if not fw_b_candidates:
        fw_b_candidates = [args.framework_b]

    fw_a = fw_a_candidates[0]
    fw_b = fw_b_candidates[0]

    ers_a = conn.execute(
        "SELECT COUNT(DISTINCT er_id) FROM er_mappings WHERE framework = ?", (fw_a,)
    ).fetchone()[0]
    ers_b = conn.execute(
        "SELECT COUNT(DISTINCT er_id) FROM er_mappings WHERE framework = ?", (fw_b,)
    ).fetchone()[0]

    # Use er_overlap_pairs view (framework_a < framework_b alphabetically)
    a_lt_b = fw_a < fw_b
    fa, fb = (fw_a, fw_b) if a_lt_b else (fw_b, fw_a)
    shared = conn.execute(
        "SELECT COUNT(DISTINCT er_id) FROM er_overlap_pairs WHERE framework_a = ? AND framework_b = ?",
        (fa, fb),
    ).fetchone()[0]

    union = ers_a + ers_b - shared
    jaccard = round(shared / union * 100, 1) if union else 0.0
    a_covers_b = round(shared / ers_b * 100, 1) if ers_b else 0.0
    b_covers_a = round(shared / ers_a * 100, 1) if ers_a else 0.0

    result = {
        "framework_a": fw_a,
        "framework_b": fw_b,
        "er_count_a": ers_a,
        "er_count_b": ers_b,
        "shared_er_count": shared,
        "union_er_count": union,
        "jaccard_pct": jaccard,
        "a_covers_b_pct": a_covers_b,
        "b_covers_a_pct": b_covers_a,
    }

    if args.format == "json":
        print(json.dumps(result, indent=2))
    elif args.format == "csv":
        writer = csv_module.DictWriter(sys.stdout, fieldnames=list(result))
        writer.writeheader()
        writer.writerow(result)
    else:
        print(f"Framework A : {fw_a} ({ers_a} ER controls)")
        print(f"Framework B : {fw_b} ({ers_b} ER controls)")
        print(f"Shared ERs  : {shared}  (union={union})")
        print(f"Jaccard     : {jaccard}%")
        print(f"A covers B  : {a_covers_b}%  ({fw_a} → {fw_b})")
        print(f"B covers A  : {b_covers_a}%  ({fw_b} → {fw_a})")
    return 0


def cmd_search(args, conn: sqlite3.Connection) -> int:
    """Full-text search across control text/title/discussion."""
    kw = args.keyword.strip()
    # FTS5 needs hyphenated terms quoted
    if " " in kw or "-" in kw:
        fts_query = f'"{kw}"'
    else:
        fts_query = kw

    conditions = ["controls_fts MATCH ?"]
    params: list = [fts_query]

    scope_join = ""
    scope_conditions = []

    fedramp_scope = getattr(args, "scope", None)
    if fedramp_scope:
        lv = fedramp_scope.lower()
        col_map = {"low": "baseline_low", "moderate": "baseline_moderate", "high": "baseline_high"}
        col = col_map.get(lv)
        if col:
            scope_conditions.append(f"c.{col} = 1")
        else:
            print(f"[ERROR] Unknown scope: {fedramp_scope!r}. Use low/moderate/high.", file=sys.stderr)
            return 1

    if getattr(args, "family", None):
        scope_conditions.append("c.family = ?")
        params.append(args.family.upper())

    if scope_conditions:
        scope_where = " AND ".join(scope_conditions)
        sql = f"""
            SELECT c.nist_id, c.family, c.title,
                   snippet(controls_fts, 1, '[', ']', '…', 12) AS excerpt
            FROM controls_fts
            JOIN controls c ON controls_fts.nist_id = c.nist_id
            WHERE {' AND '.join(conditions)}
              AND {scope_where}
            ORDER BY c.family, c.nist_id
            LIMIT 50
        """
    else:
        sql = f"""
            SELECT c.nist_id, c.family, c.title,
                   snippet(controls_fts, 1, '[', ']', '…', 12) AS excerpt
            FROM controls_fts
            JOIN controls c ON controls_fts.nist_id = c.nist_id
            WHERE {' AND '.join(conditions)}
            ORDER BY c.family, c.nist_id
            LIMIT 50
        """

    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["nist_id", "family", "title", "excerpt"]
    _output(results, args.format, cols)
    return 0


def cmd_changelog(args, conn: sqlite3.Connection) -> int:
    """Show framework changelog entries."""
    conditions = []
    params: list = []

    if getattr(args, "framework", None):
        conditions.append("framework_id = ?")
        params.append(args.framework)
    since = getattr(args, "since", None)
    if since:
        conditions.append("change_date >= ?")
        params.append(since)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT changelog_id, framework_id, version_from, version_to, change_date,
               human_confirmed, notes
        FROM changelog {where}
        ORDER BY change_date DESC
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]

    if args.format == "json":
        # For JSON, also include arrays
        full_rows = []
        for r in results:
            row = dict(r)
            cl = conn.execute("SELECT * FROM changelog WHERE changelog_id = ?", (row["changelog_id"],)).fetchone()
            full = dict(cl)
            for field in ("controls_added", "controls_withdrawn", "controls_renamed", "controls_modified"):
                try:
                    full[field] = json.loads(full.get(field, "[]") or "[]")
                except Exception:
                    pass
            full_rows.append(full)
        print(json.dumps(full_rows, indent=2, ensure_ascii=False))
        return 0

    cols = ["changelog_id", "framework_id", "version_from", "version_to", "change_date", "human_confirmed", "notes"]
    _output(results, args.format, cols)
    return 0


def cmd_feeds(args, conn: sqlite3.Connection) -> int:
    """Show framework registry."""
    conditions = []
    params: list = []

    if getattr(args, "framework", None):
        conditions.append("framework_id = ?")
        params.append(args.framework)
    if getattr(args, "status", None) == "changed":
        conditions.append("last_changed IS NOT NULL AND last_changed != ''")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT framework_id, label, current_version, last_changed, check_strategy, draft_status
        FROM framework_registry {where}
        ORDER BY framework_id
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["framework_id", "label", "current_version", "last_changed", "check_strategy", "draft_status"]
    _output(results, args.format, cols)
    return 0


def cmd_announcements(args, conn: sqlite3.Connection) -> int:
    """Show announcements feed entries."""
    conditions = []
    params: list = []

    days = getattr(args, "days", 30)
    conditions.append(f"(published_at IS NULL OR published_at >= date('now', '-{int(days)} days'))")

    if getattr(args, "unreviewed", False):
        conditions.append("human_reviewed = 0")
    if getattr(args, "framework", None):
        conditions.append("framework_ids LIKE ?")
        params.append(f"%{args.framework}%")

    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT entry_id, framework_ids, title, published_at, change_type, human_reviewed, url
        FROM announcements {where}
        ORDER BY published_at DESC
        LIMIT 100
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["entry_id", "framework_ids", "title", "published_at", "change_type", "human_reviewed", "url"]
    _output(results, args.format, cols)
    return 0


def cmd_manifest(args, conn: sqlite3.Connection) -> int:
    """Show DB build manifest (row counts, size, sha256)."""
    counts = {}
    for tbl in ("controls", "enhancements", "parameters", "unified_mappings",
                "er_controls", "er_mappings", "framework_registry", "changelog", "announcements"):
        counts[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]

    # Find manifest file
    db_path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    manifest_path = db_path.parent / "grc_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {"note": "grc_manifest.json not found", "row_counts": counts}

    if args.format == "json":
        print(json.dumps(manifest, indent=2))
    else:
        for k, v in manifest.items():
            if isinstance(v, dict):
                print(f"{k}:")
                for kk, vv in v.items():
                    print(f"  {kk}: {vv}")
            else:
                print(f"{k}: {v}")
    return 0


# ── Argument parser ────────────────────────────────────────────────────────────

def _add_format(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--format", choices=["table", "json", "csv"], default="table",
                     help="Output format (default: table)")


def _add_db(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--db", metavar="PATH", default=None,
                     help="Path to grc.db (auto-discovered if omitted)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="dbz_query.py",
        description="Token-reduction query CLI for the GRC cross-mapping database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--db", metavar="PATH", default=None,
                    help="Path to grc.db (auto-discovered if omitted)")

    subs = ap.add_subparsers(dest="command", required=True)

    # reverse
    rev = subs.add_parser("reverse", help="Framework control → NIST 800-53 IDs")
    rev.add_argument("--framework", required=True, help="Framework name or alias (e.g. iso, cmmc, 'ISO/IEC 27001:2022')")
    rev.add_argument("--control", required=True, help="Framework control ID (e.g. A.5.16)")
    _add_format(rev); _add_db(rev)

    # forward
    fwd = subs.add_parser("forward", help="NIST control → cross-framework mappings")
    fwd.add_argument("--control", required=True, help="NIST 800-53 control ID (e.g. AC-2)")
    fwd.add_argument("--frameworks", nargs="+", metavar="FW",
                     help="Limit to these frameworks (aliases accepted)")
    _add_format(fwd); _add_db(fwd)

    # scope
    scope = subs.add_parser("scope", help="List controls matching baseline/family/CUI/privacy criteria")
    scope.add_argument("--fedramp", metavar="LEVEL",
                       help="FedRAMP level: low | moderate | high")
    scope.add_argument("--family", metavar="FAM", help="Control family (e.g. IA, AC)")
    scope.add_argument("--cui", action="store_true", help="Filter CUI-applicable controls")
    scope.add_argument("--privacy", action="store_true", help="Filter privacy baseline controls")
    _add_format(scope); _add_db(scope)

    # overlap
    ov = subs.add_parser("overlap", help="ER-level overlap between two frameworks")
    ov.add_argument("--framework-a", required=True, metavar="FW_A",
                    help="First framework name (e.g. 'SOC 2')")
    ov.add_argument("--framework-b", required=True, metavar="FW_B",
                    help="Second framework name (e.g. 'ISO 27001/2 (2022)')")
    _add_format(ov); _add_db(ov)

    # search
    srch = subs.add_parser("search", help="Full-text search across control text")
    srch.add_argument("--keyword", required=True, help="Search term (e.g. 'multi-factor')")
    srch.add_argument("--scope", metavar="LEVEL",
                      help="Limit to FedRAMP level: low | moderate | high")
    srch.add_argument("--family", metavar="FAM", help="Limit to control family")
    _add_format(srch); _add_db(srch)

    # changelog
    cl = subs.add_parser("changelog", help="Show framework changelog")
    cl.add_argument("--framework", metavar="FW_ID",
                    help="Filter by framework_id (e.g. nist-800-53)")
    cl.add_argument("--since", metavar="DATE", help="Filter entries on or after YYYY-MM-DD")
    _add_format(cl); _add_db(cl)

    # feeds
    fd = subs.add_parser("feeds", help="Show framework registry")
    fd.add_argument("--framework", metavar="FW_ID", help="Filter by framework_id")
    fd.add_argument("--status", choices=["changed", "all"], default="all",
                    help="Filter: changed=has last_changed date")
    _add_format(fd); _add_db(fd)

    # announcements
    ann = subs.add_parser("announcements", help="Show announcement feed entries")
    ann.add_argument("--days", type=int, default=30, help="Look-back window in days (default 30)")
    ann.add_argument("--framework", metavar="FW_ID", help="Filter by framework_id substring")
    ann.add_argument("--unreviewed", action="store_true", help="Show only human_reviewed=false")
    _add_format(ann); _add_db(ann)

    # manifest
    man = subs.add_parser("manifest", help="Show DB build manifest (row counts, sha256)")
    _add_format(man); _add_db(man)

    return ap


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    db_override = getattr(args, "db", None)
    try:
        db_path = _find_db(db_override)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    conn = _open_db(db_path)

    cmd_map = {
        "reverse": cmd_reverse,
        "forward": cmd_forward,
        "scope": cmd_scope,
        "overlap": cmd_overlap,
        "search": cmd_search,
        "changelog": cmd_changelog,
        "feeds": cmd_feeds,
        "announcements": cmd_announcements,
        "manifest": cmd_manifest,
    }

    fn = cmd_map.get(args.command)
    if not fn:
        print(f"[ERROR] Unknown command: {args.command}", file=sys.stderr)
        return 1

    try:
        return fn(args, conn)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
