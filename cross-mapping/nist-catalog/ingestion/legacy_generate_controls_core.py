# ============================================================
# generate_controls_core.py
# Core engine for NIST 800-53 full-family control generation
# ============================================================

import json
import pandas as pd
from pathlib import Path


# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

DATA_DIR = Path("source_data")

FILE_53 = DATA_DIR / "CONTROLS WITH EXPLANATIONS - Baseline and enhancements - SP_800_53_r5.11.xlsx"
FILE_172 = DATA_DIR / "sp800-172-enhanced-security-reqs.xlsx"
FILE_171 = DATA_DIR / "NIST BASED CONTROLS CROSS MAPPING CMMC_ 800-171_800-53.xlsx"
FILE_53_171_OVERLAY = DATA_DIR / "NIST CONTROLS CROSS MAPPING sp800-53rev5 and SP800-71r3_overlay_with _necessary_additions.xlsx"
FILE_CCI = DATA_DIR / "stig-mapping-to-nist-800-53.xlsx"
FILE_HITRUST = DATA_DIR / "copy - HITRUST CSF v11.4.0 Authoritative Sources Cross-Reference.xlsx"
FILE_CSF20 = DATA_DIR / "Cybersecurity_Framework_v2-0_Concept_Crosswalk_800-53_final.xlsx"
FILE_DAAPM = DATA_DIR / "FEDERAL BASELINE AND OVERLAY MAPPING  DAAPM Appendix A Security Controls Version 2_2.xlsx"

AC2_TEMPLATE_FILE = Path("combined_frameworks- AC Section of 80053- Fedramp-HIPAA-800171-SOC1-SOC2.json")


# ------------------------------------------------------------
# LOAD AC-2 TEMPLATE FOR SCHEMA EXTRACTION
# ------------------------------------------------------------

with open(AC2_TEMPLATE_FILE, "r", encoding="utf-8") as f:
    AC2_TEMPLATE = json.load(f)

SAMPLE_ACTION = AC2_TEMPLATE["fedramp_context"]["baselines"]["li_saas"]["base_control_requirements"][0]
ACTION_FIELDS = list(SAMPLE_ACTION.keys())


# ------------------------------------------------------------
# LOAD NIST 800-53 MAIN CATALOG
# ------------------------------------------------------------

def load_53_controls():
    df = pd.read_excel(FILE_53)
    df = df[df["Control ID"].str.match(r"[A-Z]{2,3}-\d+")]
    df["Family"] = df["Control ID"].str.split("-").str[0]
    return df


# ------------------------------------------------------------
# LOAD CROSSWALKS (CCI, 171, 172, HITRUST)
# ------------------------------------------------------------

def load_cci_map():
    df = pd.read_excel(FILE_CCI)
    df = df[df["NIST Control"].str.match(r"[A-Z]{2,3}-\d+")]
    mapping = {}
    for _, row in df.iterrows():
        ctrl = row["NIST Control"].strip()
        cci = str(row["CCI"]).strip()
        mapping.setdefault(ctrl, []).append(cci)
    return mapping


def load_171_map():
    df = pd.read_excel(FILE_171)
    df = df[df["800-53 Control"].str.match(r"[A-Z]{2,3}-\d+")]
    mapping = {}
    for _, row in df.iterrows():
        ctrl = row["800-53 Control"].strip()
        mapping.setdefault(ctrl, []).append({
            "req_id": row["800-171 ID"],
            "description": row["800-171 Requirement"]
        })
    return mapping


def load_172_map():
    df = pd.read_excel(FILE_172)
    df = df[df["NIST 800-53 Control"].str.match(r"[A-Z]{2,3}-\d+")]
    mapping = {}
    for _, row in df.iterrows():
        ctrl = row["NIST 800-53 Control"].strip()
        mapping.setdefault(ctrl, []).append({
            "req_id": row["172 ID"],
            "description": row["172 Requirement"]
        })
    return mapping


def load_hitrust_map():
    df = pd.read_excel(FILE_HITRUST)
    df = df[df["NIST 800-53"].str.match(r"[A-Z]{2,3}-\d+")]
    mapping = {}
    for _, row in df.iterrows():
        ctrl = row["NIST 800-53"].strip()
        mapping.setdefault(ctrl, []).append({
            "hitrust_id": row["HITRUST ID"],
            "description": row["HITRUST Requirement"]
        })
    return mapping


# Load all crosswalks once
DF_53 = load_53_controls()
CCI_MAP = load_cci_map()
MAP_171 = load_171_map()
MAP_172 = load_172_map()
MAP_HITRUST = load_hitrust_map()


# ------------------------------------------------------------
# UTILITY FUNCTIONS FOR MAPPING
# ------------------------------------------------------------

def get_ccis(ctrl_id):
    return CCI_MAP.get(ctrl_id, [])


def make_action_item(control_id, part_id, title, description):
    """
    Constructs a control action item (a, b, c or enhancement)
    using the AC-2 schema.
    """
    return {
        "part_id": part_id,
        "title": title,
        "requirement_description": description,
        "fedramp_audit_procedure_id": f"{control_id}.{part_id}",
        "nist_examination_method": ["Examine"],
        "assessment_objective": f"Determine if '{title}' is satisfied.",
        "evidence_request": f"Evidence supporting: {title}",
        "mapped_ccis": get_ccis(control_id)
    }


# ------------------------------------------------------------
# CONTROL PARSING ENGINE
# ------------------------------------------------------------

def parse_control(control_id, name, text, enhancements):
    """
    Returns a list of action items for a control and its enhancements.
    """
    actions = []

    # Main requirement = part "a"
    actions.append(
        make_action_item(
            control_id=control_id,
            part_id="a",
            title=name,
            description=text
        )
    )

    # Enhancements
    if isinstance(enhancements, str) and enhancements.strip():
        for enh in enhancements.split("\n"):
            enh = enh.strip()
            if not enh:
                continue

            enh_id = enh.split(":")[0].strip()  # AC-3(1)
            actions.append(
                make_action_item(
                    control_id=enh_id,
                    part_id=enh_id,
                    title=f"{enh_id} Enhancement",
                    description=enh
                )
            )

    return actions


# ------------------------------------------------------------
# EXPORT CORE FUNCTIONS
# ------------------------------------------------------------

def get_all_families():
    """Returns sorted list of all NIST families from spreadsheet."""
    return sorted(DF_53["Family"].unique())


def get_controls_by_family(family):
    """Returns dataframe of all controls in a given family."""
    return DF_53[DF_53["Family"] == family]


def build_family_controls(family):
    """Builds structured data for all controls in a given family."""
    family_df = get_controls_by_family(family)
    family_actions = {}

    for _, row in family_df.iterrows():
        ctrl = row["Control ID"].strip()
        name = row["Control Name"]
        text = row["Control Statement"]
        enhancements = row.get("Enhancements", "")

        if ctrl == "AC-2":
            continue  # AC-2 already in template

        family_actions[ctrl] = parse_control(ctrl, name, text, enhancements)

    return family_actions
