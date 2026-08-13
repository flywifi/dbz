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
SCHEMA_VERSION = "3.15"  # v3.15: edge_semantic on master_mappings (what an edge CLAIMS); v3.14: regulatory-provenance columns on anticipated_updates (enum-enforced); v3.13: evidence_state ladder on master_mappings; v3.12: FedRAMP Consolidated Rules 2026; v3.11: olir_hub_edges; v3.10: anticipated_updates

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

CREATE TABLE IF NOT EXISTS anticipated_updates (
    id                TEXT PRIMARY KEY,
    feed_id           TEXT,
    authority         TEXT,
    artifact          TEXT,
    current_version   TEXT,
    expected_type     TEXT,
    lifecycle_stage   TEXT,
    expected_window   TEXT,   -- JSON {earliest,latest,basis} or the string "no_fixed_date"
    confidence        TEXT,   -- high | med | low
    trigger_signal    TEXT,
    detection         TEXT,   -- JSON {url,method,match}
    poll_frequency    TEXT,
    source_urls       TEXT,   -- JSON array
    dependent_of      TEXT,
    status            TEXT,   -- watching | draft_observed | materialized | superseded
    escalate_after_days INTEGER NOT NULL DEFAULT 120,
    last_checked      TEXT,
    last_change_detected TEXT,
    provenance_url    TEXT,   -- v3.14 regulatory-provenance block (nullable on legacy records)
    provenance_retrieved TEXT,
    provenance_verbatim  TEXT,
    support_label     TEXT,   -- WELL_SUPPORTED | CONTESTED | THIN | UNSUPPORTED (framework_vocab)
    terminal_state    TEXT,   -- ORIGIN | ORIGIN_RECOVERED | DEAD_END | ORPHAN_CONFIRMED | CIRCULAR_UNRESOLVED
    notes             TEXT
);
CREATE INDEX IF NOT EXISTS idx_anticipated_status ON anticipated_updates(status);

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
    publishdate    TEXT,           -- CCI publish date from the DISA list
    nist_rev4_refs TEXT,  -- JSON array of raw Rev-4 indices (e.g. "AC-1 a 1")
    nist_rev5_refs TEXT,  -- JSON array of RESOLVED r5 control ids (control-level)
    nist_r5_index  TEXT,  -- JSON array of raw Rev-5 indices (e.g. "AC-1 a 1 (a)")
    legacy_refs    TEXT,  -- JSON {r3:[...legacy Rev-3...], ap:[...800-53A...]}
    fetched_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_disa_ccis_status ON disa_ccis(status);

-- ── CCI↔800-53 mapping corroboration (Phase 22) ───────────────────────────────
-- One row per (cci, r5_control) edge across witnesses. acasehs + trackr are
-- DERIVED republications of the DISA CCI list, so agreement verifies transcription
-- fidelity + surfaces parse-gap candidates — NOT independent semantic authority.
-- STIG usage is the one genuinely independent (application-evidence) witness.
CREATE TABLE IF NOT EXISTS cci_mapping_corroboration (
    cci_id         TEXT NOT NULL,
    r5_control     TEXT NOT NULL,
    in_disa_bridge INTEGER NOT NULL DEFAULT 0,  -- our loader resolved this edge
    disa_basis     TEXT,                         -- r5_native | r4_identity | appj_absorption | legacy_r3_identity
    in_acasehs_r5  INTEGER NOT NULL DEFAULT 0,
    in_acasehs_r4  INTEGER NOT NULL DEFAULT 0,
    in_trackr      INTEGER NOT NULL DEFAULT 0,
    stig_exercised INTEGER NOT NULL DEFAULT 0,   -- CCI cited by >=1 STIG rule (independent)
    verdict        TEXT NOT NULL,                -- confirmed | disa_only | candidate
    witnesses      TEXT,                         -- JSON sorted list
    PRIMARY KEY (cci_id, r5_control)
);
CREATE INDEX IF NOT EXISTS idx_ccicorr_verdict ON cci_mapping_corroboration(verdict);
CREATE INDEX IF NOT EXISTS idx_ccicorr_cci     ON cci_mapping_corroboration(cci_id);

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
    r4_ref_raw    TEXT,               -- original index ref from the source (provenance)
    basis         TEXT,               -- r5_native | r4_identity | appj_absorption | xlsx_legacy
    source_file   TEXT,
    source_row    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ccibridge_ctrl    ON cci_bridge(r5_control);
CREATE INDEX IF NOT EXISTS idx_ccibridge_subpart ON cci_bridge(r5_subpart);
CREATE INDEX IF NOT EXISTS idx_ccibridge_cci     ON cci_bridge(cci_id);

CREATE TABLE IF NOT EXISTS control_odps (
    odp_id        TEXT NOT NULL,      -- canonical OSCAL id "ac-02_odp.01" (or "<ctrl>_param.NN" fallback)
    control_id    TEXT NOT NULL,      -- "AC-2"
    r5_subpart    TEXT,               -- sub-part it parameterizes (NULL = control-level)
    type          TEXT,               -- assignment | selection
    label         TEXT,
    ordinal       INTEGER,
    rekey_basis   TEXT,               -- oscal_positional_zip | positional_fallback
    link_basis    TEXT,               -- oscal_part_insert | deepest_reference | control_scope | crosswalk_reference
    PRIMARY KEY (odp_id, control_id)
);
CREATE INDEX IF NOT EXISTS idx_odps_ctrl ON control_odps(control_id);

