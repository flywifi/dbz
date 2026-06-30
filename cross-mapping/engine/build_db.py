#!/usr/bin/env python3
"""
build_db.py — GRC SQLite Database Builder

Reads all GRC source data and writes cross-mapping/output/grc.db — a local
SQLite database that enables zero-token SQL-style lookups for common queries.

Sources consumed:
  - cross-mapping/nist-catalog/output/NIST_800_53_FULL_ALL_FAMILIES.json
  - cross-mapping/core-audit/mappings/*.csv  (ER crosswalk CSVs)
  - canonical-sources/feed_registry.json
  - canonical-sources/announcements_feed.json
  - canonical-sources/framework_changelog.json

Output:
  - cross-mapping/output/grc.db        (SQLite; gitignored)
  - cross-mapping/output/grc_manifest.json  (row counts, sha256, generated_at)

Usage:
    python3 build_db.py [--catalog PATH] [--out PATH] [--no-vacuum]
    python3 build_db.py  # uses all defaults
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterator

# Import ERCrosswalk from sibling module
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from er_overlap import ERCrosswalk, CSV_FILES  # type: ignore

REPO_ROOT = _HERE.parent.parent

DEFAULT_CATALOG = REPO_ROOT / "cross-mapping" / "nist-catalog" / "output" / "NIST_800_53_FULL_ALL_FAMILIES.json"
DEFAULT_ER_MAPPINGS_DIR = REPO_ROOT / "cross-mapping" / "core-audit" / "mappings"
DEFAULT_FEED_REGISTRY = REPO_ROOT / "canonical-sources" / "feed_registry.json"
DEFAULT_ANNOUNCEMENTS = REPO_ROOT / "canonical-sources" / "announcements_feed.json"
DEFAULT_CHANGELOG = REPO_ROOT / "canonical-sources" / "framework_changelog.json"
DEFAULT_OUT = REPO_ROOT / "cross-mapping" / "output" / "grc.db"
DEFAULT_MANIFEST = REPO_ROOT / "cross-mapping" / "output" / "grc_manifest.json"

CHUNK = 500  # executemany batch size


# ── Schema DDL ────────────────────────────────────────────────────────────────

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS controls (
    nist_id           TEXT PRIMARY KEY,
    family            TEXT NOT NULL,
    title             TEXT,
    text              TEXT,
    discussion        TEXT,
    related_controls  TEXT,
    catalog_source    TEXT,
    generated_at      TEXT,
    privacy_baseline  INTEGER NOT NULL DEFAULT 0,
    baseline_low      INTEGER NOT NULL DEFAULT 0,
    baseline_moderate INTEGER NOT NULL DEFAULT 0,
    baseline_high     INTEGER NOT NULL DEFAULT 0,
    cui_applicable    INTEGER NOT NULL DEFAULT 0,
    framework_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS enhancements (
    id                TEXT PRIMARY KEY,
    base_id           TEXT NOT NULL REFERENCES controls(nist_id),
    title             TEXT,
    text              TEXT,
    discussion        TEXT,
    privacy_baseline  INTEGER NOT NULL DEFAULT 0,
    baseline_low      INTEGER NOT NULL DEFAULT 0,
    baseline_moderate INTEGER NOT NULL DEFAULT 0,
    baseline_high     INTEGER NOT NULL DEFAULT 0,
    cui_applicable    INTEGER NOT NULL DEFAULT 0,
    framework_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS parameters (
    param_id   TEXT NOT NULL,
    control_id TEXT NOT NULL,
    type       TEXT,
    label      TEXT,
    position   INTEGER,
    PRIMARY KEY (param_id, control_id)
);

CREATE TABLE IF NOT EXISTS unified_mappings (
    rowid             INTEGER PRIMARY KEY AUTOINCREMENT,
    control_id        TEXT NOT NULL,
    framework         TEXT NOT NULL,
    framework_version TEXT,
    target_id         TEXT,
    relationship_type TEXT,
    strength          TEXT,
    direction         TEXT,
    mapping_source    TEXT,
    notes             TEXT
);
CREATE INDEX IF NOT EXISTS idx_um_fw_target ON unified_mappings(framework, target_id);
CREATE INDEX IF NOT EXISTS idx_um_ctrl      ON unified_mappings(control_id);
CREATE INDEX IF NOT EXISTS idx_um_rel       ON unified_mappings(relationship_type);

CREATE TABLE IF NOT EXISTS er_controls (
    er_id       TEXT PRIMARY KEY,
    category    TEXT,
    name        TEXT,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS er_mappings (
    rowid      INTEGER PRIMARY KEY AUTOINCREMENT,
    er_id      TEXT NOT NULL REFERENCES er_controls(er_id),
    framework  TEXT NOT NULL,
    native_id  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_er_fw ON er_mappings(framework, native_id);
CREATE INDEX IF NOT EXISTS idx_er_id ON er_mappings(er_id);

CREATE TABLE IF NOT EXISTS framework_registry (
    framework_id    TEXT PRIMARY KEY,
    label           TEXT,
    authority       TEXT,
    current_version TEXT,
    last_changed    TEXT,
    check_strategy  TEXT,
    draft_status    TEXT
);

CREATE TABLE IF NOT EXISTS changelog (
    changelog_id       TEXT PRIMARY KEY,
    framework_id       TEXT,
    version_from       TEXT,
    version_to         TEXT,
    change_date        TEXT,
    controls_added     TEXT,
    controls_withdrawn TEXT,
    controls_renamed   TEXT,
    controls_modified  TEXT,
    human_confirmed    INTEGER NOT NULL DEFAULT 0,
    notes              TEXT
);

CREATE TABLE IF NOT EXISTS announcements (
    entry_id       TEXT PRIMARY KEY,
    framework_ids  TEXT,
    title          TEXT,
    published_at   TEXT,
    url            TEXT,
    source_feed    TEXT,
    change_type    TEXT,
    human_reviewed INTEGER NOT NULL DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS controls_fts USING fts5(
    nist_id UNINDEXED,
    title,
    text,
    discussion,
    content='controls',
    content_rowid='rowid'
);

CREATE VIEW IF NOT EXISTS er_overlap_pairs AS
    SELECT a.framework AS framework_a,
           b.framework AS framework_b,
           a.er_id,
           a.native_id AS native_id_a,
           b.native_id AS native_id_b
    FROM er_mappings a
    JOIN er_mappings b ON a.er_id = b.er_id AND a.framework < b.framework;

CREATE VIEW IF NOT EXISTS baseline_controls AS
    SELECT nist_id, family, title,
           baseline_low, baseline_moderate, baseline_high,
           privacy_baseline, cui_applicable, framework_count
    FROM controls;

CREATE VIEW IF NOT EXISTS reverse_index AS
    SELECT framework, target_id, control_id,
           relationship_type, strength, mapping_source
    FROM unified_mappings
    WHERE target_id IS NOT NULL AND target_id != '';
"""


