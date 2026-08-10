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
    python3 dbz_query.py kev --cve CVE-2021-44228
    python3 dbz_query.py kev --days 30 --family SI
    python3 dbz_query.py cfr --part "45-CFR-164" --section 164.308
    python3 dbz_query.py cfr --keyword "authentication" --family IA
    python3 dbz_query.py attack --technique T1078
    python3 dbz_query.py attack --tactic initial-access --control AC-2
    python3 dbz_query.py edgar --incident-type ransomware
    python3 dbz_query.py edgar --company "Acme" --days 180
    python3 dbz_query.py 800-63b --aal AAL2 [--section 4.2] [--control IA-2]
    python3 dbz_query.py fips --level 3 [--vendor "Microsoft"] [--status active]

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import framework_alias  # the single alias authority (see its module docstring)
from framework_alias import AmbiguousFrameworkError

_ALIAS_REGISTRY: dict | None = None


def _alias_registry(conn) -> dict:
    """Load the alias registry once per process (framework_labels + vocab blocks)."""
    global _ALIAS_REGISTRY
    if _ALIAS_REGISTRY is None:
        _ALIAS_REGISTRY = framework_alias.load_registry(conn)
    return _ALIAS_REGISTRY


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
    # _resolve_fw serves unified_mappings-backed commands only (reverse/forward);
    # spine labels don't exist there. Master-surface alias behavior — including the
    # cmmc→r2 fan-out — lives in _MASTER_FW_GROUPS / _master_fw_set.
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


def _unified_labels(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT framework FROM unified_mappings")]


def _resolve_fw(alias: str, conn: sqlite3.Connection) -> list[str]:
    """Resolve a framework alias/shorthand to exact `unified_mappings` name(s).

    Delegates to framework_alias — the single registry — so this surface can no longer
    disagree with `master`/`overlap` about what a word means. Registry-declared
    ambiguity raises; the legacy _FW_ALIASES map is consulted only for multi-label
    legacy groupings the registry doesn't express."""
    pool = _unified_labels(conn)
    reg = _alias_registry(conn)
    hit = framework_alias.resolve(alias, pool, reg, surface="unified")
    if hit:
        return hit
    # A declared gap means this framework genuinely has no rows here: report nothing
    # rather than letting the legacy map substitute a neighbouring framework (how
    # 'hipaa' used to answer with the Privacy Rule and '800-53' with Rev 4 Appendix J).
    if framework_alias.declared_gap(alias, "unified", reg):
        return []
    canonical = reg["alias_map"].get(alias.strip().lower())
    found = [c for c in _FW_ALIASES.get(alias.lower(), []) if c in set(pool)]
    if canonical:
        found = [c for c in found if framework_alias.compatible_families(
            reg["alias_map"].get(c.lower(), c), canonical, reg)]
    return found


# ── Context overlays (presentation filter — never touches tables) ──────────────

def _overlay_profile(args):
    """Resolve --overlay NAME[,NAME] into an effective profile, or None."""
    names = getattr(args, "overlay", None)
    if not names:
        return None
    import overlay_resolver  # sibling module
    return overlay_resolver.resolve([n.strip() for n in names.split(",") if n.strip()])


def _overlay_note(profile, suppressed=0, extra=""):
    print(f"overlay: {','.join(profile['names'])} — suppressed {suppressed} row(s); "
          f"emphasized: {', '.join(profile['emphasized_frameworks']) or 'none'}"
          f"{'; ' + extra if extra else ''} (omit --overlay for the unfiltered view)")


def _add_overlay(p):
    p.add_argument("--overlay", metavar="NAME[,NAME]",
                   help="apply context overlay(s) (canonical-sources/overlays/) — a "
                        "presentation filter; suppressed rows are always counted, never silent")


# ── Output formatters ──────────────────────────────────────────────────────────

def _output(rows: list[dict], fmt: str, columns: list[str]) -> None:
    # Normalize sqlite3.Row (and any mapping-like) to plain dicts so json/csv/table
    # all work regardless of what the caller passed.
    rows = [r if isinstance(r, dict) else dict(r) for r in rows]
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
    _sp = _overlay_profile(args)
    if not fedramp_level and _sp:  # overlay default applies only when the flag is absent
        fedramp_level = _sp["sets"].get("default_scope_fedramp")
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
    """CCI / sub-part-anchored overlap between two frameworks (never errors)."""
    import spine_overlap  # type: ignore
    basis_pref = getattr(args, "basis", "auto") or "auto"
    want_pc = bool(getattr(args, "per_control", False))
    result = spine_overlap.compute(conn, args.framework_a, args.framework_b,
                                   want_per_control=want_pc, basis_pref=basis_pref)

    profile = _overlay_profile(args)
    if profile and result.get("overlap_pct") is not None:
        result["overlay"] = {"names": profile["names"],
                             "emphasized": profile["emphasized_frameworks"],
                             "suppressed_count": 0}  # overlap is a single pair — nothing to suppress
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("overlap_pct") is not None else 1

    if result.get("overlap_pct") is None:
        print(f"[input error] {result.get('error')}", file=sys.stderr)
        print("Known frameworks:", ", ".join(result.get("known_frameworks", [])[:20]), file=sys.stderr)
        return 1

    print(f"Framework A : {result['framework_a']}")
    print(f"Framework B : {result['framework_b']}")
    _rb = f", relationship_basis: {result['relationship_basis']}" if result.get("relationship_basis") else ""
    print(f"Basis       : {result['basis']}  (provenance: {result.get('provenance')}{_rb})")
    print(f"Overlap     : {result['overlap_pct']}%  (Jaccard)")
    print(f"A covers B  : {result.get('a_covers_b_pct')}%")
    print(f"B covers A  : {result.get('b_covers_a_pct')}%")
    print(f"Shared      : {result.get('shared_count')}  "
          f"(A={result.get('framework_a_count')}, B={result.get('framework_b_count')})")
    print(f"Confidence  : {result.get('confidence')} ({result.get('confidence_score')})  "
          f"needs_confirmation={result.get('needs_confirmation')}")
    _cs = result.get("consensus_support") or {}
    if _cs.get("strong_edges"):
        print(f"Consensus   : {_cs['strong_edges']} strong cross-source pairs "
              f"({_cs['text_confirmed']} text-confirmed corroborating)")
    for c in result.get("caveats", []):
        print(f"  ! {c}")
    if result.get("data_gap"):
        print(f"  data_gap: {result['data_gap']}")
    for pc in result.get("per_control", [])[:25]:
        print(f"  [{pc['classification']:<7}] {pc['framework_a_control']:<18} "
              f"-> {', '.join(pc['corresponds_to'][:4])}")
        if pc["classification"] == "partial":
            print(f"            met: {', '.join(pc['shared_subparts'][:6])}")
            print(f"            unmet: {', '.join(pc['a_unmet_subparts'][:6])}  odp:{pc['odp']['status']}")
    return 0


def cmd_consensus(args, conn: sqlite3.Connection) -> int:
    """Cross-source consensus pairs: where independent mapping authorities agree."""
    where, params = ["1=1"], []
    if getattr(args, "framework_a", None):
        where.append("(fw_a=? OR fw_b=?)")
        params += [args.framework_a, args.framework_a]
    if getattr(args, "framework_b", None):
        where.append("(fw_a=? OR fw_b=?)")
        params += [args.framework_b, args.framework_b]
    tier = getattr(args, "tier", "strong") or "strong"
    if tier != "all":
        where.append("tier=?")
        params.append(tier)
    rows = conn.execute(f"""
        SELECT fw_a, native_a, fw_b, native_b, votes, tier, voters, extent,
               shared_atoms_count, production_support, text_confirmation, evidence
        FROM consensus_edges WHERE {' AND '.join(where)}
        ORDER BY votes DESC, fw_a, native_a, fw_b, native_b
        LIMIT ?""", (*params, getattr(args, "limit", 40) or 40)).fetchall()
    if args.format == "json":
        cols = ["fw_a", "native_a", "fw_b", "native_b", "votes", "tier", "voters",
                "extent", "shared_atoms_count", "production_support",
                "text_confirmation", "evidence"]
        print(json.dumps([dict(zip(cols, r)) for r in rows], indent=2))
        return 0
    if not rows:
        print("No consensus pairs match. (Tiers: strong >=3 voters, moderate=2; use --tier all.)")
        return 0
    print(f"{len(rows)} consensus pair(s) — agreement across independent mapping authorities.")
    print("Consensus is derived evidence with citations; it never overrides any owner's mapping.\n")
    for fw_a, na, fw_b, nb, votes, t, voters, extent, atoms, prod, txt, _ev in rows:
        prod_s = f"  production-corroborated x{prod}" if prod else ""
        print(f"[{t}:{votes}] {fw_a} {na}  <->  {fw_b} {nb}")
        print(f"        voters={voters}  extent={extent}  shared_atoms={atoms}  "
              f"text={txt}{prod_s}")
    return 0


# The tier order lives in ONE place (master_surface.TIER_ORDER) so the query
# surface and the assembler can never drift apart.
def _master_tier_order() -> list[str]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from master_surface import TIER_ORDER  # type: ignore
    return TIER_ORDER


_MASTER_TIER_ORDER = _master_tier_order()


def _master_canon_fw(conn: sqlite3.Connection, name: str) -> str | None:
    """Resolve any framework alias/label to the master-surface canonical label
    via the framework_labels registry (exact, case-insensitive, then substring
    over the canonicals actually present in master_mappings)."""
    hits = framework_alias.resolve(name, _master_labels(conn),
                                   _alias_registry(conn), surface="master")
    return hits[0] if hits else None


def _master_labels(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT fw_a FROM master_mappings "
        "UNION SELECT DISTINCT fw_b FROM master_mappings")]