-- ── 800-53A assessment objectives (sub-part anchors from the raw OSCAL catalog) ──
CREATE TABLE IF NOT EXISTS assessment_objectives (
    objective_id  TEXT PRIMARY KEY,   -- OSCAL part id "ac-2_obj.d.3-1"
    control_id    TEXT NOT NULL,      -- "AC-2"
    r5_subpart    TEXT,               -- "AC-2 d.3" (NULL = control-level objective)
    label         TEXT,               -- 53A objective label "AC-02d.03[01]"
    prose         TEXT,
    source_file   TEXT,
    source_row    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_objectives_ctrl    ON assessment_objectives(control_id);
CREATE INDEX IF NOT EXISTS idx_objectives_subpart ON assessment_objectives(r5_subpart);

-- ── Cross-source consensus: independent voters agreeing on third-party pairs ───
CREATE TABLE IF NOT EXISTS consensus_edges (
    fw_a               TEXT NOT NULL,
    native_a           TEXT NOT NULL,
    fw_b               TEXT NOT NULL,
    native_b           TEXT NOT NULL,
    votes              INTEGER NOT NULL,     -- distinct independent voters
    tier               TEXT NOT NULL,        -- strong (>=3) | moderate (2) | single
    voters             TEXT,                 -- JSON list of voter names
    evidence           TEXT,                 -- JSON: voter -> [{derivation,strength,source}]
    production_support INTEGER DEFAULT 0,    -- aggregate co-occurrence count (no ids)
    nist_ancestry_overlap INTEGER DEFAULT 0, -- olir+cmmc171 both voted (shared lineage)
    extent             TEXT,                 -- equal|a_subset_b|b_subset_a|intersect|atoms_disjoint|no_spine_footprint
    shared_atoms_count INTEGER,
    shared_atoms       TEXT,                 -- JSON list (capped) of shared spine sub-parts
    text_confirmation  TEXT,                 -- texts_on_file | texts_on_file_licensed | pending_licensed_artifact
    uncertainty_id     TEXT,
    needs_confirmation INTEGER DEFAULT 1,
    PRIMARY KEY (fw_a, native_a, fw_b, native_b)
);
CREATE INDEX IF NOT EXISTS idx_consensus_tier ON consensus_edges(tier);
CREATE INDEX IF NOT EXISTS idx_consensus_fws  ON consensus_edges(fw_a, fw_b);

-- ── Canonical framework label registry (Phase 19) ──────────────────────────────
CREATE TABLE IF NOT EXISTS framework_labels (
    alias      TEXT NOT NULL,   -- label as a surface writes it, or a query shorthand
    surface    TEXT NOT NULL,   -- canonical | alias | distinct
    canonical  TEXT NOT NULL,   -- the one canonical label ("PCI DSS v4.0", ...)
    PRIMARY KEY (alias, surface)
);
CREATE INDEX IF NOT EXISTS idx_fl_canonical ON framework_labels(canonical);

-- ── Master mapping surface (Phase 19): the all-in-one union ────────────────────
-- One row per unordered canonical pair; strongest tier wins the primary row and
-- every losing surface's claim is preserved in `corroboration` (minority report).
CREATE TABLE IF NOT EXISTS master_mappings (
    fw_a               TEXT NOT NULL,   -- canonical labels; (fw_a,native_a) <= (fw_b,native_b)
    native_a           TEXT NOT NULL,
    fw_b               TEXT NOT NULL,
    native_b           TEXT NOT NULL,
    relationship       TEXT NOT NULL DEFAULT 'unspecified',
    relationship_basis TEXT NOT NULL,   -- source_stated|derived_cardinality|co_membership|co_citation|multi_source_consensus|production_cooccurrence
    tier               TEXT NOT NULL,   -- owner_direct|nist_stated|hub|bundled|consensus|production_aggregate
    provenance         TEXT NOT NULL,
    confidence         REAL,            -- NULL for consensus / production_aggregate
    hop_count          INTEGER,
    needs_confirmation INTEGER NOT NULL DEFAULT 1,
    uncertainty_id     TEXT,
    votes              INTEGER,         -- consensus corroboration where present
    production_support INTEGER NOT NULL DEFAULT 0,   -- aggregate counts only, never ids
    shared_anchors     TEXT,            -- JSON capped list of r5 anchors under the pair
    anchor_count       INTEGER,
    corroboration      TEXT,            -- JSON minority report (non-winning surfaces)
    edge_semantic      TEXT NOT NULL DEFAULT 'informs',
                                        -- v3.15: what the edge CLAIMS (orthogonal to
                                        -- confidence/tier): equivalent|supports|
                                        -- co_referenced|informs. Vocabulary + derivation:
                                        -- framework_vocab.json -> edge_semantics
    evidence_state     TEXT NOT NULL DEFAULT 'asserted_by_source',
                                        -- derived ladder (v3.13): oracle_confirmed|cross_validated|columns_aligned|asserted_by_source
    source_ref         TEXT NOT NULL,
    PRIMARY KEY (fw_a, native_a, fw_b, native_b)
);
CREATE INDEX IF NOT EXISTS idx_mm_a    ON master_mappings(fw_a, native_a);
CREATE INDEX IF NOT EXISTS idx_mm_b    ON master_mappings(fw_b, native_b);
CREATE INDEX IF NOT EXISTS idx_mm_tier ON master_mappings(tier);
CREATE INDEX IF NOT EXISTS idx_mm_pair ON master_mappings(fw_a, fw_b);

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
    uncertainty_id     TEXT,               -- stable id for the confirmation ledger
    status             TEXT NOT NULL DEFAULT 'open',  -- open | confirmed | refuted
    source_file        TEXT,
    source_sheet       TEXT,
    source_row         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fp_uid ON framework_projection(uncertainty_id);
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

-- ── ODP assigned values (Phase 4): concrete parameter values a baseline pins ────
CREATE TABLE IF NOT EXISTS odp_values (
    rowid                 INTEGER PRIMARY KEY AUTOINCREMENT,
    control_id            TEXT NOT NULL,     -- "AC-2(2)"
    odp_id                TEXT,              -- canonical ODP id if linkable, else NULL
    baseline              TEXT NOT NULL,     -- "DAAPM (DoD)"
    value_raw             TEXT NOT NULL,     -- "not more than 72 hours"
    value_norm            TEXT NOT NULL,     -- "72 hour"
    value_kind            TEXT,              -- duration|count|frequency
    extraction_confidence REAL NOT NULL,
    needs_confirmation    INTEGER NOT NULL DEFAULT 1,
    source_file           TEXT,
    source_row            INTEGER
);
CREATE INDEX IF NOT EXISTS idx_odpval_ctrl ON odp_values(control_id);
CREATE INDEX IF NOT EXISTS idx_odpval_base ON odp_values(baseline);

-- ── Precomputed pairwise overlap (Phase 5) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS overlap_matrix (
    framework_a        TEXT NOT NULL,
    framework_b        TEXT NOT NULL,   -- framework_a < framework_b lexicographically
    basis              TEXT NOT NULL,   -- cci | subpart | control | inferred_er | none
    shared_count       INTEGER NOT NULL DEFAULT 0,
    a_count            INTEGER NOT NULL DEFAULT 0,
    b_count            INTEGER NOT NULL DEFAULT 0,
    jaccard_pct        REAL NOT NULL DEFAULT 0,
    a_covers_b_pct     REAL NOT NULL DEFAULT 0,
    b_covers_a_pct     REAL NOT NULL DEFAULT 0,
    confidence         REAL NOT NULL DEFAULT 0,
    needs_confirmation INTEGER NOT NULL DEFAULT 0,
    consensus_strong_edges   INTEGER NOT NULL DEFAULT 0,  -- strong consensus pairs between the two frameworks
    consensus_text_confirmed INTEGER NOT NULL DEFAULT 0,  -- subset eligible to corroborate (texts on file, real shared footprint)
    PRIMARY KEY (framework_a, framework_b)
);

CREATE VIEW IF NOT EXISTS projection_overlap_subpart AS
    SELECT a.framework AS framework_a, b.framework AS framework_b, a.r5_subpart,
           a.native_id AS native_a, b.native_id AS native_b
    FROM framework_projection a
    JOIN framework_projection b
      ON a.r5_subpart = b.r5_subpart AND a.r5_subpart IS NOT NULL
     AND a.framework < b.framework;

CREATE VIEW IF NOT EXISTS projection_overlap_cci AS
    SELECT a.framework AS framework_a, b.framework AS framework_b, cb.cci_id,
           a.native_id AS native_a, b.native_id AS native_b
    FROM framework_projection a
    JOIN framework_projection b ON a.r5_subpart = b.r5_subpart AND a.r5_subpart IS NOT NULL
    JOIN cci_bridge cb ON cb.r5_subpart = a.r5_subpart
    WHERE a.framework < b.framework;

-- ── STIG application layer (Phase 21, technology tier) ────────────────────────
-- STIG benchmarks are a per-product implementation tier, NOT master-surface
-- frameworks: they never enter framework_projection, overlap_matrix, or
-- master_mappings. Their footprint over the 800-53 spine is resolved on demand
-- (spine_overlap `stig:` resolver) via each rule's CCIs through cci_bridge.
CREATE TABLE IF NOT EXISTS stig_catalog (
    stig_id        TEXT PRIMARY KEY,   -- XCCDF Benchmark id (e.g. "RHEL_9_STIG")
    title          TEXT,
    version        TEXT,
    release        TEXT,
    benchmark_date TEXT,               -- ISO date of the benchmark
    type           TEXT,               -- stig | srg
    rule_count     INTEGER NOT NULL DEFAULT 0,
    cci_citations  INTEGER NOT NULL DEFAULT 0,  -- total CCI references (with repetition)
    distinct_ccis  INTEGER NOT NULL DEFAULT 0,
    trackr_title   TEXT,               -- cyber.trackr.live catalog key (delta detector), NULL if unmatched
    source         TEXT,               -- disa_compilation | trackr | …
    source_zip     TEXT
);
CREATE INDEX IF NOT EXISTS idx_stigcat_trackr ON stig_catalog(trackr_title);

CREATE TABLE IF NOT EXISTS stig_rules (
    stig_id     TEXT NOT NULL REFERENCES stig_catalog(stig_id),
    group_id    TEXT NOT NULL,         -- V-xxxxxx
    rule_id     TEXT,                  -- SV-…_rule
    version_id  TEXT,                  -- STIG rule version id (carries SRG lineage), e.g. AZLX-23-000100
    severity    TEXT,                  -- high | medium | low
    title       TEXT,
    ccis        TEXT,                  -- JSON-sorted list of "CCI-NNNNNN"
    PRIMARY KEY (stig_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_stigrules_stig ON stig_rules(stig_id);

CREATE TABLE IF NOT EXISTS stig_cci_usage (
    cci_id     TEXT PRIMARY KEY,       -- "CCI-000068"
    n_stigs    INTEGER NOT NULL DEFAULT 0,
    n_rules    INTEGER NOT NULL DEFAULT 0,
    in_bridge  INTEGER NOT NULL DEFAULT 0   -- 1 if resolvable in cci_bridge, else 0 (gap detector)
);

-- OLIR-hub composed edges (Phase 25): third-party control -> CSF 2.0 -> 800-53 r5,
-- composed through the CSF 2.0 hub from OLIR sets already committed in the CPRT
-- element graphs.  Every edge cites two real OLIR references.  These are a
-- query-surface / on-demand tier: they never enter framework_projection,
-- overlap_matrix, or master_mappings, so the matrix and master tiers are unchanged.
CREATE TABLE IF NOT EXISTS olir_hub_edges (
    framework    TEXT NOT NULL,        -- third-party framework (e.g. "CIS Controls 8.1")
    native_id    TEXT NOT NULL,        -- native control id in that framework
    csf2_id      TEXT NOT NULL,        -- CSF 2.0 subcategory the composition bridges through
    r5_control   TEXT NOT NULL,        -- 800-53 r5 control reached via the hub
    basis        TEXT NOT NULL,        -- olir_hub_composed
    source_ref_a TEXT NOT NULL,        -- third-party -> CSF2 OLIR set name (hop 1)
    source_ref_b TEXT NOT NULL,        -- CSF2 -> 800-53 OLIR set name (hop 2)
    confidence   REAL NOT NULL DEFAULT 0.6,
    PRIMARY KEY (framework, native_id, csf2_id, r5_control)
);
CREATE INDEX IF NOT EXISTS idx_olirhub_fw ON olir_hub_edges(framework);

-- FedRAMP Consolidated Rules 2026 (Phase 26): the machine-readable audit-framework
-- revision (confirmation/monitoring machinery). KSI edges are FedRAMP's OWN published
-- 800-53 mapping. Contained query-surface tier — never enters framework_projection /
-- overlap_matrix / master_mappings; FedRAMP r5 keeps its matrix seat unchanged.
CREATE TABLE IF NOT EXISTS fedramp_ksi (
    indicator_id TEXT PRIMARY KEY,     -- e.g. "KSI-IAM-AAM"
    family       TEXT NOT NULL,        -- e.g. "KSI-IAM"
    family_name  TEXT,
    name         TEXT,
    statement    TEXT,
    status       TEXT,                 -- dataset-published status (stable | placeholder | ...)
    lifecycle    TEXT NOT NULL         -- 2026_public_preview
);
CREATE TABLE IF NOT EXISTS fedramp_ksi_controls (
    indicator_id TEXT NOT NULL REFERENCES fedramp_ksi(indicator_id),
    r5_control   TEXT NOT NULL,        -- resolved 800-53 r5 id
    basis        TEXT NOT NULL,        -- fedramp_stated (authority-published self-mapping)
    confidence   REAL NOT NULL DEFAULT 0.9,
    PRIMARY KEY (indicator_id, r5_control)
);
CREATE INDEX IF NOT EXISTS idx_frksi_ctrl ON fedramp_ksi_controls(r5_control);
CREATE TABLE IF NOT EXISTS fedramp_rules (
    rule_id        TEXT NOT NULL,      -- e.g. "AFC-FRP-VRE"
    family         TEXT NOT NULL,      -- e.g. "AFC"
    family_name    TEXT,
    pipeline       TEXT NOT NULL,      -- all | 20x | rev5 (the version-transition dimension)
    subgroup       TEXT NOT NULL,
    name           TEXT,
    statement      TEXT,
    force          TEXT,               -- MUST | SHOULD | ...
    status         TEXT,               -- family status (stable | placeholder)
    effective_json TEXT,
    PRIMARY KEY (rule_id, pipeline, subgroup)
);
CREATE TABLE IF NOT EXISTS fedramp_odp_pins (
    parameter_id TEXT NOT NULL,        -- e.g. "ac-06.01_odp.02"
    r5_control   TEXT,
    value        TEXT,
    source       TEXT NOT NULL,        -- fedramp_ctl_2026
    PRIMARY KEY (parameter_id, source)
);
CREATE TABLE IF NOT EXISTS fedramp_ctl_guidance (
    ctl_key              TEXT PRIMARY KEY,  -- dataset key, e.g. "AC-20"
    r5_control           TEXT,
    guidance_json        TEXT,              -- FedRAMP implementation guidance (JSON list)
    varies_by_class_json TEXT               -- per-certification-class guidance where it differs
);
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


_PROV_SUPPORT = {"WELL_SUPPORTED", "CONTESTED", "THIN", "UNSUPPORTED"}
_PROV_TERMINAL = {"ORIGIN", "ORIGIN_RECOVERED", "DEAD_END", "ORPHAN_CONFIRMED", "CIRCULAR_UNRESOLVED"}


def load_anticipated_updates(path: Path) -> list[dict]:
    """Load the horizon registry (anticipated_updates.json) into flat rows.
    Static content only — the dynamic overdue/materialized state is computed at
    query time by horizon_monitor.py, so the table stays deterministic.
    v3.14: flattens the optional regulatory-provenance block and HARD-FAILS on
    out-of-vocab support/terminal values (protocol-layer/regulatory-provenance.md)."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for r in doc.get("records", []):
        prov = r.get("provenance") or {}
        support = prov.get("support")
        terminal = prov.get("terminal_state")
        if support is not None and support not in _PROV_SUPPORT:
            raise SystemExit(f"anticipated_updates: record {r.get('id')} has invalid "
                             f"support label {support!r} (allowed: {sorted(_PROV_SUPPORT)})")
        if terminal is not None and terminal not in _PROV_TERMINAL:
            raise SystemExit(f"anticipated_updates: record {r.get('id')} has invalid "
                             f"terminal state {terminal!r} (allowed: {sorted(_PROV_TERMINAL)})")
        # URL well-formedness applies to EVERY terminal state: DEAD_END exempts content
        # matching, never the citation itself (regulatory-provenance.md §2). Validation
        # tightening only — no schema shape change, so SCHEMA_VERSION is unaffected.
        url = prov.get("primary_source_url")
        if url is not None and not str(url).startswith(("http://", "https://")):
            raise SystemExit(f"anticipated_updates: record {r.get('id')} provenance URL "
                             f"must be http(s) and non-empty for every terminal state "
                             f"(got {url!r})")
        rows.append({
            "id": r.get("id", ""),
            "feed_id": r.get("feed_id", ""),
            "authority": r.get("authority", ""),
            "artifact": r.get("artifact", ""),
            "current_version": r.get("current_version", ""),
            "expected_type": r.get("expected_type", ""),
            "lifecycle_stage": r.get("lifecycle_stage"),
            "expected_window": json.dumps(r.get("expected_window"), ensure_ascii=False),
            "confidence": r.get("confidence", ""),
            "trigger_signal": r.get("trigger_signal", ""),
            "detection": json.dumps(r.get("detection", {}), ensure_ascii=False),
            "poll_frequency": r.get("poll_frequency", ""),
            "source_urls": json.dumps(r.get("source_urls", []), ensure_ascii=False),
            "dependent_of": r.get("dependent_of"),
            "status": r.get("status", "watching"),
            "escalate_after_days": int(r.get("escalate_after_days", 120)),
            "last_checked": r.get("last_checked"),
            "last_change_detected": r.get("last_change_detected"),
            "provenance_url": prov.get("primary_source_url"),
            "provenance_retrieved": prov.get("retrieved_at"),
            "provenance_verbatim": prov.get("verbatim"),
            "support_label": support,
            "terminal_state": terminal,
            "notes": r.get("notes", ""),
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
    import uncertainty as _unc  # type: ignore
    confirmations = _unc.load_confirmations(REPO_ROOT / "canonical-sources" / "confirmations.jsonl")
    # CCI bridge: prefer the current DISA CCI List XML (native rev-5 refs + App J
    # absorption recovery); fall back to the legacy xlsx derivative if absent.
    if spine_loader.CCI_XML_PATH.exists():
        cci_bridge_rows, spine_disa_rows, cci_stats = spine_loader.load_cci_bridge_xml(catalog_ids)
    else:
        cci_bridge_rows, spine_disa_rows, cci_stats = spine_loader.load_cci_bridge(catalog_ids)
        for r in cci_bridge_rows:
            r.setdefault("basis", "xlsx_legacy")
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
        INSERT INTO cci_bridge (cci_id, r5_control, r5_subpart, r4_ref_raw, basis, source_file, source_row)
        VALUES (:cci_id, :r5_control, :r5_subpart, :r4_ref_raw, :basis, :source_file, :source_row)
    """, cci_bridge_rows, "cci_bridge")

    _executemany_chunked(conn, """
        INSERT OR IGNORE INTO control_odps
            (odp_id, control_id, r5_subpart, type, label, ordinal, rekey_basis)
        VALUES (:odp_id, :control_id, :r5_subpart, :type, :label, :ordinal, :rekey_basis)
    """, odp_rows, "control_odps")

    # Populate disa_ccis from the CCI source (real data; the Trackr JSON step below
    # will REPLACE/augment these if that source is present).
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO disa_ccis
            (cci_id, definition, type, status, publishdate, nist_rev4_refs, nist_rev5_refs,
             nist_r5_index, legacy_refs, fetched_at)
        VALUES (:cci_id, :definition, :type, :status, :publishdate, :nist_rev4_refs,
                :nist_rev5_refs, :nist_r5_index, :legacy_refs, :fetched_at)
    """, spine_disa_rows, "disa_ccis")

    # 1c. OSCAL structural walk — definitive ODP -> sub-part links + 800-53A
    # assessment objectives (sub-part anchors for families without CCIs).
    oscal_links, objective_rows, oscal_stats = spine_loader.load_oscal_structural(catalog_ids)
    conn.commit()
    n_odp_linked = spine_loader.link_odps_to_subparts_from_oscal(oscal_links, conn)
    print(f"  oscal_structural: controls={oscal_stats.get('controls_seen')} "
          f"odp_links={oscal_stats.get('odp_links')} objectives={oscal_stats.get('objectives')} "
          f"link_bases={oscal_stats.get('link_basis_counts')}")
    print(f"  odp_backfill(oscal): {n_odp_linked} control_odps rows linked")
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO assessment_objectives
            (objective_id, control_id, r5_subpart, label, prose, source_file, source_row)
        VALUES (:objective_id, :control_id, :r5_subpart, :label, :prose, :source_file, :source_row)
    """, objective_rows, "assessment_objectives")

    # Framework projection edges — Phase 2: NIST 800-53 <-> ISO 27001 via the OLIR.
    olir_edges, olir_stats = spine_loader.load_olir_projection(catalog_ids)
    _unc.apply_confirmations_to_edges(olir_edges, confirmations)
    print(f"  olir projection: edges={olir_stats['edges']} unresolved_focal={olir_stats['unresolved_focal']}")
    _executemany_chunked(conn, """
        INSERT INTO framework_projection
            (framework, native_id, r5_control, r5_subpart, cci_id, odp_id,
             relationship, relationship_basis, granularity, provenance, confidence,
             hop_count, needs_confirmation, uncertainty_id, status, source_file, source_sheet, source_row)
        VALUES
            (:framework, :native_id, :r5_control, :r5_subpart, :cci_id, :odp_id,
             :relationship, :relationship_basis, :granularity, :provenance, :confidence,
             :hop_count, :needs_confirmation, :uncertainty_id, :status, :source_file, :source_sheet, :source_row)
    """, olir_edges, "framework_projection")

    # Phase 2b: CMMC/800-171 <-> 800-53 crosswalks (source-stated relationships).
    cmmc_edges, fedramp_odp_rows, cmmc_stats = spine_loader.load_cmmc171_projection(catalog_ids)
    _unc.apply_confirmations_to_edges(cmmc_edges, confirmations)
    print(f"  cmmc171 projection: edges={cmmc_stats['edges']} "
          f"(cmmc={cmmc_stats['cmmc_edges']} 171={cmmc_stats['nist171_edges']}) "
          f"relationships={cmmc_stats['relationships']} "
          f"fedramp_odp_values={cmmc_stats['fedramp_values']}")
    _executemany_chunked(conn, """
        INSERT INTO framework_projection
            (framework, native_id, r5_control, r5_subpart, cci_id, odp_id,
             relationship, relationship_basis, granularity, provenance, confidence,
             hop_count, needs_confirmation, uncertainty_id, status, source_file, source_sheet, source_row)
        VALUES
            (:framework, :native_id, :r5_control, :r5_subpart, :cci_id, :odp_id,
             :relationship, :relationship_basis, :granularity, :provenance, :confidence,
             :hop_count, :needs_confirmation, :uncertainty_id, :status, :source_file, :source_sheet, :source_row)
    """, cmmc_edges, "framework_projection")

    # Backfill control_odps.r5_subpart from crosswalk ODP links
    odp_backfill_count = spine_loader.link_odps_to_subparts(
        cmmc_stats.get("odp_links", []), conn)
    print(f"  odp_backfill: {odp_backfill_count} control_odps rows linked to r5_subpart")

    # FedRAMP ODP pinned values extracted from the crosswalk
    if fedramp_odp_rows:
        _executemany_chunked(conn, """
            INSERT INTO odp_values
                (control_id, odp_id, baseline, value_raw, value_norm, value_kind,
                 extraction_confidence, needs_confirmation, source_file, source_row)
            VALUES
                (:control_id, :odp_id, :baseline, :value_raw, :value_norm, :value_kind,
                 :extraction_confidence, :needs_confirmation, :source_file, :source_row)
        """, fedramp_odp_rows, "odp_values (FedRAMP)")
        print(f"  fedramp_odp_values: {len(fedramp_odp_rows)} pinned values (partial gap fill)")

    # Phase 3: HITRUST hub — SOC 2 / ISO / HIPAA / GDPR / CMMC / FedRAMP / CIS / 800-171.
    hub_rows, hub_edges, hub_stats = spine_loader.load_hitrust_hub(catalog_ids)
    cascade = _unc.apply_confirmations_to_edges(hub_edges, confirmations)
    print(f"  hitrust hub: frameworks={len(hub_stats['frameworks'])} edges={hub_stats['edges']} "
          f"nist_parse_incomplete={hub_stats['nist_parse_incomplete']} "
          f"iso_ambiguous={hub_stats.get('iso_ambiguous', 0)}")
    print(f"  confirmation cascade: {cascade}")
    _executemany_chunked(conn, """
        INSERT INTO hitrust_hub (hitrust_id, framework, target_id, source_row)
        VALUES (:hitrust_id, :framework, :target_id, :source_row)
    """, hub_rows, "hitrust_hub")
    _executemany_chunked(conn, """
        INSERT INTO framework_projection
            (framework, native_id, r5_control, r5_subpart, cci_id, odp_id,
             relationship, relationship_basis, granularity, provenance, confidence,
             hop_count, needs_confirmation, uncertainty_id, status, source_file, source_sheet, source_row)
        VALUES
            (:framework, :native_id, :r5_control, :r5_subpart, :cci_id, :odp_id,
             :relationship, :relationship_basis, :granularity, :provenance, :confidence,
             :hop_count, :needs_confirmation, :uncertainty_id, :status, :source_file, :source_sheet, :source_row)
    """, hub_edges, "framework_projection")

    # Phase 19: direct projections — HIPAA (NIST SP 800-66r2 OLIR), CSF 2.0
    # (official OLIR, r5.2.0-pinned), 171r3 + 172r3 (official CPRT datasets),
    # PCI (bundled tier from the user-provided master crosswalk). Each is
    # guarded on artifact existence (offline rebuilds still pass).
    _P19_INSERT = """
        INSERT INTO framework_projection
            (framework, native_id, r5_control, r5_subpart, cci_id, odp_id,
             relationship, relationship_basis, granularity, provenance, confidence,
             hop_count, needs_confirmation, uncertainty_id, status, source_file, source_sheet, source_row)
        VALUES
            (:framework, :native_id, :r5_control, :r5_subpart, :cci_id, :odp_id,
             :relationship, :relationship_basis, :granularity, :provenance, :confidence,
             :hop_count, :needs_confirmation, :uncertainty_id, :status, :source_file, :source_sheet, :source_row)
    """
    for _label, _loader in (("800-66 (HIPAA direct)", spine_loader.load_800_66_projection),
                            ("csf2 (OLIR r5.2.0)", spine_loader.load_csf2_projection),
                            ("171r3 (CPRT)", spine_loader.load_171r3_projection),
                            ("172r3 (CPRT)", spine_loader.load_172r3_projection),
                            ("pci (master crosswalk, bundled)", spine_loader.load_pci_master_projection),
                            ("scf (owner-stated, SCF/CAP scope)", spine_loader.load_scf_projection),
                            ("ccm (owner-stated OSCAL, CSA STAR scope)", spine_loader.load_ccm_projection)):
        _edges, _pstats = _loader(catalog_ids)
        if not _edges:
            print(f"  {_label} projection: skipped ({_pstats.get('skipped', 'no edges')})")
            continue
        _unc.apply_confirmations_to_edges(_edges, confirmations)
        print(f"  {_label} projection: {_pstats}")
        _executemany_chunked(conn, _P19_INSERT, _edges, "framework_projection")

    # Complete the sub-part inventory: union every sub-part referenced by
    # framework_projection or assessment_objectives into nist_subparts, so
    # control-level footprint expansion enumerates the same denominator that
    # sub-part-level edges name directly (each row traces to real source rows
    # in the referencing table).
    n_inv = spine_loader.complete_subpart_inventory(conn)
    print(f"  subpart_inventory: +{n_inv} sub-parts unioned from projections/objectives")

    # Phase 4: concrete ODP values pinned in DAAPM (DoD) prose.
    odpval_rows, odpval_stats = spine_loader.load_odp_values(catalog_ids)
    print(f"  odp_values: rows={odpval_stats.get('rows')} controls={odpval_stats.get('controls_with_values')}")
    print("  odp_values data_gap: FedRAMP baselines partially loaded (37 values from CMMC crosswalk); "
          "SOC 2 / ISO / HIPAA do not pin NIST ODPs (parameter comparison is undetermined there)")
    _executemany_chunked(conn, """
        INSERT INTO odp_values
            (control_id, odp_id, baseline, value_raw, value_norm, value_kind,
             extraction_confidence, needs_confirmation, source_file, source_row)
        VALUES
            (:control_id, :odp_id, :baseline, :value_raw, :value_norm, :value_kind,
             :extraction_confidence, :needs_confirmation, :source_file, :source_row)
    """, odpval_rows, "odp_values")

    # Phase 21: STIG application layer (technology tier). Guarded on artifact
    # existence — offline rebuilds without the distilled stig_cci_map still pass.
    # STIG benchmarks never enter framework_projection / overlap_matrix /
    # master_mappings; their spine footprint is resolved on demand.
    stig_cat_rows, stig_rule_rows, stig_usage_rows, stig_stats = spine_loader.load_stig_rules(catalog_ids)
    if stig_cat_rows:
        # in_bridge: mark each STIG-cited CCI resolvable in cci_bridge (gap detector)
        bridge_ccis = {r[0] for r in conn.execute("SELECT DISTINCT cci_id FROM cci_bridge")}
        for u in stig_usage_rows:
            u["in_bridge"] = 1 if u["cci_id"] in bridge_ccis else 0
        _unknown = sum(1 for u in stig_usage_rows if not u["in_bridge"])
        _executemany_chunked(conn, """
            INSERT INTO stig_catalog
                (stig_id, title, version, release, benchmark_date, type, rule_count,
                 cci_citations, distinct_ccis, trackr_title, source, source_zip)
            VALUES
                (:stig_id, :title, :version, :release, :benchmark_date, :type, :rule_count,
                 :cci_citations, :distinct_ccis, :trackr_title, :source, :source_zip)
        """, stig_cat_rows, "stig_catalog")
        _executemany_chunked(conn, """
            INSERT INTO stig_rules
                (stig_id, group_id, rule_id, version_id, severity, title, ccis)
            VALUES
                (:stig_id, :group_id, :rule_id, :version_id, :severity, :title, :ccis)
        """, stig_rule_rows, "stig_rules")
        _executemany_chunked(conn, """
            INSERT INTO stig_cci_usage (cci_id, n_stigs, n_rules, in_bridge)
            VALUES (:cci_id, :n_stigs, :n_rules, :in_bridge)
        """, stig_usage_rows, "stig_cci_usage")
        print(f"  stig application layer: {stig_stats}")
        print(f"  stig_cci_usage: {len(stig_usage_rows)} distinct CCIs "
              f"({_unknown} STIG-cited CCIs unresolved in cci_bridge — gap detector, informational)")
    else:
        print(f"  stig application layer: skipped ({stig_stats.get('skipped')})")

    # Phase 25: OLIR-hub composed edges (third-party -> CSF 2.0 -> 800-53 r5).
    # Contained tier — never enters framework_projection / overlap_matrix / master_mappings.
    olir_hub_rows, olir_hub_stats = spine_loader.load_olir_hub_edges(catalog_ids)
    if olir_hub_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO olir_hub_edges
                (framework, native_id, csf2_id, r5_control, basis, source_ref_a, source_ref_b, confidence)
            VALUES
                (:framework, :native_id, :csf2_id, :r5_control, :basis, :source_ref_a, :source_ref_b, :confidence)
        """, olir_hub_rows, "olir_hub_edges")
        print(f"  olir_hub_edges: {olir_hub_stats}")
    else:
        print(f"  olir_hub_edges: skipped ({olir_hub_stats.get('skipped')})")

    # Phase 26: FedRAMP Consolidated Rules 2026 (KSIs + rules + ODP pins).
    # Contained tier — never enters framework_projection / overlap_matrix / master_mappings.
    fr_ksi, fr_edges, fr_rules, fr_odp, fr_guid, fr_stats = spine_loader.load_fedramp_rules(catalog_ids)
    if fr_ksi:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO fedramp_ksi
                (indicator_id, family, family_name, name, statement, status, lifecycle)
            VALUES (:indicator_id, :family, :family_name, :name, :statement, :status, :lifecycle)
        """, fr_ksi, "fedramp_ksi")
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO fedramp_ksi_controls
                (indicator_id, r5_control, basis, confidence)
            VALUES (:indicator_id, :r5_control, :basis, :confidence)
        """, fr_edges, "fedramp_ksi_controls")
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO fedramp_rules
                (rule_id, family, family_name, pipeline, subgroup, name, statement, force, status, effective_json)
            VALUES (:rule_id, :family, :family_name, :pipeline, :subgroup, :name, :statement, :force, :status, :effective_json)
        """, fr_rules, "fedramp_rules")
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO fedramp_odp_pins (parameter_id, r5_control, value, source)
            VALUES (:parameter_id, :r5_control, :value, :source)
        """, fr_odp, "fedramp_odp_pins")
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO fedramp_ctl_guidance
                (ctl_key, r5_control, guidance_json, varies_by_class_json)
            VALUES (:ctl_key, :r5_control, :guidance_json, :varies_by_class_json)
        """, fr_guid, "fedramp_ctl_guidance")
        print(f"  fedramp consolidated rules: {fr_stats}")
    else:
        print(f"  fedramp consolidated rules: skipped ({fr_stats.get('skipped')})")

    conn.commit()

    # Phase 22: CCI↔800-53 mapping corroboration (DISA bridge × acasehs × trackr ×
    # STIG usage). Runs after stig_cci_usage exists so application evidence is joined.
    cci_corr_rows, cci_corr_stats = spine_loader.build_cci_corroboration(cci_bridge_rows, conn)
    if cci_corr_rows:
        _executemany_chunked(conn, """
            INSERT INTO cci_mapping_corroboration
                (cci_id, r5_control, in_disa_bridge, disa_basis, in_acasehs_r5,
                 in_acasehs_r4, in_trackr, stig_exercised, verdict, witnesses)
            VALUES
                (:cci_id, :r5_control, :in_disa_bridge, :disa_basis, :in_acasehs_r5,
                 :in_acasehs_r4, :in_trackr, :stig_exercised, :verdict, :witnesses)
        """, cci_corr_rows, "cci_mapping_corroboration")
        print(f"  cci_mapping_corroboration: {cci_corr_stats}")
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

    # 5b. Anticipated updates (horizon-scanning registry)
    au_path = REPO_ROOT / "canonical-sources" / "anticipated_updates.json"
    au_rows = load_anticipated_updates(au_path)
    if au_rows:
        _executemany_chunked(conn, """
            INSERT OR REPLACE INTO anticipated_updates
                (id, feed_id, authority, artifact, current_version, expected_type, lifecycle_stage,
                 expected_window, confidence, trigger_signal, detection, poll_frequency, source_urls,
                 dependent_of, status, escalate_after_days, last_checked, last_change_detected,
                 provenance_url, provenance_retrieved, provenance_verbatim, support_label,
                 terminal_state, notes)
            VALUES
                (:id, :feed_id, :authority, :artifact, :current_version, :expected_type, :lifecycle_stage,
                 :expected_window, :confidence, :trigger_signal, :detection, :poll_frequency, :source_urls,
                 :dependent_of, :status, :escalate_after_days, :last_checked, :last_change_detected,
                 :provenance_url, :provenance_retrieved, :provenance_verbatim, :support_label,
                 :terminal_state, :notes)
        """, au_rows, "anticipated_updates")
        print(f"  anticipated_updates: {len(au_rows)} horizon records")
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

    # 12. DISA CCI data (Trackr JSON). Precedence: when the authoritative CCI List
    # XML populated disa_ccis in step 1b, its r5-resolved refs win — the trackr
    # rows only fill CCIs the XML didn't cover (INSERT OR IGNORE). Without the
    # XML, trackr may REPLACE the legacy xlsx-derived rows.
    print(f"\n[12/15] Loading DISA CCI data: {cci_path.name}")
    cci_rows = load_cci_data(cci_path)
    if cci_rows:
        _verb = "IGNORE" if spine_loader.CCI_XML_PATH.exists() else "REPLACE"
        _executemany_chunked(conn, f"""
            INSERT OR {_verb} INTO disa_ccis
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

    # Cross-source consensus: independent voters agreeing on third-party pairs.
    # Runs BEFORE the overlap matrix so the matrix can persist per-pair consensus
    # corroboration counts.
    import consensus_detector as _cd  # type: ignore
    consensus_rows, cd_stats = _cd.detect(conn)
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO consensus_edges
            (fw_a, native_a, fw_b, native_b, votes, tier, voters, evidence,
             production_support, nist_ancestry_overlap, extent, shared_atoms_count,
             shared_atoms, text_confirmation, uncertainty_id, needs_confirmation)
        VALUES
            (:fw_a, :native_a, :fw_b, :native_b, :votes, :tier, :voters, :evidence,
             :production_support, :nist_ancestry_overlap, :extent, :shared_atoms_count,
             :shared_atoms, :text_confirmation, :uncertainty_id, :needs_confirmation)
    """, consensus_rows, "consensus_edges")
    conn.commit()
    print(f"  consensus_edges: pairs={cd_stats['pairs']} tiers={cd_stats['tiers']} "
          f"production_corroborated={cd_stats['with_production_support']}")

    # Precompute the pairwise overlap matrix across all spine frameworks.
    # consensus_tier=False: the persisted matrix never depends on the
    # consensus_provenance flag state, so builds stay deterministic; the
    # corroboration counts are stored alongside and the query layer applies
    # the flag-gated tier live.
    # Phase 19: canonical framework label registry + the master mapping surface.
    import master_surface as _ms  # type: ignore
    label_rows = _ms.load_label_rows()
    # Self-register every surface label the DB actually carries that has no
    # explicit alias: identity rows (surface='surface_observed'), so the
    # registry is complete and new unified/er labels never break resolution.
    _known_aliases = {r["alias"] for r in label_rows}
    _observed = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT framework FROM unified_mappings WHERE framework <> 'DISA CCI' "
        "UNION SELECT DISTINCT framework FROM er_mappings "
        "UNION SELECT DISTINCT framework FROM framework_projection")})
    for _lbl in _observed:
        if _lbl not in _known_aliases:
            label_rows.append({"alias": _lbl, "surface": "surface_observed", "canonical": _lbl})
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO framework_labels (alias, surface, canonical)
        VALUES (:alias, :surface, :canonical)
    """, label_rows, "framework_labels")
    print(f"  framework_labels: {len(label_rows)} alias rows "
          f"({sum(1 for r in label_rows if r['surface'] == 'surface_observed')} surface-observed identities)")

    _csf2_pairs, _cp_stats = spine_loader.collect_csf2_olir_pairs()
    print(f"  csf2 olir pairs: {_cp_stats}")
    _tsp_pairs, _tsp_stats = spine_loader.load_aicpa_tsp_hub()
    print(f"  aicpa_tsp pairs: {_tsp_stats}")
    _ccm_cis_pairs, _cc_stats = spine_loader.collect_ccm_cis_pairs()
    print(f"  ccm_cis pairs: {_cc_stats}")
    master_rows, master_stats = _ms.assemble(conn, csf2_pairs=_csf2_pairs, tsp_pairs=_tsp_pairs,
                                             ccm_cis_pairs=_ccm_cis_pairs)
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO master_mappings
            (fw_a, native_a, fw_b, native_b, relationship, relationship_basis,
             tier, provenance, confidence, hop_count, needs_confirmation,
             uncertainty_id, votes, production_support, shared_anchors,
             anchor_count, corroboration, edge_semantic, evidence_state, source_ref)
        VALUES
            (:fw_a, :native_a, :fw_b, :native_b, :relationship, :relationship_basis,
             :tier, :provenance, :confidence, :hop_count, :needs_confirmation,
             :uncertainty_id, :votes, :production_support, :shared_anchors,
             :anchor_count, :corroboration, :edge_semantic, :evidence_state, :source_ref)
    """, master_rows, "master_mappings")
    conn.commit()
    print(f"  master_mappings: rows={master_stats['rows']} by_tier={master_stats['by_tier']} "
          f"(fedramp baseline-annotation natives excluded: {master_stats['skipped_fedramp']}; "
          f"single-voter consensus pairs excluded: {master_stats['skipped_consensus_single']})")

    print("\n[overlap] Precomputing overlap_matrix over spine frameworks")
    import spine_overlap as _so  # type: ignore
    proj_fws = [r[0] for r in conn.execute(
        "SELECT DISTINCT framework FROM framework_projection ORDER BY framework")]
    # Phase 19: the matrix covers the canonical union — spine frameworks plus
    # ER-only frameworks (SOC 1, HITRUST CSF), which compute() degrades to
    # inferred_er / none honestly. Canonicalized, deduped, deterministic.
    _er_fws = [r[0] for r in conn.execute(
        "SELECT DISTINCT framework FROM er_mappings ORDER BY framework")]
    _canon_map = {a: c for a, _s, c in conn.execute(
        "SELECT alias, surface, canonical FROM framework_labels")}
    matrix_fws = sorted({f for f in proj_fws} |
                        {_canon_map.get(f, f) for f in _er_fws})
    # er labels that canonicalize onto a projection framework keep the
    # projection label; genuinely new ones (SOC 1, HITRUST CSF) join the matrix.
    proj_fws = [f for f in matrix_fws]
    om_rows = []
    for i in range(len(proj_fws)):
        for j in range(i + 1, len(proj_fws)):
            fa, fb = proj_fws[i], proj_fws[j]
            res = _so.compute(conn, fa, fb, consensus_tier=False)
            support = res.get("consensus_support") or {}
            om_rows.append({
                "framework_a": fa, "framework_b": fb, "basis": res.get("basis", "none"),
                "shared_count": res.get("shared_count", 0),
                "a_count": res.get("framework_a_count", 0),
                "b_count": res.get("framework_b_count", 0),
                "jaccard_pct": res.get("overlap_pct", 0.0) or 0.0,
                "a_covers_b_pct": res.get("a_covers_b_pct", 0.0) or 0.0,
                "b_covers_a_pct": res.get("b_covers_a_pct", 0.0) or 0.0,
                "confidence": res.get("confidence_score", 0.0) or 0.0,
                "needs_confirmation": int(res.get("needs_confirmation", False)),
                "consensus_strong_edges": support.get("strong_edges", 0),
                "consensus_text_confirmed": support.get("text_confirmed", 0),
            })
    _executemany_chunked(conn, """
        INSERT OR REPLACE INTO overlap_matrix
            (framework_a, framework_b, basis, shared_count, a_count, b_count,
             jaccard_pct, a_covers_b_pct, b_covers_a_pct, confidence, needs_confirmation,
             consensus_strong_edges, consensus_text_confirmed)
        VALUES
            (:framework_a, :framework_b, :basis, :shared_count, :a_count, :b_count,
             :jaccard_pct, :a_covers_b_pct, :b_covers_a_pct, :confidence, :needs_confirmation,
             :consensus_strong_edges, :consensus_text_confirmed)
    """, om_rows, "overlap_matrix")
    conn.commit()
    print(f"  overlap_matrix: {len(om_rows)} pairs")

    # Durable, committed uncertainty ledger (what the health tools scan).
    ledger_path = REPO_ROOT / "canonical-sources" / "uncertainty_ledger.jsonl"
    n_ledger = _unc.write_ledger(conn, ledger_path, confirmations)
    print(f"  uncertainty_ledger.jsonl: {n_ledger} entries -> {ledger_path.name}")

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
                "nist_subparts", "cci_bridge", "control_odps", "assessment_objectives",
                "framework_projection", "hitrust_hub", "odp_values", "overlap_matrix",
                "consensus_edges", "framework_labels", "master_mappings",
                "stig_catalog", "stig_rules", "stig_cci_usage",
                "cci_mapping_corroboration", "anticipated_updates", "olir_hub_edges",
                "fedramp_ksi", "fedramp_ksi_controls", "fedramp_rules", "fedramp_odp_pins",
                "fedramp_ctl_guidance"):
        row = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
        counts[tbl] = row[0]

    # Logical content digests — the determinism comparator across rebuilds
    # (the raw SQLite file hash varies with page layout; these do not).
    # Coverage is DERIVED from sqlite_master so a new table is digested the day it
    # is created — a hand-kept list is how coverage gaps arise. Exclusions only,
    # each with a reason; a stale exclusion (naming a table that no longer exists)
    # is itself drift and warns.
    _DIGEST_EXCLUDE = {
        "sqlite_sequence": "SQLite AUTOINCREMENT bookkeeping — not content",
        "sqlite_stat1": "SQLite ANALYZE statistics — not content",
        "controls_fts": "FTS5 virtual table — derived from controls, which is digested",
        "controls_fts_config": "FTS5 shadow table (see controls_fts)",
        "controls_fts_data": "FTS5 shadow table (see controls_fts)",
        "controls_fts_docsize": "FTS5 shadow table (see controls_fts)",
        "controls_fts_idx": "FTS5 shadow table (see controls_fts)",
        "db_metadata": "carries built_at, a wall-clock timestamp — nondeterministic by design",
    }
    all_tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for stale in sorted(set(_DIGEST_EXCLUDE) - set(all_tables)):
        print(f"  [warn] digest exclusion names a missing table: {stale} — prune the exclusion")
    table_digests = {}
    for tbl in all_tables:
        if tbl in _DIGEST_EXCLUDE:
            continue
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})") if r[1] != "rowid"]
        h = hashlib.sha256()
        for row in conn.execute(f"SELECT {','.join(cols)} FROM {tbl} ORDER BY {','.join(cols)}"):
            h.update(repr(row).encode())
        table_digests[tbl] = h.hexdigest()[:16]

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
        "table_digests": table_digests,
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