def _batched(iterable, n: int) -> Iterator[list]:
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= n:
            yield batch
            batch = []
    if batch:
        yield batch


def _bool(val) -> int:
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, int):
        return 1 if val else 0
    if isinstance(val, str):
        return 1 if val.lower() in ("true", "yes", "1") else 0
    return 0


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_catalog(path: Path) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Read the full JSON catalog.
    Returns (ctrl_rows, enh_rows, param_rows, mapping_rows).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    ctrl_rows: list[dict] = []
    enh_rows: list[dict] = []
    param_rows: list[dict] = []
    mapping_rows: list[dict] = []
    seen_params: set[tuple] = set()

    def _add_params(ctrl_id: str, params: list) -> None:
        for p in params or []:
            key = (p.get("id", ""), ctrl_id)
            if key in seen_params:
                continue
            seen_params.add(key)
            param_rows.append({
                "param_id": p.get("id", ""),
                "control_id": ctrl_id,
                "type": p.get("type", ""),
                "label": p.get("label", ""),
                "position": p.get("position"),
            })

    def _add_mappings(ctrl_id: str, mappings: list) -> None:
        for m in mappings or []:
            mapping_rows.append({
                "control_id": ctrl_id,
                "framework": m.get("framework", ""),
                "framework_version": m.get("framework_version", ""),
                "target_id": m.get("control_id", ""),
                "relationship_type": m.get("relationship_type", ""),
                "strength": m.get("strength", ""),
                "direction": m.get("direction", ""),
                "mapping_source": m.get("mapping_source", ""),
                "notes": m.get("notes", ""),
            })

    # Catalog structure: {family → {ctrl_id → record}}
    for family_dict in data.values():
        if not isinstance(family_dict, dict):
            continue
        for ctrl_id, rec in family_dict.items():
            if not isinstance(rec, dict) or not rec.get("id"):
                continue
            bl = rec.get("baselines", {})
            cs = rec.get("compliance_scope", {})
            ctrl_rows.append({
                "nist_id": rec["id"],
                "family": rec.get("family", ""),
                "title": rec.get("title", ""),
                "text": rec.get("text", ""),
                "discussion": rec.get("discussion", ""),
                "related_controls": rec.get("related_controls", ""),
                "catalog_source": rec.get("catalog_source", ""),
                "generated_at": rec.get("generated_at", ""),
                "privacy_baseline": _bool(bl.get("privacy", cs.get("privacy_baseline", False))),
                "baseline_low": _bool(bl.get("low", False)),
                "baseline_moderate": _bool(bl.get("moderate", False)),
                "baseline_high": _bool(bl.get("high", False)),
                "cui_applicable": _bool(cs.get("cui_applicable", False)),
                "framework_count": int(cs.get("framework_count", 0)),
            })
            _add_params(rec["id"], rec.get("parameters", []))
            _add_mappings(rec["id"], rec.get("unified_mappings", []))

            # Enhancements
            for enh in rec.get("enhancements", []):
                if not isinstance(enh, dict) or not enh.get("id"):
                    continue
                ebl = enh.get("baselines", {})
                ecs = enh.get("compliance_scope", {})
                enh_rows.append({
                    "id": enh["id"],
                    "base_id": rec["id"],
                    "title": enh.get("title", ""),
                    "text": enh.get("text", ""),
                    "discussion": enh.get("discussion", ""),
                    "privacy_baseline": _bool(ebl.get("privacy", ecs.get("privacy_baseline", False))),
                    "baseline_low": _bool(ebl.get("low", False)),
                    "baseline_moderate": _bool(ebl.get("moderate", False)),
                    "baseline_high": _bool(ebl.get("high", False)),
                    "cui_applicable": _bool(ecs.get("cui_applicable", False)),
                    "framework_count": int(ecs.get("framework_count", 0)),
                })
                _add_params(enh["id"], enh.get("parameters", []))
                _add_mappings(enh["id"], enh.get("unified_mappings", []))

    return ctrl_rows, enh_rows, param_rows, mapping_rows