def _master_fw_set(conn: sqlite3.Connection, name: str) -> tuple[list[str], str]:
    """Resolve a user-typed framework name for the master surface. Returns
    (labels, note): a declared family group (framework_vocab framework_aliases.
    family_groups — e.g. cmmc spanning CMMC 2.0 + 800-171 r2 under the May-2024 class
    deviation) fans out to every member the surface carries; anything else resolves to
    a single canonical. `note` explains a fan-out so the answer is self-describing."""
    reg = _alias_registry(conn)
    labels = framework_alias.resolve(name, _master_labels(conn), reg, surface="master")
    group = framework_alias.group_for(name, reg)
    if group and len(labels) > 1:
        basis = reg["family_groups"][name.strip().lower()].get("basis", "")
        return labels, (f"'{name}' spans {' + '.join(labels)}"
                        + (f" — {basis.split('.')[0]}" if basis else ""))
    return labels, ""


def _master_declared_gap(conn, name: str, fmt: str) -> int | None:
    """A registry-declared framework/surface data gap answered as a structured gap
    rather than 'unknown framework' — the difference between "we know this framework
    has no master rows and why" and "we do not recognise the word". Same response shape
    as _master_soc1_gap, which is the original instance of this pattern."""
    spec = framework_alias.declared_gap(name, "master", _alias_registry(conn))
    if not spec:
        return None
    gap = {
        "tool": "master-crosswalk",
        "framework": name,
        "data_gap": "declared_no_master_rows",
        "explanation": spec.get("reason", ""),
        "human_review_required": True,
    }
    if fmt == "json":
        print(json.dumps(gap, indent=2))
    else:
        print(f"[data gap] {name}: {gap['explanation']}")
    return 0


def _master_soc1_gap(fmt: str) -> int:
    gap = {
        "tool": "master-crosswalk",
        "framework": "SOC 1",
        "data_gap": "no_public_control_layer",
        "explanation": "SOC 1 (SSAE 22 / AT-C 320) defines report standards, not "
                       "a public control catalog — every SOC 1 control set is "
                       "engagement-specific. The master surface carries no SOC 1 "
                       "id-level rows; use `overlap` for the aggregate "
                       "inferred_er signal.",
        "human_review_required": True,
    }
    if fmt == "json":
        print(json.dumps(gap, indent=2))
    else:
        print(f"[data gap] {gap['explanation']}")
    return 0


