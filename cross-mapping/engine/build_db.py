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
  - canonical-sources/known_exploited_vulnerabilities.json  (optional; kev_loader.py)
  - canonical-sources/cfr/*.json                           (optional; ecfr_loader.py)
  - canonical-sources/mitre-attack-techniques.json         (optional; attack_stix_loader.py)
  - canonical-sources/edgar-8k-cyber.json                 (optional; edgar_loader.py)
  - canonical-sources/nist-800-63b-requirements.json      (optional; generate_controls_800_63b.py)
  - canonical-sources/fips-cmvp-validations.json          (optional; fips_cmvp_loader.py)

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
import spine_loader  # type: ignore  # overlap spine tables (nist_subparts, cci_bridge, control_odps, …)

REPO_ROOT = _HERE.parent.parent

DEFAULT_CATALOG = REPO_ROOT / "cross-mapping" / "nist-catalog" / "output" / "NIST_800_53_FULL_ALL_FAMILIES.json"
DEFAULT_ER_MAPPINGS_DIR = REPO_ROOT / "cross-mapping" / "core-audit" / "mappings"
DEFAULT_FEED_REGISTRY = REPO_ROOT / "canonical-sources" / "feed_registry.json"
DEFAULT_ANNOUNCEMENTS = REPO_ROOT / "canonical-sources" / "announcements_feed.json"
DEFAULT_CHANGELOG = REPO_ROOT / "canonical-sources" / "framework_changelog.json"
DEFAULT_OUT = REPO_ROOT / "cross-mapping" / "output" / "grc.db"
DEFAULT_MANIFEST = REPO_ROOT / "cross-mapping" / "output" / "grc_manifest.json"

# Optional enrichment sources (loaded if present; skipped silently if absent)
KEV_PATH = REPO_ROOT / "canonical-sources" / "known_exploited_vulnerabilities.json"
ATTACK_PATH = REPO_ROOT / "canonical-sources" / "mitre-attack-techniques.json"
EDGAR_PATH = REPO_ROOT / "canonical-sources" / "edgar-8k-cyber.json"
CFR_DIR = REPO_ROOT / "canonical-sources" / "cfr"
NVD_DIR = REPO_ROOT / "canonical-sources"       # nvd-cve-{date}.json files land here
CCI_PATH = REPO_ROOT / "canonical-sources" / "disa-cci-trackr.json"
EURLEX_DIR = REPO_ROOT / "canonical-sources" / "eurlex"
NIST_800_63B_PATH = REPO_ROOT / "canonical-sources" / "nist-800-63b-requirements.json"
FIPS_CMVP_PATH = REPO_ROOT / "canonical-sources" / "fips-cmvp-validations.json"

# System versioning — bump ENGINE_VERSION on schema changes; never mix with framework versions
ENGINE_VERSION = "1.2.0"
SCHEMA_VERSION = "3.2"   # v3.2: adds overlap spine (nist_subparts, cci_bridge, control_odps)

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
    framework_id          TEXT PRIMARY KEY,
    label                 TEXT,
    authority             TEXT,
    current_version       TEXT,
    last_changed          TEXT,
    check_strategy        TEXT,
    draft_status          TEXT,
    version_signal        TEXT,
    next_expected_version TEXT,
    release_notes_url     TEXT
);

CREATE TABLE IF NOT EXISTS db_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS cisa_kev (
    cve_id             TEXT PRIMARY KEY,
    date_added         TEXT,
    vulnerability_name TEXT,
    affected_product   TEXT,
    short_description  TEXT,
    required_action    TEXT,
    due_date           TEXT,
    nist_families      TEXT  -- JSON array
);
CREATE INDEX IF NOT EXISTS idx_kev_date ON cisa_kev(date_added);

CREATE TABLE IF NOT EXISTS cfr_requirements (
    section_id    TEXT PRIMARY KEY,
    title         TEXT,
    text          TEXT,
    cfr_part      TEXT,
    framework_id  TEXT,
    nist_families TEXT  -- JSON array
);
CREATE INDEX IF NOT EXISTS idx_cfr_part ON cfr_requirements(cfr_part);
CREATE INDEX IF NOT EXISTS idx_cfr_fw   ON cfr_requirements(framework_id);

CREATE TABLE IF NOT EXISTS attack_techniques (
    technique_id   TEXT PRIMARY KEY,
    name           TEXT,
    tactic         TEXT,   -- JSON array of tactic names
    is_subtechnique INTEGER NOT NULL DEFAULT 0,
    parent_id      TEXT,
    nist_controls  TEXT,   -- JSON array of control IDs
    nist_families  TEXT    -- JSON array of family codes (derived)
);
CREATE INDEX IF NOT EXISTS idx_atk_tactic ON attack_techniques(tactic);

CREATE TABLE IF NOT EXISTS edgar_cyber_incidents (
    accession_no   TEXT PRIMARY KEY,
    company_name   TEXT,
    cik            TEXT,
    filed_at       TEXT,
    period_of_report TEXT,
    incident_type  TEXT,
    nist_families  TEXT,   -- JSON array
    classification_confidence TEXT,
    text_snippet   TEXT,
    edgar_url      TEXT
);
CREATE INDEX IF NOT EXISTS idx_edgar_type ON edgar_cyber_incidents(incident_type);
CREATE INDEX IF NOT EXISTS idx_edgar_date ON edgar_cyber_incidents(filed_at);

CREATE TABLE IF NOT EXISTS nvd_cves (
    cve_id        TEXT PRIMARY KEY,
    published     TEXT,
    last_modified TEXT,
    description   TEXT,
    cvss_score    REAL,
    severity      TEXT,
    cwe_ids       TEXT,  -- JSON array
    nist_families TEXT,  -- JSON array
    fetched_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_nvd_severity ON nvd_cves(severity);
CREATE INDEX IF NOT EXISTS idx_nvd_published ON nvd_cves(published);

CREATE TABLE IF NOT EXISTS disa_ccis (
    cci_id         TEXT PRIMARY KEY,
    definition     TEXT,
    type           TEXT,
    status         TEXT,
    nist_rev4_refs TEXT,  -- JSON array of {control_id, ap_acronym}
    nist_rev5_refs TEXT,  -- JSON array
    fetched_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_disa_ccis_status ON disa_ccis(status);

CREATE TABLE IF NOT EXISTS eurlex_articles (
    article_id     TEXT,
    regulation_id  TEXT,
    celex_id       TEXT,
    article_number TEXT,
    title          TEXT,
    text           TEXT,
    nist_families  TEXT,  -- JSON array; keyword-heuristic mapping
    fetched_at     TEXT,
    PRIMARY KEY (regulation_id, article_id)
);
CREATE INDEX IF NOT EXISTS idx_eurlex_regulation ON eurlex_articles(regulation_id);

CREATE TABLE IF NOT EXISTS nist_800_63b_requirements (
    requirement_id       TEXT PRIMARY KEY,
    section              TEXT,
    title                TEXT,
    aal_level            TEXT,
    text                 TEXT,
    nist_800_53_controls TEXT,  -- JSON array
    cci_provenance       TEXT
);
CREATE INDEX IF NOT EXISTS idx_800_63b_section ON nist_800_63b_requirements(section);
CREATE INDEX IF NOT EXISTS idx_800_63b_aal     ON nist_800_63b_requirements(aal_level);

CREATE TABLE IF NOT EXISTS fips_140_validations (
    module_id              TEXT PRIMARY KEY,
    vendor                 TEXT,
    module_name            TEXT,
    validation_date        TEXT,
    level                  TEXT,
    status                 TEXT,
    algorithm_capabilities TEXT,  -- JSON array
    nist_800_53_controls   TEXT,  -- JSON array
    cci_provenance         TEXT,  -- JSON object
    fetched_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_fips_status ON fips_140_validations(status);
CREATE INDEX IF NOT EXISTS idx_fips_level  ON fips_140_validations(level);

-- ── Overlap spine (Phase 1): sub-part inventory + CCI bridge + rekeyed ODPs ────
CREATE TABLE IF NOT EXISTS nist_subparts (
    subpart_id    TEXT PRIMARY KEY,   -- canonical "AC-2 d.1" (or the control id for whole-control)
    r5_control    TEXT NOT NULL,      -- "AC-2"
    path          TEXT,               -- "d.1"  ('' for whole-control)
    ordinal       INTEGER,
    source_file   TEXT,
    source_sheet  TEXT,
    source_row    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_subparts_ctrl ON nist_subparts(r5_control);

CREATE TABLE IF NOT EXISTS cci_bridge (
    cci_id        TEXT NOT NULL,      -- "CCI-000015"
    r5_control    TEXT NOT NULL,      -- "AC-2"
    r5_subpart    TEXT,               -- "AC-2 a" (NULL if only control-level resolvable)
    r4_ref_raw    TEXT,               -- original "AC-2 a" from the index column (provenance)
    source_file   TEXT,
    source_row    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ccibridge_ctrl    ON cci_bridge(r5_control);
CREATE INDEX IF NOT EXISTS idx_ccibridge_subpart ON cci_bridge(r5_subpart);
CREATE INDEX IF NOT EXISTS idx_ccibridge_cci     ON cci_bridge(cci_id);

CREATE TABLE IF NOT EXISTS control_odps (
    odp_id        TEXT NOT NULL,      -- canonical OSCAL id "ac-02_odp.01" (or "<ctrl>_param.NN" fallback)
    control_id    TEXT NOT NULL,      -- "AC-2"
    r5_subpart    TEXT,               -- sub-part it parameterizes (NULL = control-level for now)
    type          TEXT,               -- assignment | selection
    label         TEXT,
    ordinal       INTEGER,
    rekey_basis   TEXT,               -- oscal_positional_zip | positional_fallback
    PRIMARY KEY (odp_id, control_id)
);
CREATE INDEX IF NOT EXISTS idx_odps_ctrl ON control_odps(control_id);

-- ── Universal projection: any framework native control -> spine coordinate ─────
CREATE TABLE IF NOT EXISTS framework_projection (
    rowid              INTEGER PRIMARY KEY AUTOINCREMENT,
    framework          TEXT NOT NULL,      -- "ISO 27001/2 (2022)"
    native_id          TEXT NOT NULL,      -- "A.5.15"
    r5_control         TEXT NOT NULL,      -- "AC-2"
    r5_subpart         TEXT,               -- "AC-2 d.1" or NULL (control-level)
    cci_id             TEXT,
    odp_id             TEXT,
    relationship       TEXT NOT NULL DEFAULT 'unspecified',      -- equal|subset|superset|intersect|disjoint|unspecified
    relationship_basis TEXT NOT NULL DEFAULT 'derived_cardinality', -- source_stated|derived_cardinality|co_membership
    granularity        TEXT NOT NULL,      -- cci|subpart|control|er|citation
    provenance         TEXT NOT NULL,      -- direct_olir|hitrust_hub|cci_list|cmmc171|cui_overlay|inferred_er_cooccurrence|soc2_tsp_hub|transitive
    confidence         REAL NOT NULL,
    hop_count          INTEGER NOT NULL DEFAULT 1,
    needs_confirmation INTEGER NOT NULL DEFAULT 0,
    source_file        TEXT,
    source_sheet       TEXT,
    source_row         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fp_fw_native ON framework_projection(framework, native_id);
CREATE INDEX IF NOT EXISTS idx_fp_subpart   ON framework_projection(r5_subpart);
CREATE INDEX IF NOT EXISTS idx_fp_control   ON framework_projection(r5_control);
CREATE INDEX IF NOT EXISTS idx_fp_cci       ON framework_projection(cci_id);
CREATE INDEX IF NOT EXISTS idx_fp_fw        ON framework_projection(framework);
CREATE INDEX IF NOT EXISTS idx_fp_prov      ON framework_projection(provenance);

-- ── HITRUST hub raw audit trail (Phase 3): one row per hitrust_id × framework × id ─
CREATE TABLE IF NOT EXISTS hitrust_hub (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    hitrust_id  TEXT NOT NULL,        -- "01.b User Registration"
    framework   TEXT NOT NULL,        -- canonical framework label
    target_id   TEXT NOT NULL,        -- one parsed id from the cell
    source_row  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_hub_fw      ON hitrust_hub(framework, target_id);
CREATE INDEX IF NOT EXISTS idx_hub_hitrust ON hitrust_hub(hitrust_id);
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
            "version_signal": entry.get("version_signal", ""),
            "next_expected_version": entry.get("next_expected_version", ""),
            "release_notes_url": entry.get("release_notes_url", ""),
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
        # fr_watcher.py uses "feed_id" / "agency"; accept both for compatibility
        entry_id = entry.get("entry_id") or entry.get("feed_id", "")
        source_feed = entry.get("source_feed") or entry.get("agency", "")
        if not entry_id:
            continue  # skip entries without a usable primary key
        rows.append({
            "entry_id": entry_id,
            "framework_ids": json.dumps(entry.get("framework_ids", [])),
            "title": entry.get("title", ""),
            "published_at": entry.get("published_at"),
            "url": entry.get("url", ""),
            "source_feed": source_feed,
            "change_type": entry.get("change_type", ""),
            "human_reviewed": _bool(entry.get("human_reviewed", False)),
        })
    return rows


def load_kev_data(path: Path) -> list[dict]:
    """Load CISA KEV enriched JSON; return rows for cisa_kev table."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for v in doc.get("vulnerabilities", []):
        rows.append({
            "cve_id": v.get("cveID") or v.get("cve_id", ""),
            "date_added": v.get("dateAdded", ""),
            "vulnerability_name": v.get("vulnerabilityName", ""),
            "affected_product": v.get("product", ""),
            "short_description": v.get("shortDescription", ""),
            "required_action": v.get("requiredAction", ""),
            "due_date": v.get("dueDate", ""),
            "nist_families": json.dumps(v.get("nist_families", [])),
        })
    return rows


def load_cfr_data(cfr_dir: Path) -> list[dict]:
    """Load structured CFR requirement JSON files from cfr/ directory."""
    if not cfr_dir.exists():
        return []
    rows = []
    for f in sorted(cfr_dir.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        framework_id = doc.get("_framework_id", "")
        cfr_part = doc.get("_cfr_part", "")
        for req in doc.get("requirements", []):
            rows.append({
                "section_id": req.get("section_id", ""),
                "title": req.get("title", ""),
                "text": req.get("text", ""),
                "cfr_part": cfr_part or req.get("cfr_part", ""),
                "framework_id": framework_id,
                "nist_families": json.dumps(req.get("nist_families", [])),
            })
    return rows


def load_attack_data(path: Path) -> list[dict]:
    """Load MITRE ATT&CK technique JSON; return rows for attack_techniques table."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for t in doc.get("techniques", []):
        nist_controls = t.get("nist_controls", [])  # attack_stix_loader.py writes "nist_controls"
        # Derive family codes from control IDs (e.g. "AC-2" → "AC")
        families = sorted({c.split("-")[0] for c in nist_controls if "-" in c})
        rows.append({
            "technique_id": t.get("technique_id", ""),
            "name": t.get("name", ""),
            "tactic": json.dumps(t.get("tactics", t.get("tactic", []))),
            "is_subtechnique": 1 if t.get("is_subtechnique") else 0,
            "parent_id": t.get("parent_id", "") or "",
            "nist_controls": json.dumps(nist_controls),
            "nist_families": json.dumps(families),
        })
    return rows


def load_edgar_data(path: Path) -> list[dict]:
    """Load SEC EDGAR 8-K cyber disclosure JSON; return rows for edgar_cyber_incidents table."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for d in doc.get("disclosures", []):
        rows.append({
            "accession_no": d.get("accession_no", ""),
            "company_name": d.get("company_name", ""),
            "cik": d.get("cik", ""),
            "filed_at": d.get("filed_at", ""),
            "period_of_report": d.get("period_of_report", ""),
            "incident_type": d.get("incident_type", ""),
            "nist_families": json.dumps(d.get("nist_families", [])),
            "classification_confidence": d.get("classification_confidence", ""),
            "text_snippet": d.get("text_snippet", ""),
            "edgar_url": d.get("edgar_url", ""),
        })
    return rows


def load_nvd_data(nvd_dir: Path) -> list[dict]:
    """Load NVD CVE JSON files (nvd-cve-{date}.json) from nvd_dir."""
    rows = []
    import glob as _glob
    for f in sorted(_glob.glob(str(nvd_dir / "nvd-cve-*.json"))):
        try:
            doc = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        fetched_at = doc.get("metadata", {}).get("generated_at", "")
        for cve in doc.get("cves", []):
            rows.append({
                "cve_id":        cve.get("cve_id", ""),
                "published":     cve.get("published", ""),
                "last_modified": cve.get("last_modified", ""),
                "description":   cve.get("description", ""),
                "cvss_score":    cve.get("cvss_score"),
                "severity":      cve.get("severity", ""),
                "cwe_ids":       json.dumps(cve.get("cwe_ids", [])),
                "nist_families": json.dumps(cve.get("nist_families", [])),
                "fetched_at":    fetched_at,
            })
    return rows


def load_cci_data(cci_path: Path) -> list[dict]:
    """Load DISA CCI Trackr JSON; return rows for disa_ccis table."""
    if not cci_path.exists():
        return []
    doc = json.loads(cci_path.read_text(encoding="utf-8"))
    rows = []
    fetched_at = doc.get("fetched_at", "")
    for cci in doc.get("ccis", []):
        rows.append({
            "cci_id":         cci.get("cci_id") or cci.get("id", ""),
            "definition":     cci.get("definition", ""),
            "type":           cci.get("type", ""),
            "status":         cci.get("status", ""),
            "nist_rev4_refs": json.dumps(cci.get("nist_rev4_refs", [])),
            "nist_rev5_refs": json.dumps(cci.get("nist_rev5_refs", [])),
            "fetched_at":     fetched_at,
        })
    return rows


def load_nist800_63b_data(path: Path) -> list[dict]:
    """Load NIST SP 800-63B requirements JSON; return rows for nist_800_63b_requirements table."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for req in doc.get("requirements", []):
        rows.append({
            "requirement_id":       req.get("requirement_id", ""),
            "section":              req.get("section", ""),
            "title":                req.get("title", ""),
            "aal_level":            req.get("aal_level", ""),
            "text":                 req.get("text", ""),
            "nist_800_53_controls": json.dumps(req.get("nist_800_53_controls", [])),
            "cci_provenance":       req.get("cci_provenance", ""),
        })
    return rows


def load_fips_cmvp_data(path: Path) -> list[dict]:
    """Load FIPS CMVP validated modules JSON; return rows for fips_140_validations table."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for mod in doc.get("modules", []):
        rows.append({
            "module_id":              mod.get("module_id", ""),
            "vendor":                 mod.get("vendor", ""),
            "module_name":            mod.get("module_name", ""),
            "validation_date":        mod.get("validation_date", ""),
            "level":                  mod.get("level", ""),
            "status":                 mod.get("status", ""),
            "algorithm_capabilities": mod.get("algorithm_capabilities", "[]"),
            "nist_800_53_controls":   mod.get("nist_800_53_controls", "[]"),
            "cci_provenance":         mod.get("cci_provenance", "{}"),
            "fetched_at":             mod.get("fetched_at", ""),
        })
    return rows


def load_eurlex_data(eurlex_dir: Path) -> list[dict]:
    """Load EUR-Lex article JSON files from eurlex_dir."""
    if not eurlex_dir.exists():
        return []
    rows = []
    for f in sorted(eurlex_dir.glob("*-articles.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        reg_id = doc.get("metadata", {}).get("regulation_id", f.stem.replace("-articles", ""))
        celex_id = doc.get("_celex_id") or doc.get("metadata", {}).get("celex_id", "")
        fetched_at = doc.get("metadata", {}).get("generated_at", "")
        for art in doc.get("articles", []):
            rows.append({
                "article_id":     art.get("article_id", ""),
                "regulation_id":  reg_id,
                "celex_id":       celex_id,
                "article_number": art.get("article_number", ""),
                "title":          art.get("title", ""),
                "text":           art.get("text", ""),
                "nist_families":  json.dumps(art.get("nist_families", [])),
                "fetched_at":     fetched_at,
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
    kev_path: Path = KEV_PATH,
    attack_path: Path = ATTACK_PATH,
    edgar_path: Path = EDGAR_PATH,
    cfr_dir: Path = CFR_DIR,
    nvd_dir: Path = NVD_DIR,
    cci_path: Path = CCI_PATH,
    eurlex_dir: Path = EURLEX_DIR,
    nist_800_63b_path: Path = NIST_800_63B_PATH,
    fips_cmvp_path: Path = FIPS_CMVP_PATH,
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

    # 0. Stamp build metadata (system versioning — distinct from framework versioning)
    from datetime import datetime, timezone as _tz
    feed_count = 0
    if feed_registry_path.exists():
        try:
            feed_count = len(json.loads(feed_registry_path.read_text()).get("feeds", {}))
        except Exception:
            pass
    db_meta = [
        ("engine_version", ENGINE_VERSION),
        ("schema_version", SCHEMA_VERSION),
        ("built_at", datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("feed_registry_entry_count", str(feed_count)),
    ]
    conn.executemany("INSERT OR REPLACE INTO db_metadata VALUES (?,?)", db_meta)
    conn.commit()

    # 1. Controls + enhancements + parameters + unified_mappings
    print(f"\n[1/15] Loading catalog: {catalog_path.name}")
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

    # 1b. Overlap spine — sub-part inventory + CCI bridge + rekeyed ODPs
    print("\n[1b] Loading overlap spine (nist_subparts, cci_bridge, control_odps)")
    catalog_ids = {r["nist_id"] for r in ctrl_rows} | {r["id"] for r in enh_rows}
    cci_bridge_rows, spine_disa_rows, cci_stats = spine_loader.load_cci_bridge(catalog_ids)
    subpart_rows = spine_loader.load_nist_subparts(catalog_ids, cci_bridge_rows)
    odp_rows, odp_stats = spine_loader.load_control_odps(param_rows)
    print(f"  cci_bridge: {cci_stats}")
    print(f"  control_odps: {odp_stats}")

    _executemany_chunked(conn, """
        INSERT OR IGNORE INTO nist_subparts
            (subpart_id, r5_control, path, ordinal, source_file, source_sheet, source_row)
        VALUES (:subpart_id, :r5_control, :path, :ordinal, :source_file, :source_sheet, :source_row)
    """, subpart_rows, "nist_subparts")

    _executemany_chunked(conn, """
        INSERT INTO cci_bridge (cci_id, r5_control, r5_subpart, r4_ref_raw, source_file, source_row)
        VALUES (:cci_id, :r5_control, :r5_subpart, :r4_ref_raw, :source_file, :source_row)
    """, cci_bridge_rows, "cci_bridge")

    _executemany_chunked(conn, """
        INSERT OR IGNORE INTO control_odps
            (odp_id, control_id, r5_subpart, type, label, ordinal, rekey_basis)
        VALUES (:odp_id, :control_id, :r5_subpart, :type, :label, :ordinal, :rekey_basis)
    """, odp_rows, "control_odps")

    # Populate disa_ccis from the CCI xlsx (real data; the Trackr JSON step below
    # will REPLACE/augment these if that source is present).
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO disa_ccis
            (cci_id, definition, type, status, nist_rev4_refs, nist_rev5_refs, fetched_at)
        VALUES (:cci_id, :definition, :type, :status, :nist_rev4_refs, :nist_rev5_refs, :fetched_at)
    """, spine_disa_rows, "disa_ccis")

    # Framework projection edges — Phase 2: NIST 800-53 <-> ISO 27001 via the OLIR.
    olir_edges, olir_stats = spine_loader.load_olir_projection(catalog_ids)
    print(f"  olir projection: edges={olir_stats['edges']} unresolved_focal={olir_stats['unresolved_focal']}")
    _executemany_chunked(conn, """
        INSERT INTO framework_projection
            (framework, native_id, r5_control, r5_subpart, cci_id, odp_id,
             relationship, relationship_basis, granularity, provenance, confidence,
             hop_count, needs_confirmation, source_file, source_sheet, source_row)
        VALUES
            (:framework, :native_id, :r5_control, :r5_subpart, :cci_id, :odp_id,
             :relationship, :relationship_basis, :granularity, :provenance, :confidence,
             :hop_count, :needs_confirmation, :source_file, :source_sheet, :source_row)
    """, olir_edges, "framework_projection")

    # Phase 3: HITRUST hub — SOC 2 / ISO / HIPAA / GDPR / CMMC / FedRAMP / CIS / 800-171.
    hub_rows, hub_edges, hub_stats = spine_loader.load_hitrust_hub(catalog_ids)
    print(f"  hitrust hub: frameworks={len(hub_stats['frameworks'])} edges={hub_stats['edges']} "
          f"nist_parse_incomplete={hub_stats['nist_parse_incomplete']}")
    _executemany_chunked(conn, """
        INSERT INTO hitrust_hub (hitrust_id, framework, target_id, source_row)
        VALUES (:hitrust_id, :framework, :target_id, :source_row)
    """, hub_rows, "hitrust_hub")
    _executemany_chunked(conn, """
        INSERT INTO framework_projection
            (framework, native_id, r5_control, r5_subpart, cci_id, odp_id,
             relationship, relationship_basis, granularity, provenance, confidence,
             hop_count, needs_confirmation, source_file, source_sheet, source_row)
        VALUES
            (:framework, :native_id, :r5_control, :r5_subpart, :cci_id, :odp_id,
             :relationship, :relationship_basis, :granularity, :provenance, :confidence,
             :hop_count, :needs_confirmation, :source_file, :source_sheet, :source_row)
    """, hub_edges, "framework_projection")

    conn.commit()

    # 2. ER crosswalk data
    print(f"\n[2/15] Loading ER crosswalk CSVs from {er_dir.name}/")
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
    print(f"\n[3/15] Loading feed registry: {feed_registry_path.name}")
    reg_rows = load_framework_registry(feed_registry_path)
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO framework_registry
            (framework_id, label, authority, current_version, last_changed, check_strategy, draft_status,
             version_signal, next_expected_version, release_notes_url)
        VALUES
            (:framework_id, :label, :authority, :current_version, :last_changed, :check_strategy, :draft_status,
             :version_signal, :next_expected_version, :release_notes_url)
    """, reg_rows, "framework_registry")
    conn.commit()

    # 4. Changelog
    print(f"\n[4/15] Loading changelog: {changelog_path.name}")
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
    print(f"\n[5/15] Loading announcements: {announcements_path.name}")
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

    # 6. CISA KEV catalog
    print(f"\n[6/15] Loading CISA KEV: {kev_path.name}")
    kev_rows = load_kev_data(kev_path)
    if kev_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO cisa_kev
                (cve_id, date_added, vulnerability_name, affected_product,
                 short_description, required_action, due_date, nist_families)
            VALUES
                (:cve_id, :date_added, :vulnerability_name, :affected_product,
                 :short_description, :required_action, :due_date, :nist_families)
        """, kev_rows, "cisa_kev")
    else:
        print(f"  cisa_kev: 0 rows (run kev_loader.py to populate)")
    conn.commit()

    # 7. CFR requirements
    print(f"\n[7/15] Loading CFR requirements from {cfr_dir.name}/")
    cfr_rows = load_cfr_data(cfr_dir)
    if cfr_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO cfr_requirements
                (section_id, title, text, cfr_part, framework_id, nist_families)
            VALUES
                (:section_id, :title, :text, :cfr_part, :framework_id, :nist_families)
        """, cfr_rows, "cfr_requirements")
    else:
        print(f"  cfr_requirements: 0 rows (run ecfr_loader.py to populate)")
    conn.commit()

    # 8. MITRE ATT&CK techniques
    print(f"\n[8/15] Loading ATT&CK techniques: {attack_path.name}")
    atk_rows = load_attack_data(attack_path)
    if atk_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO attack_techniques
                (technique_id, name, tactic, is_subtechnique, parent_id, nist_controls, nist_families)
            VALUES
                (:technique_id, :name, :tactic, :is_subtechnique, :parent_id, :nist_controls, :nist_families)
        """, atk_rows, "attack_techniques")
    else:
        print(f"  attack_techniques: 0 rows (run attack_stix_loader.py to populate)")
    conn.commit()

    # 9. SEC EDGAR cyber incident disclosures
    print(f"\n[9/15] Loading EDGAR disclosures: {edgar_path.name}")
    edgar_rows = load_edgar_data(edgar_path)
    if edgar_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO edgar_cyber_incidents
                (accession_no, company_name, cik, filed_at, period_of_report,
                 incident_type, nist_families, classification_confidence, text_snippet, edgar_url)
            VALUES
                (:accession_no, :company_name, :cik, :filed_at, :period_of_report,
                 :incident_type, :nist_families, :classification_confidence, :text_snippet, :edgar_url)
        """, edgar_rows, "edgar_cyber_incidents")
    else:
        print(f"  edgar_cyber_incidents: 0 rows (run edgar_loader.py to populate)")
    conn.commit()

    # 10. FTS5 population
    print(f"\n[10/15] Building FTS5 index …")
    conn.execute("INSERT INTO controls_fts(controls_fts) VALUES('rebuild')")
    conn.commit()

    # 11. NVD CVE data
    print(f"\n[11/15] Loading NVD CVE data from {nvd_dir.name}/")
    nvd_rows = load_nvd_data(nvd_dir)
    if nvd_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO nvd_cves
                (cve_id, published, last_modified, description, cvss_score,
                 severity, cwe_ids, nist_families, fetched_at)
            VALUES
                (:cve_id, :published, :last_modified, :description, :cvss_score,
                 :severity, :cwe_ids, :nist_families, :fetched_at)
        """, nvd_rows, "nvd_cves")
    else:
        print(f"  nvd_cves: 0 rows (run nvd_api_loader.py to populate)")
    conn.commit()

    # 12. DISA CCI data
    print(f"\n[12/15] Loading DISA CCI data: {cci_path.name}")
    cci_rows = load_cci_data(cci_path)
    if cci_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO disa_ccis
                (cci_id, definition, type, status, nist_rev4_refs, nist_rev5_refs, fetched_at)
            VALUES
                (:cci_id, :definition, :type, :status, :nist_rev4_refs, :nist_rev5_refs, :fetched_at)
        """, cci_rows, "disa_ccis")
    else:
        print(f"  disa_ccis: 0 rows (run cci_trackr_loader.py to populate)")
    conn.commit()

    # 13. EUR-Lex articles
    print(f"\n[13/15] Loading EUR-Lex articles from {eurlex_dir.name}/")
    eurlex_rows = load_eurlex_data(eurlex_dir)
    if eurlex_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO eurlex_articles
                (article_id, regulation_id, celex_id, article_number,
                 title, text, nist_families, fetched_at)
            VALUES
                (:article_id, :regulation_id, :celex_id, :article_number,
                 :title, :text, :nist_families, :fetched_at)
        """, eurlex_rows, "eurlex_articles")
    else:
        print(f"  eurlex_articles: 0 rows (run eurlex_loader.py to populate)")
    conn.commit()

    # 14. NIST SP 800-63B digital identity requirements
    print(f"\n[14/15] Loading NIST SP 800-63B requirements: {nist_800_63b_path.name}")
    b63b_rows = load_nist800_63b_data(nist_800_63b_path)
    if b63b_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO nist_800_63b_requirements
                (requirement_id, section, title, aal_level, text,
                 nist_800_53_controls, cci_provenance)
            VALUES
                (:requirement_id, :section, :title, :aal_level, :text,
                 :nist_800_53_controls, :cci_provenance)
        """, b63b_rows, "nist_800_63b_requirements")
    else:
        print(f"  nist_800_63b_requirements: 0 rows (run generate_controls_800_63b.py to populate)")
    conn.commit()

    # 15. FIPS 140-3/140-2 CMVP validated modules
    print(f"\n[15/15] Loading FIPS CMVP validations: {fips_cmvp_path.name}")
    fips_rows = load_fips_cmvp_data(fips_cmvp_path)
    if fips_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO fips_140_validations
                (module_id, vendor, module_name, validation_date, level, status,
                 algorithm_capabilities, nist_800_53_controls, cci_provenance, fetched_at)
            VALUES
                (:module_id, :vendor, :module_name, :validation_date, :level, :status,
                 :algorithm_capabilities, :nist_800_53_controls, :cci_provenance, :fetched_at)
        """, fips_rows, "fips_140_validations")
    else:
        print(f"  fips_140_validations: 0 rows (run fips_cmvp_loader.py to populate)")
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
                "er_controls", "er_mappings", "framework_registry", "changelog", "announcements",
                "cisa_kev", "cfr_requirements", "attack_techniques", "edgar_cyber_incidents",
                "nvd_cves", "disa_ccis", "eurlex_articles",
                "nist_800_63b_requirements", "fips_140_validations",
                "nist_subparts", "cci_bridge", "control_odps", "framework_projection",
                "hitrust_hub"):
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