def load_er_data(er_dir: Path) -> tuple[list[dict], list[dict]]:
    """
    Load ER crosswalk CSVs. Returns (er_ctrl_rows, er_mapping_rows).
    """
    er_ctrl_rows: list[dict] = []
    er_mapping_rows: list[dict] = []
    seen_er: set[str] = set()

    for label, csv_path in CSV_FILES.items():
        if not csv_path.exists():
            print(f"  [WARN] ER CSV missing: {csv_path}", file=sys.stderr)
            continue
        print(f"  Loading ER CSV: {csv_path.name}")
        try:
            xwalk = ERCrosswalk(csv_path)
        except Exception as e:
            print(f"  [WARN] Failed to parse {csv_path.name}: {e}", file=sys.stderr)
            continue

        for er_id, info in xwalk.er_controls.items():
            if er_id not in seen_er:
                seen_er.add(er_id)
                er_ctrl_rows.append({
                    "er_id": er_id,
                    "category": info.get("category", ""),
                    "name": info.get("name", ""),
                    "source_file": csv_path.name,
                })
            for fw, native_ids in info.get("controls_by_framework", {}).items():
                for nid in native_ids:
                    er_mapping_rows.append({
                        "er_id": er_id,
                        "framework": fw,
                        "native_id": nid,
                    })

    return er_ctrl_rows, er_mapping_rows


def load_framework_registry(path: Path) -> list[dict]:
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for fw_id, entry in doc.get("feeds", {}).items():
        rows.append({
            "framework_id": fw_id,
            "label": entry.get("label", ""),
            "authority": entry.get("authority", ""),
            "current_version": entry.get("current_version", ""),
            "last_changed": entry.get("last_changed", ""),
            "check_strategy": entry.get("check_strategy", ""),
            "draft_status": entry.get("draft_status", ""),
        })
    return rows