def cmd_master(args, conn: sqlite3.Connection) -> int:
    """Master mapping surface: any framework <-> any framework, tier-arbitrated,
    with minority-report corroboration. Pair, control, and audit-scope modes."""
    limit = getattr(args, "limit", 100) or 100
    min_tier = getattr(args, "min_tier", None)
    if min_tier is None:  # overlay may supply a default; an explicit flag always wins
        _p = _overlay_profile(args)
        if _p:
            min_tier = _p["sets"].get("default_min_tier")
    max_rank = (_MASTER_TIER_ORDER.index(min_tier) + 1) if min_tier else len(_MASTER_TIER_ORDER)
    tier_case = " ".join(f"WHEN '{t}' THEN {i + 1}" for i, t in enumerate(_MASTER_TIER_ORDER))

    ev_state = getattr(args, "evidence_state", None)
    ev_cond = " AND evidence_state = ?" if ev_state else ""
    ev_params = (ev_state,) if ev_state else ()

    control = getattr(args, "control", None)
    fw_single = getattr(args, "framework", None)
    fa_in, fb_in = getattr(args, "framework_a", None), getattr(args, "framework_b", None)

    if control and fw_single:  # ── control mode ────────────────────────────────
        fws, note = _master_fw_set(conn, fw_single)
        if "SOC 1" in fws:
            return _master_soc1_gap(args.format)
        if not fws:
            print(f"[input error] unknown framework: {fw_single!r}", file=sys.stderr)
            return 1
        ph = ",".join("?" * len(fws))
        rows = conn.execute(f"""
            SELECT * FROM master_mappings
            WHERE ((fw_a IN ({ph}) AND native_a = ?) OR (fw_b IN ({ph}) AND native_b = ?))
              AND (CASE tier {tier_case} END) <= ?{ev_cond}
            ORDER BY CASE tier {tier_case} END, fw_a, native_a, fw_b, native_b
            LIMIT ?""", (*fws, control, *fws, control, max_rank, *ev_params, limit)).fetchall()
        header = f"{' + '.join(fws)} {control}: {len(rows)} master mapping(s)" + \
                 (f" [{note}]" if note else "")
    elif fa_in and fb_in:  # ── pair mode ───────────────────────────────────────
        fas, note_a = _master_fw_set(conn, fa_in)
        fbs, note_b = _master_fw_set(conn, fb_in)
        if "SOC 1" in fas or "SOC 1" in fbs:
            return _master_soc1_gap(args.format)
        if not fas or not fbs:
            missing = [x for x, r in ((fa_in, fas), (fb_in, fbs)) if not r]
            for m in missing:
                rc = _master_declared_gap(conn, m, args.format)
                if rc is not None:
                    return rc
            print(f"[input error] unknown framework(s): {missing}", file=sys.stderr)
            return 1
        pha, phb = ",".join("?" * len(fas)), ",".join("?" * len(fbs))
        rows = conn.execute(f"""
            SELECT * FROM master_mappings
            WHERE ((fw_a IN ({pha}) AND fw_b IN ({phb}))
                OR (fw_a IN ({phb}) AND fw_b IN ({pha})))
              AND (CASE tier {tier_case} END) <= ?{ev_cond}
            ORDER BY CASE tier {tier_case} END, fw_a, native_a, fw_b, native_b
            LIMIT ?""", (*fas, *fbs, *fbs, *fas, max_rank, *ev_params, limit)).fetchall()
        notes = "; ".join(n for n in (note_a, note_b) if n)
        header = f"{' + '.join(fas)} <-> {' + '.join(fbs)}: {len(rows)} master mapping(s)" + \
                 (f" [{notes}]" if notes else "")
    elif fa_in and (getattr(args, "fedramp", None) or getattr(args, "cui", False)
                    or getattr(args, "privacy", False) or getattr(args, "family", None)):
        # ── audit-scope mode: which of A's requirements touch the in-scope
        #    NIST control set (baseline flags on controls + enhancements). ──────
        fa = _master_canon_fw(conn, fa_in)
        if fa == "SOC 1":
            return _master_soc1_gap(args.format)
        if not fa:
            print(f"[input error] unknown framework: {fa_in!r}", file=sys.stderr)
            return 1
        conds, params = [], []
        lv = (getattr(args, "fedramp", None) or "").lower()
        if lv:
            colname = {"low": "baseline_low", "l": "baseline_low",
                       "moderate": "baseline_moderate", "mod": "baseline_moderate", "m": "baseline_moderate",
                       "high": "baseline_high", "h": "baseline_high"}.get(lv)
            if not colname:
                print(f"[ERROR] Unknown FedRAMP level: {lv!r}. Use low/moderate/high.", file=sys.stderr)
                return 1
            conds.append(f"{colname} = 1")
        if getattr(args, "privacy", False):
            conds.append("privacy_baseline = 1")
        if getattr(args, "cui", False):
            conds.append("cui_applicable = 1")
        fam_cond_c, fam_cond_e = "", ""
        if getattr(args, "family", None):
            fam_cond_c = " AND family = ?"
            fam_cond_e = " AND family = ?"
            params.append(args.family.upper())
        where = " AND ".join(conds) if conds else "1=1"
        scope_ids = {r[0] for r in conn.execute(
            f"SELECT nist_id FROM controls WHERE {where}{fam_cond_c}", params)}
        scope_ids |= {r[0] for r in conn.execute(
            f"SELECT id FROM enhancements WHERE {where}{fam_cond_e}", params)}
        all_rows = conn.execute(f"""
            SELECT * FROM master_mappings
            WHERE ((fw_a = ? AND fw_b = 'NIST 800-53') OR (fw_b = ? AND fw_a = 'NIST 800-53'))
              AND (CASE tier {tier_case} END) <= ?
            ORDER BY CASE tier {tier_case} END, fw_a, native_a, fw_b, native_b""",
            (fa, fa, max_rank)).fetchall()
        rows, natives_in, natives_all = [], set(), set()
        for r in all_rows:
            d = dict(r)
            nat, ctrl = ((d["native_a"], d["native_b"]) if d["fw_a"] == fa
                         else (d["native_b"], d["native_a"]))
            natives_all.add(nat)
            if ctrl in scope_ids:
                natives_in.add(nat)
                if len(rows) < limit:
                    rows.append(r)
        header = (f"{fa} x scope({', '.join(conds) if conds else 'all'}"
                  f"{' family=' + args.family.upper() if getattr(args, 'family', None) else ''}): "
                  f"{len(natives_in)} of {len(natives_all)} {fa} requirements touch "
                  f"{len(scope_ids)} in-scope NIST controls (advisory — actual audit "
                  f"scope depends on organization context)")
    else:
        print("[input error] master needs --framework-a + --framework-b (pair), "
              "--framework + --control (control), or --framework-a + a scope flag "
              "(--scope-fedramp/--cui/--privacy/--family).", file=sys.stderr)
        return 1

    results = [dict(r) for r in rows]
    if ev_state:
        results = [d for d in results if d.get("evidence_state") == ev_state]
        header += f" [evidence_state={ev_state}]"
    overlay_block = None
    profile = _overlay_profile(args)
    if profile:
        import overlay_resolver
        results, suppressed = overlay_resolver.apply_to_rows(profile, results)
        overlay_block = overlay_resolver.stamp(profile, suppressed)
    if args.format == "json":
        payload = {"tool": "master-crosswalk", "summary": header,
                   "rows": results, "human_review_required": True}
        if overlay_block:
            payload["overlay"] = overlay_block
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(header)
    if profile:
        _overlay_note(profile, overlay_block["suppressed_count"])
    print(f"Tier order: {' > '.join(_MASTER_TIER_ORDER)}; "
          "corroboration preserves every non-winning surface.\n")
    for d in results:
        conf = f" conf={d['confidence']}" if d["confidence"] is not None else ""
        votes = f" votes={d['votes']}" if d["votes"] else ""
        prod = f" production x{d['production_support']}" if d["production_support"] else ""
        anch = f" anchors={d['anchor_count']}" if d["anchor_count"] else ""
        corr = ""
        if d["corroboration"]:
            corr = f" (+{len(json.loads(d['corroboration']))} corroborating surface(s))"
        ev = f" ev={d['evidence_state']}" if d.get("evidence_state") else ""
        print(f"[{d['tier']}:{d['provenance']}{conf}{ev}] {d['fw_a']} {d['native_a']} <-> "
              f"{d['fw_b']} {d['native_b']} ({d['relationship']}){votes}{prod}{anch}{corr}")
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
    if not fedramp_scope:  # overlay default when the flag is absent (control-text search
        _sp = _overlay_profile(args)  # is not framework-keyed, so only the scope default applies)
        if _sp:
            fedramp_scope = _sp["sets"].get("default_scope_fedramp")
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


def cmd_horizon(args, conn: sqlite3.Connection) -> int:
    """Show the anticipated-updates horizon (expected/scheduled future revisions).
    Delegates the dynamic overdue/upcoming logic to horizon_monitor for a single
    source of truth; --list reads the DB table directly."""
    import importlib, json as _json
    try:
        hm = importlib.import_module("horizon_monitor")
    except Exception:
        hm = None

    mode = "list"
    for m in ("overdue", "upcoming", "materialized"):
        if getattr(args, m, None):
            mode = m
            break

    if hm is not None and mode in ("overdue", "upcoming"):
        argv = ([f"--{mode}"] + ([str(args.upcoming)] if mode == "upcoming" else [])
                + (["--json"] if args.format == "json" else []))
        return hm.main(argv)

    # list / materialized: read the DB table
    where = "WHERE status = 'materialized'" if mode == "materialized" else ""
    rows = conn.execute(f"""
        SELECT id, feed_id, authority, artifact, expected_window, confidence, status, lifecycle_stage
        FROM anticipated_updates {where} ORDER BY status, id""").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        w = _json.loads(d["expected_window"]) if d.get("expected_window") else None
        d["window"] = ("no_fixed_date" if not isinstance(w, dict)
                       else (w["latest"] if w.get("earliest") == w.get("latest") else f'{w["earliest"]}…{w["latest"]}'))
        del d["expected_window"]
        out.append(d)
    cols = ["id", "authority", "artifact", "window", "confidence", "status", "lifecycle_stage"]
    _output([{k: r.get(k) for k in cols} for r in out], args.format, cols)
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


def cmd_kev(args, conn: sqlite3.Connection) -> int:
    """Look up a CVE or list recent KEV entries with NIST family mappings."""
    conditions = []
    params: list = []

    if getattr(args, "cve", None):
        conditions.append("cve_id = ?")
        params.append(args.cve.upper())
    if getattr(args, "days", None):
        conditions.append(f"date_added >= date('now', '-{int(args.days)} days')")
    if getattr(args, "family", None):
        conditions.append("nist_families LIKE ?")
        params.append(f'%"{args.family.upper()}"%')

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT cve_id, date_added, vulnerability_name, affected_product, nist_families
        FROM cisa_kev {where}
        ORDER BY date_added DESC
        LIMIT 100
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["cve_id", "date_added", "vulnerability_name", "affected_product", "nist_families"]
    _output(results, args.format, cols)
    return 0


def cmd_cfr(args, conn: sqlite3.Connection) -> int:
    """Look up CFR requirements by part, section, or keyword."""
    conditions = []
    params: list = []

    if getattr(args, "part", None):
        conditions.append("cfr_part LIKE ?")
        params.append(f"%{args.part}%")
    if getattr(args, "section", None):
        conditions.append("section_id LIKE ?")
        params.append(f"%{args.section}%")
    if getattr(args, "keyword", None):
        conditions.append("(title LIKE ? OR text LIKE ?)")
        kw = f"%{args.keyword}%"
        params.extend([kw, kw])
    if getattr(args, "family", None):
        conditions.append("nist_families LIKE ?")
        params.append(f'%"{args.family.upper()}"%')

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT section_id, cfr_part, framework_id, title, nist_families
        FROM cfr_requirements {where}
        ORDER BY cfr_part, section_id
        LIMIT 100
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["section_id", "cfr_part", "framework_id", "title", "nist_families"]
    _output(results, args.format, cols)
    return 0


def cmd_attack(args, conn: sqlite3.Connection) -> int:
    """Look up MITRE ATT&CK techniques and their NIST 800-53 control mappings."""
    conditions = []
    params: list = []

    if getattr(args, "technique", None):
        tid = args.technique.upper()
        conditions.append("(technique_id = ? OR technique_id LIKE ?)")
        params.extend([tid, f"{tid}.%"])
    if getattr(args, "name", None):
        conditions.append("name LIKE ?")
        params.append(f"%{args.name}%")
    if getattr(args, "tactic", None):
        conditions.append("tactic LIKE ?")
        params.append(f"%{args.tactic}%")
    if getattr(args, "control", None):
        conditions.append("nist_controls LIKE ?")
        params.append(f'%"{args.control.upper()}%')

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT technique_id, name, tactic, is_subtechnique, nist_controls, nist_families
        FROM attack_techniques {where}
        ORDER BY technique_id
        LIMIT 100
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["technique_id", "name", "tactic", "is_subtechnique", "nist_controls", "nist_families"]
    _output(results, args.format, cols)
    return 0


def cmd_edgar(args, conn: sqlite3.Connection) -> int:
    """Query SEC EDGAR 8-K Item 1.05 cyber incident disclosures."""
    conditions = []
    params: list = []

    if getattr(args, "company", None):
        conditions.append("company_name LIKE ?")
        params.append(f"%{args.company}%")
    if getattr(args, "incident_type", None):
        conditions.append("incident_type LIKE ?")
        params.append(f"%{args.incident_type}%")
    if getattr(args, "days", None):
        conditions.append(f"filed_at >= date('now', '-{int(args.days)} days')")
    if getattr(args, "family", None):
        conditions.append("nist_families LIKE ?")
        params.append(f'%"{args.family.upper()}"%')

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT accession_no, company_name, filed_at, incident_type,
               nist_families, classification_confidence
        FROM edgar_cyber_incidents {where}
        ORDER BY filed_at DESC
        LIMIT 100
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["accession_no", "company_name", "filed_at", "incident_type",
            "nist_families", "classification_confidence"]
    _output(results, args.format, cols)
    return 0