def load_changelog(path: Path) -> list[dict]:
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for entry in doc.get("entries", []):
        rows.append({
            "changelog_id": entry.get("changelog_id", ""),
            "framework_id": entry.get("framework_id", ""),
            "version_from": entry.get("version_from"),
            "version_to": entry.get("version_to"),
            "change_date": entry.get("change_date"),
            "controls_added": json.dumps(entry.get("controls_added", [])),
            "controls_withdrawn": json.dumps(entry.get("controls_withdrawn", [])),
            "controls_renamed": json.dumps(entry.get("controls_renamed", [])),
            "controls_modified": json.dumps(entry.get("controls_modified", [])),
            "human_confirmed": _bool(entry.get("human_confirmed", False)),
            "notes": entry.get("notes", ""),
        })
    return rows


def load_announcements(path: Path) -> list[dict]:
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for entry in doc.get("entries", []):
        rows.append({
            "entry_id": entry.get("entry_id", ""),
            "framework_ids": json.dumps(entry.get("framework_ids", [])),
            "title": entry.get("title", ""),
            "published_at": entry.get("published_at"),
            "url": entry.get("url", ""),
            "source_feed": entry.get("source_feed", ""),
            "change_type": entry.get("change_type", ""),
            "human_reviewed": _bool(entry.get("human_reviewed", False)),
        })
    return rows


# ── DB writer ─────────────────────────────────────────────────────────────────

def _executemany_chunked(conn: sqlite3.Connection, sql: str, rows: list, label: str) -> None:
    total = 0
    for batch in _batched(rows, CHUNK):
        conn.executemany(sql, [{k: r[k] for k in r} for r in batch])
        total += len(batch)
    print(f"  {label}: {total} rows")