def cmd_manifest(args, conn: sqlite3.Connection) -> int:
    """Show DB build manifest (row counts, size, sha256) and system build metadata."""
    # Show system build metadata first (engine/schema version, build timestamp)
    meta_rows = conn.execute("SELECT key, value FROM db_metadata ORDER BY key").fetchall()
    if meta_rows and args.format != "json":
        print("=== Build Metadata ===")
        for k, v in meta_rows:
            print(f"  {k}: {v}")
        print()

    counts = {}
    all_tables = (
        "controls", "enhancements", "parameters", "unified_mappings",
        "er_controls", "er_mappings", "framework_registry", "changelog", "announcements",
        "cisa_kev", "cfr_requirements", "attack_techniques", "edgar_cyber_incidents",
        "nvd_cves", "disa_ccis", "eurlex_articles",
        "nist_800_63b_requirements", "fips_140_validations",
    )
    for tbl in all_tables:
        try:
            counts[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        except Exception:
            counts[tbl] = "n/a"

    # Find manifest file
    db_path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    manifest_path = db_path.parent / "grc_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["db_metadata"] = dict(meta_rows)
        manifest["row_counts"] = {**manifest.get("row_counts", {}), **counts}
    else:
        manifest = {
            "note": "grc_manifest.json not found",
            "db_metadata": dict(meta_rows),
            "row_counts": counts,
        }

    if args.format == "json":
        print(json.dumps(manifest, indent=2))
    else:
        for k, v in manifest.items():
            if k == "db_metadata":
                continue  # already printed above
            if isinstance(v, dict):
                print(f"{k}:")
                for kk, vv in v.items():
                    print(f"  {kk}: {vv}")
            else:
                print(f"{k}: {v}")
    return 0


def cmd_nvd(args, conn: sqlite3.Connection) -> int:
    """Query NVD CVE data by ID, severity, or NIST family."""
    conditions = []
    params: list = []

    if getattr(args, "cve", None):
        conditions.append("cve_id = ?")
        params.append(args.cve.upper())

    if getattr(args, "severity", None):
        conditions.append("severity = ?")
        params.append(args.severity.upper())

    if getattr(args, "family", None):
        conditions.append("nist_families LIKE ?")
        params.append(f'%"{args.family}"%')

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"SELECT cve_id, published, severity, cvss_score, description, nist_families FROM nvd_cves {where} ORDER BY published DESC LIMIT 50"
    results = conn.execute(sql, params).fetchall()
    cols = ["cve_id", "published", "severity", "cvss_score", "description", "nist_families"]
    _output(results, args.format, cols)
    return 0


def cmd_cci(args, conn: sqlite3.Connection) -> int:
    """Query DISA CCI data by CCI ID or mapped NIST control; inspect the CCI
    dictionary (definitions), the mapping corroboration layer, and coverage."""
    import json as _json

    # --coverage: dictionary completeness + corroboration summary
    if getattr(args, "coverage", False):
        n_cci, n_def = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN definition<>'' THEN 1 ELSE 0 END) FROM disa_ccis").fetchone()
        status = dict(conn.execute("SELECT status, COUNT(*) FROM disa_ccis GROUP BY status").fetchall())
        n_defonly = conn.execute(
            "SELECT COUNT(*) FROM disa_ccis d WHERE NOT EXISTS "
            "(SELECT 1 FROM cci_bridge b WHERE b.cci_id=d.cci_id)").fetchone()[0]
        basis = dict(conn.execute("SELECT basis, COUNT(*) FROM cci_bridge GROUP BY basis").fetchall())
        try:
            verdicts = dict(conn.execute(
                "SELECT verdict, COUNT(*) FROM cci_mapping_corroboration GROUP BY verdict").fetchall())
            n_stig = conn.execute(
                "SELECT COUNT(DISTINCT cci_id) FROM cci_mapping_corroboration WHERE stig_exercised=1").fetchone()[0]
        except sqlite3.OperationalError:
            verdicts, n_stig = {}, 0
        result = {
            "tool": "dbz-cci", "dictionary_ccis": n_cci, "with_definition": n_def,
            "status": status, "definition_only_unmapped": n_defonly,
            "bridge_basis": basis, "corroboration_verdicts": verdicts,
            "ccis_exercised_by_stig": n_stig,
            "note": "acasehs/trackr are derived republications of the DISA list — "
                    "confirmation verifies transcription fidelity + surfaces candidate gaps, "
                    "not independent authority. STIG usage is the independent application witness.",
            "human_review_required": True,
        }
        if args.format == "json":
            print(_json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for k in ("dictionary_ccis", "with_definition", "definition_only_unmapped",
                      "ccis_exercised_by_stig"):
                print(f"{k:<28} {result[k]}")
            print(f"status                       {status}")
            print(f"bridge_basis                 {basis}")
            print(f"corroboration_verdicts       {verdicts}")
        return 0

    # --corroboration CCI-xxxxxx: witnesses + verdict per edge
    if getattr(args, "corroboration", None):
        cci = args.corroboration.strip().upper()
        rows = conn.execute(
            "SELECT r5_control, verdict, disa_basis, in_disa_bridge, in_acasehs_r5, "
            "in_acasehs_r4, in_trackr, stig_exercised, witnesses "
            "FROM cci_mapping_corroboration WHERE cci_id=? ORDER BY r5_control", (cci,)).fetchall()
        cols = ["r5_control", "verdict", "disa_basis", "in_disa_bridge", "in_acasehs_r5",
                "in_acasehs_r4", "in_trackr", "stig_exercised", "witnesses"]
        if args.format == "json":
            defn = conn.execute("SELECT definition FROM disa_ccis WHERE cci_id=?", (cci,)).fetchone()
            print(_json.dumps({
                "cci_id": cci,
                "definition": defn[0] if defn else None,
                "edges": [dict(zip(cols, r)) for r in rows],
                "human_review_required": True,
            }, indent=2, ensure_ascii=False))
        else:
            _output([dict(zip(cols, r)) for r in rows], args.format, cols)
        return 0

    conditions = []
    params: list = []

    if getattr(args, "id", None):
        conditions.append("cci_id = ?")
        params.append(args.id)

    if getattr(args, "control", None):
        conditions.append("(nist_rev5_refs LIKE ? OR nist_rev4_refs LIKE ?)")
        params.extend([f'%{args.control}%', f'%{args.control}%'])

    if getattr(args, "status", None):
        conditions.append("status = ?")
        params.append(args.status)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    # --definition widens the projection to the full text + native indices
    if getattr(args, "definition", False):
        cols = ["cci_id", "status", "type", "publishdate", "definition",
                "nist_rev4_refs", "nist_r5_index", "nist_rev5_refs", "legacy_refs"]
    else:
        cols = ["cci_id", "status", "type", "definition", "nist_rev5_refs"]
    sql = f"SELECT {','.join(cols)} FROM disa_ccis {where} ORDER BY cci_id LIMIT 100"
    results = conn.execute(sql, params).fetchall()
    _output([dict(zip(cols, r)) for r in results], args.format, cols)
    return 0


def cmd_stig(args, conn: sqlite3.Connection) -> int:
    """STIG application-layer queries: catalog, rules, CCI usage, coverage.

    STIGs are the technology/implementation tier — for a STIG's overlap with a
    framework use `overlap stig:<title> × <framework>` (on-demand spine
    projection); this subcommand inspects the raw STIG data itself."""
    import json as _json

    # --coverage: usage stats + unknown-CCI gap report (informational)
    if getattr(args, "coverage", False):
        n_stig, n_rules, n_cite = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(rule_count),0), COALESCE(SUM(cci_citations),0) "
            "FROM stig_catalog").fetchone()
        n_used, n_unknown = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(CASE WHEN in_bridge=0 THEN 1 ELSE 0 END),0) "
            "FROM stig_cci_usage").fetchone()
        n_bridge = conn.execute("SELECT COUNT(DISTINCT cci_id) FROM cci_bridge").fetchone()[0]
        n_bridge_exercised = conn.execute(
            "SELECT COUNT(*) FROM stig_cci_usage WHERE in_bridge=1").fetchone()[0]
        unknown = [r[0] for r in conn.execute(
            "SELECT cci_id FROM stig_cci_usage WHERE in_bridge=0 ORDER BY cci_id")]
        lib = conn.execute(
            "SELECT value FROM db_metadata WHERE key='schema_version'").fetchone()
        result = {
            "tool": "dbz-stig",
            "stigs": n_stig, "rules": n_rules, "cci_citations": n_cite,
            "distinct_ccis_exercised": n_used,
            "cci_bridge_total": n_bridge,
            "cci_bridge_exercised_by_stig": n_bridge_exercised,
            "cci_bridge_coverage_pct": round(n_bridge_exercised / n_bridge * 100, 1) if n_bridge else 0.0,
            "stig_cited_ccis_unresolved_in_bridge": n_unknown,
            "unresolved_ccis": unknown,
            "note": "unresolved CCIs are STIG-cited but absent from cci_bridge "
                    "(DISA list lag or r4-only) — a gap detector, informational; "
                    "STIG releases can lead CCI-list updates. Never dropped.",
            "human_review_required": True,
        }
        if args.format == "json":
            print(_json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for k in ("stigs", "rules", "cci_citations", "distinct_ccis_exercised",
                      "cci_bridge_total", "cci_bridge_exercised_by_stig",
                      "cci_bridge_coverage_pct", "stig_cited_ccis_unresolved_in_bridge"):
                print(f"{k:<38} {result[k]}")
            if unknown:
                print(f"unresolved: {', '.join(unknown[:30])}"
                      + (" …" if len(unknown) > 30 else ""))
        return 0

    # --cci CCI-000068: which STIGs/rules exercise a CCI
    if getattr(args, "cci", None):
        cci = args.cci.strip().upper()
        rows = conn.execute(
            "SELECT stig_id, group_id, rule_id, version_id, severity FROM stig_rules "
            "WHERE ccis LIKE ? ORDER BY stig_id, group_id",
            (f'%"{cci}"%',)).fetchall()
        usage = conn.execute(
            "SELECT n_stigs, n_rules, in_bridge FROM stig_cci_usage WHERE cci_id=?",
            (cci,)).fetchone()
        cols = ["stig_id", "group_id", "rule_id", "version_id", "severity"]
        if args.format == "json":
            print(_json.dumps({
                "cci_id": cci,
                "n_stigs": usage[0] if usage else 0,
                "n_rules": usage[1] if usage else 0,
                "in_cci_bridge": bool(usage[2]) if usage else False,
                "exercising_rules": [dict(zip(cols, r)) for r in rows][:500],
                "human_review_required": True,
            }, indent=2, ensure_ascii=False))
        else:
            if usage:
                print(f"{cci}: exercised by {usage[0]} STIG(s), {usage[1]} rule(s); "
                      f"in cci_bridge={bool(usage[2])}\n")
            _output([dict(zip(cols, r)) for r in rows[:200]], args.format, cols)
        return 0

    # --stig <id>: one STIG's rules + CCIs + resolved controls
    if getattr(args, "stig", None):
        st, sv = resolve_stig_id(conn, args.stig)
        if st != "ok":
            print(f"[input error] {sv if isinstance(sv, str) else 'ambiguous: ' + ', '.join(sv[:20])}",
                  file=sys.stderr)
            return 1
        cat = conn.execute(
            "SELECT stig_id, title, version, release, benchmark_date, type, rule_count, "
            "distinct_ccis, trackr_title, source FROM stig_catalog WHERE stig_id=?",
            (sv,)).fetchone()
        catcols = ["stig_id", "title", "version", "release", "benchmark_date", "type",
                   "rule_count", "distinct_ccis", "trackr_title", "source"]
        rules = conn.execute(
            "SELECT group_id, rule_id, version_id, severity, title, ccis FROM stig_rules "
            "WHERE stig_id=? ORDER BY group_id", (sv,)).fetchall()
        rulecols = ["group_id", "rule_id", "version_id", "severity", "title", "ccis"]
        if args.format == "json":
            print(_json.dumps({
                "catalog": dict(zip(catcols, cat)),
                "rules": [{**dict(zip(rulecols, r)),
                           "ccis": _json.loads(r[5] or "[]")} for r in rules],
                "human_review_required": True,
            }, indent=2, ensure_ascii=False))
        else:
            print("  ".join(f"{c}={v}" for c, v in zip(catcols, cat)) + "\n")
            _output([dict(zip(rulecols, r)) for r in rules], args.format, rulecols)
        return 0

    # --list [--filter]: the catalog (default)
    flt = getattr(args, "filter", None)
    if flt:
        rows = conn.execute(
            "SELECT stig_id, title, version, release, benchmark_date, rule_count, distinct_ccis "
            "FROM stig_catalog WHERE stig_id LIKE ? OR title LIKE ? ORDER BY stig_id",
            (f"%{flt}%", f"%{flt}%")).fetchall()
    else:
        rows = conn.execute(
            "SELECT stig_id, title, version, release, benchmark_date, rule_count, distinct_ccis "
            "FROM stig_catalog ORDER BY stig_id").fetchall()
    cols = ["stig_id", "title", "version", "release", "benchmark_date", "rule_count", "distinct_ccis"]
    _output([dict(zip(cols, r)) for r in rows], args.format, cols)
    return 0


def resolve_stig_id(conn, name: str):
    """('ok', stig_id) | ('err', msg) | ('err', [candidates]) — a `stig` subcommand
    thin wrapper over spine_overlap.resolve_stig (accepts bare or stig:-prefixed)."""
    import spine_overlap  # type: ignore
    probe = name if name.strip().lower().startswith("stig:") else f"stig:{name}"
    kind, val = spine_overlap.resolve_stig(conn, probe)
    if kind == "ok":
        return ("ok", val)
    if kind == "ambiguous":
        return ("err", val)
    return ("err", f"no STIG matches '{name}'")


def cmd_olir_hub(args, conn: sqlite3.Connection) -> int:
    """OLIR-hub composed edges: third-party control -> CSF 2.0 -> 800-53 r5.

    A query-surface / on-demand tier — these edges are composed through the CSF 2.0
    hub from OLIR sets NIST publishes in the CPRT element graphs, and each cites two
    real informative references. They never enter the precomputed matrix / master."""
    have = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name='olir_hub_edges'").fetchone()
    if not have:
        print("[ERROR] olir_hub_edges table absent (rebuild grc.db)", file=sys.stderr)
        return 1
    # --coverage: per-framework tallies
    if getattr(args, "coverage", False):
        rows = conn.execute(
            "SELECT framework, COUNT(*), COUNT(DISTINCT native_id), COUNT(DISTINCT r5_control) "
            "FROM olir_hub_edges GROUP BY framework ORDER BY framework").fetchall()
        result = {
            "tool": "dbz-olir-hub",
            "note": "third-party -> CSF 2.0 -> 800-53 r5 edges composed via the CSF 2.0 hub; "
                    "each edge cites two OLIR references (hop1 third-party->CSF2, hop2 CSF2->800-53). "
                    "Query-surface tier: never in framework_projection / overlap_matrix / master_mappings.",
            "by_framework": [{"framework": r[0], "edges": r[1], "distinct_natives": r[2],
                              "distinct_controls": r[3]} for r in rows],
            "total_edges": conn.execute("SELECT COUNT(*) FROM olir_hub_edges").fetchone()[0],
            "human_review_required": True,
        }
        if args.format == "json":
            print(json.dumps(result, indent=2))
        else:
            print(f"OLIR-hub composed edges — total {result['total_edges']}")
            for r in result["by_framework"]:
                print(f"  {r['framework']:24} {r['edges']:5} edges  "
                      f"{r['distinct_natives']:4} natives -> {r['distinct_controls']:4} controls")
        return 0
    # --native <id>: which 800-53 controls a specific third-party control reaches
    if getattr(args, "native", None):
        rows = conn.execute(
            "SELECT framework, native_id, csf2_id, r5_control, source_ref_a, source_ref_b "
            "FROM olir_hub_edges WHERE native_id=? ORDER BY framework, csf2_id, r5_control",
            (args.native,)).fetchall()
        cols = ["framework", "native_id", "csf2_id", "r5_control", "source_ref_a", "source_ref_b"]
        out = [dict(zip(cols, r)) for r in rows]
        if args.format == "json":
            print(json.dumps({"tool": "dbz-olir-hub", "native": args.native, "edges": out,
                              "human_review_required": True}, indent=2))
        else:
            for r in out:
                print(f"  {r['native_id']} [{r['framework']}] via {r['csf2_id']} -> {r['r5_control']}")
        return 0
    # default / --framework: reach for a framework (control -> {controls})
    fw = getattr(args, "framework", None)
    q = "SELECT framework, native_id, r5_control FROM olir_hub_edges"
    params: tuple = ()
    if fw:
        q += " WHERE framework=?"
        params = (fw,)
    q += " ORDER BY framework, native_id, r5_control"
    rows = conn.execute(q, params).fetchall()
    if args.format == "json":
        print(json.dumps({"tool": "dbz-olir-hub", "framework": fw,
                          "edges": [{"framework": r[0], "native_id": r[1], "r5_control": r[2]} for r in rows],
                          "human_review_required": True}, indent=2))
    else:
        for r in rows:
            print(f"  {r[0]:24} {r[1]:10} -> {r[2]}")
    return 0


def cmd_fedramp(args, conn: sqlite3.Connection) -> int:
    """FedRAMP Consolidated Rules 2026: KSIs, the official KSI->800-53 crosswalk,
    program rules (MAS/SCN/VDR/...), FedRAMP ODP pins, and CTL guidance.

    Contained query-surface tier (2026 Public Preview) — FedRAMP r5 remains a
    first-class matrix framework; use `overlap` / `master` for baseline overlap."""
    have = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name='fedramp_ksi'").fetchone()
    if not have:
        print("[ERROR] fedramp tables absent (rebuild grc.db)", file=sys.stderr)
        return 1
    if getattr(args, "coverage", False):
        fams = conn.execute(
            "SELECT k.family, k.family_name, COUNT(DISTINCT k.indicator_id), COUNT(e.r5_control) "
            "FROM fedramp_ksi k LEFT JOIN fedramp_ksi_controls e USING (indicator_id) "
            "GROUP BY k.family ORDER BY k.family").fetchall()
        n_rules = conn.execute("SELECT COUNT(*) FROM fedramp_rules").fetchone()[0]
        n_odp = conn.execute("SELECT COUNT(*) FROM fedramp_odp_pins").fetchone()[0]
        n_guid = conn.execute("SELECT COUNT(*) FROM fedramp_ctl_guidance").fetchone()[0]
        result = {"tool": "dbz-fedramp",
                  "lifecycle": "2026_public_preview",
                  "families": [{"family": f, "name": n, "indicators": i, "control_edges": c}
                               for f, n, i, c in fams],
                  "rules": n_rules, "odp_pins": n_odp, "ctl_guidance": n_guid,
                  "note": "KSI->800-53 edges are FedRAMP's own published mapping "
                          "(basis=fedramp_stated). FedRAMP r5 baselines remain the matrix "
                          "framework; this is the new confirmation/monitoring layer.",
                  "human_review_required": True}
        if args.format == "json":
            print(json.dumps(result, indent=2))
        else:
            for f in result["families"]:
                print(f"  {f['family']:8} {f['name']:38} {f['indicators']:3} indicators  {f['control_edges']:4} edges")
            print(f"  rules={n_rules} odp_pins={n_odp} ctl_guidance={n_guid}  [{result['lifecycle']}]")
        return 0
    if getattr(args, "indicator", None):
        row = conn.execute("SELECT indicator_id, family_name, name, statement, status "
                           "FROM fedramp_ksi WHERE indicator_id=?", (args.indicator,)).fetchone()
        if not row:
            print(f"[ERROR] unknown indicator {args.indicator}", file=sys.stderr)
            return 1
        ctrls = [r[0] for r in conn.execute(
            "SELECT r5_control FROM fedramp_ksi_controls WHERE indicator_id=? ORDER BY r5_control",
            (args.indicator,))]
        out = {"tool": "dbz-fedramp", "indicator": row[0], "family": row[1], "name": row[2],
               "statement": row[3], "status": row[4], "controls": ctrls,
               "human_review_required": True}
        print(json.dumps(out, indent=2) if args.format == "json"
              else f"{row[0]} [{row[1]}] {row[2]}\n  {row[3]}\n  controls: {', '.join(ctrls)}")
        return 0
    if getattr(args, "control", None):
        rows = conn.execute(
            "SELECT e.indicator_id, k.name FROM fedramp_ksi_controls e "
            "JOIN fedramp_ksi k USING (indicator_id) WHERE e.r5_control=? ORDER BY e.indicator_id",
            (args.control.upper(),)).fetchall()
        out = {"tool": "dbz-fedramp", "control": args.control.upper(),
               "indicators": [{"indicator_id": r[0], "name": r[1]} for r in rows],
               "human_review_required": True}
        if args.format == "json":
            print(json.dumps(out, indent=2))
        else:
            for r in rows:
                print(f"  {r[0]:16} {r[1]}")
        return 0
    if getattr(args, "rules", None) is not None:
        q = ("SELECT rule_id, family, pipeline, subgroup, force, name, statement "
             "FROM fedramp_rules")
        params: tuple = ()
        if args.rules:
            q += " WHERE family=?"
            params = (args.rules.upper(),)
        q += " ORDER BY rule_id, pipeline, subgroup"
        rows = conn.execute(q, params).fetchall()
        cols = ["rule_id", "family", "pipeline", "subgroup", "force", "name", "statement"]
        out = [dict(zip(cols, r)) for r in rows]
        if args.format == "json":
            print(json.dumps({"tool": "dbz-fedramp", "rules": out,
                              "human_review_required": True}, indent=2))
        else:
            for r in out:
                print(f"  {r['rule_id']:16} [{r['pipeline']:4}] {r['force']:6} {r['name']}")
        return 0
    if getattr(args, "ksi", None) is not None:
        q = "SELECT indicator_id, family, name, status FROM fedramp_ksi"
        params = ()
        if args.ksi:
            q += " WHERE family=? OR family='KSI-'||?"
            params = (args.ksi.upper(), args.ksi.upper())
        q += " ORDER BY indicator_id"
        rows = conn.execute(q, params).fetchall()
        if args.format == "json":
            print(json.dumps({"tool": "dbz-fedramp",
                              "ksi": [{"indicator_id": r[0], "family": r[1], "name": r[2],
                                       "status": r[3]} for r in rows],
                              "human_review_required": True}, indent=2))
        else:
            for r in rows:
                print(f"  {r[0]:16} [{r[1]}] {r[2]} ({r[3]})")
        return 0
    print("[ERROR] pass --coverage, --ksi, --indicator, --control, or --rules", file=sys.stderr)
    return 1


def cmd_800_63b(args, conn: sqlite3.Connection) -> int:
    """Query NIST SP 800-63B digital identity requirements by section, AAL level, or control."""
    conditions = []
    params: list = []

    if getattr(args, "section", None):
        conditions.append("section LIKE ?")
        params.append(f"{args.section}%")
    if getattr(args, "aal", None):
        conditions.append("aal_level = ?")
        params.append(args.aal.upper())
    if getattr(args, "control", None):
        conditions.append("nist_800_53_controls LIKE ?")
        params.append(f'%"{args.control.upper()}%')
    if getattr(args, "keyword", None):
        conditions.append("(title LIKE ? OR text LIKE ?)")
        params.extend([f"%{args.keyword}%", f"%{args.keyword}%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT requirement_id, section, aal_level, title, nist_800_53_controls, cci_provenance
        FROM nist_800_63b_requirements {where}
        ORDER BY section, requirement_id
        LIMIT 100
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["requirement_id", "section", "aal_level", "title", "nist_800_53_controls", "cci_provenance"]
    _output(results, args.format, cols)
    return 0


def cmd_fips(args, conn: sqlite3.Connection) -> int:
    """Query FIPS 140-3/140-2 CMVP validated cryptographic modules."""
    conditions = []
    params: list = []

    if getattr(args, "vendor", None):
        conditions.append("vendor LIKE ?")
        params.append(f"%{args.vendor}%")
    if getattr(args, "level", None):
        conditions.append("level = ?")
        params.append(str(args.level))
    if getattr(args, "status", None):
        conditions.append("status = ?")
        params.append(args.status.lower())
    if getattr(args, "keyword", None):
        conditions.append("(vendor LIKE ? OR module_name LIKE ?)")
        params.extend([f"%{args.keyword}%", f"%{args.keyword}%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT module_id, vendor, module_name, validation_date, level, status
        FROM fips_140_validations {where}
        ORDER BY validation_date DESC, module_id
        LIMIT 100
    """
    rows = conn.execute(sql, params).fetchall()
    results = [dict(r) for r in rows]
    cols = ["module_id", "vendor", "module_name", "validation_date", "level", "status"]
    _output(results, args.format, cols)
    return 0


def cmd_eurlex(args, conn: sqlite3.Connection) -> int:
    """Query EUR-Lex regulatory articles by regulation, article number, or NIST family."""
    conditions = []
    params: list = []

    if getattr(args, "regulation", None):
        conditions.append("regulation_id = ?")
        params.append(args.regulation.lower())

    if getattr(args, "article", None):
        conditions.append("(article_number = ? OR article_id LIKE ?)")
        params.extend([args.article, f'%art{args.article}%'])

    if getattr(args, "family", None):
        conditions.append("nist_families LIKE ?")
        params.append(f'%"{args.family}"%')

    if getattr(args, "keyword", None):
        conditions.append("(title LIKE ? OR text LIKE ?)")
        params.extend([f'%{args.keyword}%', f'%{args.keyword}%'])

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = f"SELECT regulation_id, article_number, title, nist_families FROM eurlex_articles {where} ORDER BY regulation_id, article_number LIMIT 50"
    results = conn.execute(sql, params).fetchall()
    cols = ["regulation_id", "article_number", "title", "nist_families"]
    _output(results, args.format, cols)
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
    _add_overlay(scope); _add_format(scope); _add_db(scope)

    # overlap
    ov = subs.add_parser("overlap", help="CCI / sub-part-anchored overlap between two frameworks")
    ov.add_argument("--framework-a", required=True, metavar="FW_A",
                    help="First framework name (e.g. 'SOC 2')")
    ov.add_argument("--framework-b", required=True, metavar="FW_B",
                    help="Second framework name (e.g. 'ISO 27001/2 (2022)')")
    ov.add_argument("--basis", choices=["auto", "cci", "subpart", "control"], default="auto",
                    help="Spine basis (default: auto = finest available)")
    ov.add_argument("--per-control", action="store_true",
                    help="Include per-control full/partial/none breakdown")
    _add_overlay(ov); _add_format(ov); _add_db(ov)

    # consensus
    cons = subs.add_parser("consensus",
                           help="Cross-source consensus pairs (independent authorities agreeing)")
    cons.add_argument("--framework-a", metavar="FW_A",
                      help="Filter: pair touches this framework (e.g. 'SOC 2 (TSC)')")
    cons.add_argument("--framework-b", metavar="FW_B",
                      help="Filter: pair also touches this framework")
    cons.add_argument("--tier", choices=["strong", "moderate", "single", "all"],
                      default="strong", help="Consensus tier (default: strong = >=3 voters)")
    cons.add_argument("--limit", type=int, default=40)
    _add_format(cons); _add_db(cons)

    # search
    # master (Phase 19)
    mst = subs.add_parser("master",
                          help="Master mapping surface: any framework <-> any framework, tier-arbitrated")
    mst.add_argument("--framework-a", help="pair/scope mode: first framework (alias ok)")
    mst.add_argument("--framework-b", help="pair mode: second framework")
    mst.add_argument("--framework", help="control mode: framework of --control")
    mst.add_argument("--control", help="control mode: one native id (e.g. CC6.1, 164.312(a)(1), AC-2)")
    mst.add_argument("--scope-fedramp", dest="fedramp", help="audit-scope mode: low|moderate|high")
    mst.add_argument("--cui", action="store_true", help="audit-scope mode: CUI-applicable controls")
    mst.add_argument("--privacy", action="store_true", help="audit-scope mode: privacy baseline")
    mst.add_argument("--family", help="audit-scope mode: NIST family filter (e.g. IA)")
    mst.add_argument("--min-tier", choices=list(_MASTER_TIER_ORDER),
                     help="only tiers at or above this rank")
    mst.add_argument("--evidence-state",
                     choices=["oracle_confirmed", "cross_validated",
                              "columns_aligned", "asserted_by_source"],
                     help="filter by the derived corroboration ladder (v3.13)")
    mst.add_argument("--limit", type=int, default=100)
    _add_overlay(mst); _add_format(mst)
    _add_db(mst)

    srch = subs.add_parser("search", help="Full-text search across control text")
    srch.add_argument("--keyword", required=True, help="Search term (e.g. 'multi-factor')")
    srch.add_argument("--scope", metavar="LEVEL",
                      help="Limit to FedRAMP level: low | moderate | high")
    srch.add_argument("--family", metavar="FAM", help="Limit to control family")
    _add_overlay(srch); _add_format(srch); _add_db(srch)

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

    # horizon — anticipated (expected/scheduled) future standard revisions
    hor = subs.add_parser("horizon", help="Anticipated future standard revisions (horizon scanning)")
    hor.add_argument("--overdue", action="store_true", help="past-window or due-for-review records")
    hor.add_argument("--upcoming", type=int, metavar="N", help="the N nearest dated expectations")
    hor.add_argument("--materialized", action="store_true", help="records marked materialized")
    _add_format(hor); _add_db(hor)

    # manifest
    man = subs.add_parser("manifest", help="Show DB build manifest (row counts, sha256)")
    _add_format(man); _add_db(man)

    # kev
    kev = subs.add_parser("kev", help="Look up CISA KEV entries (CVE → NIST families)")
    kev.add_argument("--cve", metavar="CVE_ID", help="CVE ID (e.g. CVE-2021-44228)")
    kev.add_argument("--days", type=int, metavar="N", help="Added in last N days")
    kev.add_argument("--family", metavar="FAM", help="Filter by NIST family (e.g. SI, IA)")
    _add_format(kev); _add_db(kev)

    # cfr
    cfr = subs.add_parser("cfr", help="Query CFR regulatory requirements")
    cfr.add_argument("--part", metavar="PART", help="CFR part (e.g. 45-CFR-164, 16-CFR-314)")
    cfr.add_argument("--section", metavar="SEC", help="Section ID substring (e.g. 164.308)")
    cfr.add_argument("--keyword", metavar="KW", help="Keyword search in title/text")
    cfr.add_argument("--family", metavar="FAM", help="Filter by NIST family")
    _add_format(cfr); _add_db(cfr)

    # attack
    atk = subs.add_parser("attack", help="Query MITRE ATT&CK techniques and NIST 800-53 mappings")
    atk.add_argument("--technique", metavar="TID", help="ATT&CK technique ID (e.g. T1078)")
    atk.add_argument("--name", metavar="NAME", help="Technique name substring")
    atk.add_argument("--tactic", metavar="TACTIC", help="Tactic name substring (e.g. initial-access)")
    atk.add_argument("--control", metavar="CTRL", help="NIST control ID (e.g. AC-2)")
    _add_format(atk); _add_db(atk)

    # edgar
    edg = subs.add_parser("edgar", help="Query SEC EDGAR 8-K cyber incident disclosures")
    edg.add_argument("--company", metavar="NAME", help="Company name substring")
    edg.add_argument("--incident-type", metavar="TYPE", dest="incident_type",
                     help="Incident type (e.g. ransomware, data_breach, unauthorized_access)")
    edg.add_argument("--days", type=int, metavar="N", help="Filed in last N days")
    edg.add_argument("--family", metavar="FAM", help="Filter by NIST family")
    _add_format(edg); _add_db(edg)

    # nvd
    nvd_p = subs.add_parser("nvd", help="Query NVD CVE data (severity, NIST families)")
    nvd_p.add_argument("--cve", metavar="CVE_ID", help="CVE ID (e.g. CVE-2021-44228)")
    nvd_p.add_argument("--severity", metavar="LEVEL",
                       help="Severity: LOW | MEDIUM | HIGH | CRITICAL")
    nvd_p.add_argument("--family", metavar="FAM", help="Filter by NIST family (e.g. SI, IA)")
    _add_format(nvd_p); _add_db(nvd_p)

    # cci
    cci_p = subs.add_parser("cci", help="Query DISA CCI dictionary, definitions, and mapping corroboration")
    cci_p.add_argument("--id", metavar="CCI_ID", help="CCI ID (e.g. CCI-000001)")
    cci_p.add_argument("--control", metavar="CTRL",
                       help="NIST control ID (e.g. AC-2) — shows all CCIs mapping to it")
    cci_p.add_argument("--status", metavar="STATUS", help="CCI status (e.g. draft, deprecated)")
    cci_p.add_argument("--definition", action="store_true",
                       help="show full definition text + native r4/r5 indices + legacy refs")
    cci_p.add_argument("--corroboration", metavar="CCI_ID",
                       help="mapping witnesses + verdict for one CCI (DISA/acasehs/trackr/STIG)")
    cci_p.add_argument("--coverage", action="store_true",
                       help="dictionary completeness + corroboration verdict summary")
    _add_format(cci_p); _add_db(cci_p)

    # stig (application layer)
    stig_p = subs.add_parser("stig",
        help="STIG application layer: catalog, rules, CCI usage, coverage "
             "(for STIG×framework overlap use `overlap stig:<title> × <fw>`)")
    stig_p.add_argument("--list", action="store_true", help="list the STIG catalog (default)")
    stig_p.add_argument("--filter", metavar="SUBSTR", help="filter --list by id/title substring")
    stig_p.add_argument("--stig", metavar="ID", help="one STIG's rules + CCIs (id or title)")
    stig_p.add_argument("--cci", metavar="CCI-NNNNNN", help="which STIGs/rules exercise a CCI")
    stig_p.add_argument("--coverage", action="store_true",
                        help="usage stats + unresolved-CCI gap report")
    _add_format(stig_p); _add_db(stig_p)

    # olir-hub (composed third-party -> CSF2 -> 800-53 edges)
    oh = subs.add_parser("olir-hub",
        help="OLIR-hub composed edges: third-party control -> CSF 2.0 -> 800-53 r5 "
             "(query-surface tier; two OLIR refs per edge)")
    oh.add_argument("--framework", metavar="FW", help="filter by framework (e.g. 'CIS Controls 8.1')")
    oh.add_argument("--native", metavar="ID", help="which 800-53 controls a third-party control id reaches")
    oh.add_argument("--coverage", action="store_true", help="per-framework edge/native/control tallies")
    _add_format(oh); _add_db(oh)

    # fedramp (Consolidated Rules 2026)
    fr = subs.add_parser("fedramp",
        help="FedRAMP Consolidated Rules 2026: KSIs, official KSI->800-53 edges, "
             "program rules, ODP pins (2026 Public Preview layer)")
    fr.add_argument("--coverage", action="store_true", help="per-family KSI/edge tallies + totals")
    fr.add_argument("--ksi", nargs="?", const="", metavar="FAM", help="list indicators (optionally one family, e.g. IAM)")
    fr.add_argument("--indicator", metavar="ID", help="one indicator's statement + 800-53 controls")
    fr.add_argument("--control", metavar="CTRL", help="reverse: which KSIs confirm an 800-53 control")
    fr.add_argument("--rules", nargs="?", const="", metavar="FAM", help="program rules (optionally one family, e.g. MAS, SCN)")
    _add_format(fr); _add_db(fr)

    # 800-63b
    b63 = subs.add_parser("800-63b", help="Query NIST SP 800-63B digital identity requirements")
    b63.add_argument("--section", metavar="SEC", help="Section number (e.g. 4.2, 5.1.1)")
    b63.add_argument("--aal", metavar="LEVEL", help="Authenticator assurance level: AAL1 | AAL2 | AAL3")
    b63.add_argument("--control", metavar="CTRL", help="NIST 800-53 control ID (e.g. IA-2, IA-5)")
    b63.add_argument("--keyword", metavar="KW", help="Keyword search in title or text")
    _add_format(b63); _add_db(b63)

    # fips
    fips_p = subs.add_parser("fips", help="Query FIPS 140-3/140-2 CMVP validated modules")
    fips_p.add_argument("--vendor", metavar="VENDOR", help="Vendor name substring")
    fips_p.add_argument("--level", metavar="LEVEL", help="Security level (1, 2, 3, or 4)")
    fips_p.add_argument("--status", metavar="STATUS", help="Validation status: active | historical | revoked")
    fips_p.add_argument("--keyword", metavar="KW", help="Keyword in vendor or module name")
    _add_format(fips_p); _add_db(fips_p)

    # eurlex
    eur = subs.add_parser("eurlex", help="Query EUR-Lex regulatory articles (GDPR, NIS2, DORA, EU AI Act)")
    eur.add_argument("--regulation", metavar="REG",
                     help="Regulation ID: gdpr | nis2 | dora | eu-ai-act")
    eur.add_argument("--article", metavar="NUM", help="Article number (e.g. 32)")
    eur.add_argument("--family", metavar="FAM", help="Filter by NIST family")
    eur.add_argument("--keyword", metavar="KW", help="Keyword in article title or text")
    _add_format(eur); _add_db(eur)

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
        "consensus": cmd_consensus,
        "master": cmd_master,
        "search": cmd_search,
        "changelog": cmd_changelog,
        "feeds": cmd_feeds,
        "announcements": cmd_announcements,
        "horizon": cmd_horizon,
        "manifest": cmd_manifest,
        "kev": cmd_kev,
        "cfr": cmd_cfr,
        "attack": cmd_attack,
        "edgar": cmd_edgar,
        "nvd": cmd_nvd,
        "cci": cmd_cci,
        "stig": cmd_stig,
        "olir-hub": cmd_olir_hub,
        "fedramp": cmd_fedramp,
        "eurlex": cmd_eurlex,
        "800-63b": cmd_800_63b,
        "fips": cmd_fips,
    }

    fn = cmd_map.get(args.command)
    if not fn:
        print(f"[ERROR] Unknown command: {args.command}", file=sys.stderr)
        return 1

    try:
        return fn(args, conn)
    except AmbiguousFrameworkError as e:
        # Explicit, not incidental: a term that maps to several framework families is
        # reported with its candidates instead of resolved by guessing (phase 35 —
        # 'csf' used to answer HITRUST CSF on this surface and NIST CSF 2.0 on overlap).
        print(f"[input error] {e}", file=sys.stderr)
        for c in e.candidates:
            print(f"    --framework-a {c!r}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