def build_db(
    catalog_path: Path = DEFAULT_CATALOG,
    er_dir: Path = DEFAULT_ER_MAPPINGS_DIR,
    feed_registry_path: Path = DEFAULT_FEED_REGISTRY,
    announcements_path: Path = DEFAULT_ANNOUNCEMENTS,
    changelog_path: Path = DEFAULT_CHANGELOG,
    out_db: Path = DEFAULT_OUT,
    manifest_path: Path = DEFAULT_MANIFEST,
    vacuum: bool = True,
) -> dict:
    t0 = time.monotonic()
    out_db.parent.mkdir(parents=True, exist_ok=True)

    if out_db.exists():
        out_db.unlink()

    print(f"Building {out_db} …")
    conn = sqlite3.connect(str(out_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Create schema
    conn.executescript(SCHEMA_DDL)
    conn.commit()

    # 1. Controls + enhancements + parameters + unified_mappings
    print(f"\n[1/6] Loading catalog: {catalog_path.name}")
    ctrl_rows, enh_rows, param_rows, mapping_rows = load_catalog(catalog_path)

    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO controls
            (nist_id, family, title, text, discussion, related_controls,
             catalog_source, generated_at, privacy_baseline, baseline_low,
             baseline_moderate, baseline_high, cui_applicable, framework_count)
        VALUES
            (:nist_id, :family, :title, :text, :discussion, :related_controls,
             :catalog_source, :generated_at, :privacy_baseline, :baseline_low,
             :baseline_moderate, :baseline_high, :cui_applicable, :framework_count)
    """, ctrl_rows, "controls")

    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO enhancements
            (id, base_id, title, text, discussion, privacy_baseline,
             baseline_low, baseline_moderate, baseline_high, cui_applicable, framework_count)
        VALUES
            (:id, :base_id, :title, :text, :discussion, :privacy_baseline,
             :baseline_low, :baseline_moderate, :baseline_high, :cui_applicable, :framework_count)
    """, enh_rows, "enhancements")

    _executemany_chunked(conn, """
        INSERT OR IGNORE INTO parameters (param_id, control_id, type, label, position)
        VALUES (:param_id, :control_id, :type, :label, :position)
    """, param_rows, "parameters")

    _executemany_chunked(conn, """
        INSERT INTO unified_mappings
            (control_id, framework, framework_version, target_id, relationship_type,
             strength, direction, mapping_source, notes)
        VALUES
            (:control_id, :framework, :framework_version, :target_id, :relationship_type,
             :strength, :direction, :mapping_source, :notes)
    """, mapping_rows, "unified_mappings")

    conn.commit()

    # 2. ER crosswalk data
    print(f"\n[2/6] Loading ER crosswalk CSVs from {er_dir.name}/")
    er_ctrl_rows, er_mapping_rows = load_er_data(er_dir)

    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO er_controls (er_id, category, name, source_file)
        VALUES (:er_id, :category, :name, :source_file)
    """, er_ctrl_rows, "er_controls")

    _executemany_chunked(conn, """
        INSERT INTO er_mappings (er_id, framework, native_id)
        VALUES (:er_id, :framework, :native_id)
    """, er_mapping_rows, "er_mappings")

    conn.commit()

    # 3. Framework registry
    print(f"\n[3/6] Loading feed registry: {feed_registry_path.name}")
    reg_rows = load_framework_registry(feed_registry_path)
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO framework_registry
            (framework_id, label, authority, current_version, last_changed, check_strategy, draft_status)
        VALUES
            (:framework_id, :label, :authority, :current_version, :last_changed, :check_strategy, :draft_status)
    """, reg_rows, "framework_registry")
    conn.commit()

    # 4. Changelog
    print(f"\n[4/6] Loading changelog: {changelog_path.name}")
    cl_rows = load_changelog(changelog_path)
    if cl_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO changelog
                (changelog_id, framework_id, version_from, version_to, change_date,
                 controls_added, controls_withdrawn, controls_renamed, controls_modified,
                 human_confirmed, notes)
            VALUES
                (:changelog_id, :framework_id, :version_from, :version_to, :change_date,
                 :controls_added, :controls_withdrawn, :controls_renamed, :controls_modified,
                 :human_confirmed, :notes)
        """, cl_rows, "changelog")
    else:
        print("  changelog: 0 rows (empty)")
    conn.commit()

    # 5. Announcements
    print(f"\n[5/6] Loading announcements: {announcements_path.name}")
    ann_rows = load_announcements(announcements_path)
    if ann_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO announcements
                (entry_id, framework_ids, title, published_at, url, source_feed, change_type, human_reviewed)
            VALUES
                (:entry_id, :framework_ids, :title, :published_at, :url, :source_feed, :change_type, :human_reviewed)
        """, ann_rows, "announcements")
    else:
        print("  announcements: 0 rows (empty)")
    conn.commit()

    # 6. FTS5 population
    print(f"\n[6/6] Building FTS5 index …")
    conn.execute("INSERT INTO controls_fts(controls_fts) VALUES('rebuild')")
    conn.commit()

    # ANALYZE + optional VACUUM
    print("\nRunning ANALYZE …")
    conn.execute("ANALYZE")
    conn.commit()
    if vacuum:
        print("Running VACUUM …")
        conn.execute("VACUUM")
        conn.commit()

    # Row counts
    counts = {}
    for tbl in ("controls", "enhancements", "parameters", "unified_mappings",
                "er_controls", "er_mappings", "framework_registry", "changelog", "announcements"):
        row = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
        counts[tbl] = row[0]

    conn.close()

    elapsed = time.monotonic() - t0

    # SHA256 of the DB file
    sha256 = hashlib.sha256(out_db.read_bytes()).hexdigest()

    # Write manifest
    from datetime import datetime, timezone
    manifest = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "db_path": str(out_db),
        "db_sha256": sha256,
        "db_size_bytes": out_db.stat().st_size,
        "elapsed_seconds": round(elapsed, 2),
        "row_counts": counts,
        "sources": {
            "catalog": str(catalog_path),
            "er_dir": str(er_dir),
            "feed_registry": str(feed_registry_path),
            "announcements": str(announcements_path),
            "changelog": str(changelog_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"grc.db built in {elapsed:.1f}s  ({out_db.stat().st_size // 1024} KB)")
    print(f"SHA256: {sha256[:16]}…")
    for tbl, n in counts.items():
        print(f"  {tbl:<22} {n:>8,} rows")
    print(f"Manifest: {manifest_path}")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build the GRC SQLite database from all source data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--catalog", default=str(DEFAULT_CATALOG), metavar="PATH",
                    help="Path to NIST_800_53_FULL_ALL_FAMILIES.json")
    ap.add_argument("--er-dir", default=str(DEFAULT_ER_MAPPINGS_DIR), metavar="PATH",
                    help="Directory containing ER crosswalk CSVs")
    ap.add_argument("--out", default=str(DEFAULT_OUT), metavar="PATH",
                    help="Output path for grc.db")
    ap.add_argument("--no-vacuum", action="store_true",
                    help="Skip VACUUM (faster, larger file)")
    a = ap.parse_args(argv)

    build_db(
        catalog_path=Path(a.catalog),
        er_dir=Path(a.er_dir),
        out_db=Path(a.out),
        vacuum=not a.no_vacuum,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
