# ============================================================
# generate_controls_builder.py
# Schema assembler, normalizer, and full control builder
# ============================================================

import json
from pathlib import Path

from generate_controls_core import (
    AC2_TEMPLATE,
    ACTION_FIELDS,
    MAP_171,
    MAP_172,
    MAP_HITRUST,
    get_all_families,
    build_family_controls,
)


# ------------------------------------------------------------
# UNIVERSAL FEDRAMP BLOCK (Option A)
# ------------------------------------------------------------
# Every control in every family gets a FedRAMP block,
# even if NULL applicability, to enforce strict schema.

EMPTY_FEDRAMP_BLOCK = {
    "authorization_boundary": "",
    "baselines": {
        "li_saas": { "base_control_requirements": [] },
        "low":     { "base_control_requirements": [] },
        "moderate":{ "base_control_requirements": [] },
        "high":    { "base_control_requirements": [] }
    },
    "fedramp_20x_automation": []
}


# ------------------------------------------------------------
# UNIVERSAL HIPAA BLOCK
# ------------------------------------------------------------

EMPTY_HIPAA_BLOCK = {
    "legal_mandates": [],
    "nprm_2025_proposed_updates": {
        "mandates": []
    }
}


# ------------------------------------------------------------
# UNIVERSAL NIST CUI CONTEXT (171 & 172)
# ------------------------------------------------------------

EMPTY_NIST_CUI_BLOCK = {
    "nist_sp_800_171_r3": {
        "description": "",
        "requirements": []
    },
    "nist_sp_800_172": {
        "description": "",
        "requirements": []
    }
}


# ------------------------------------------------------------
# UNIVERSAL SOC CONTEXT
# ------------------------------------------------------------

EMPTY_SOC_BLOCK = {
    "soc1": {
        "report_type": "",
        "control_objectives": []
    },
    "soc2": {
        "framework_version": "",
        "relevant_criteria": []
    }
}


# ------------------------------------------------------------
# UNIVERSAL HITRUST CONTEXT
# ------------------------------------------------------------

EMPTY_HITRUST_CONTEXT = {
    "controls": []
}


# ------------------------------------------------------------
# SCHEMA ENFORCEMENT
# ------------------------------------------------------------

def enforce_action_schema(action):
    """
    Ensures each action item conforms to AC-2 template schema.
    Missing fields are inserted as empty placeholders.
    """
    normalized = {}

    for field in ACTION_FIELDS:
        if field in action:
            normalized[field] = action[field]
        else:
            # Fill missing fields with empty values
            if field == "mapped_ccis":
                normalized[field] = []
            elif field == "nist_examination_method":
                normalized[field] = []
            else:
                normalized[field] = ""

    return normalized


def build_fedramp_block(actions):
    """
    Places action items into all FedRAMP baselines.
    Even if no applicability exists, Option A requires full structure.
    """
    block = json.loads(json.dumps(EMPTY_FEDRAMP_BLOCK))

    for baseline in block["baselines"]:
        block["baselines"][baseline]["base_control_requirements"].extend(actions)

    return block


def build_hipaa_block(control_id, actions):
    """
    Because HIPAA is mapped primarily via CCI AND you chose Option 1,
    every control receives a HIPAA block, even if empty.
    """
    block = json.loads(json.dumps(EMPTY_HIPAA_BLOCK))

    # HIPAA mapping via CCI is possible, but only if CCIs overlap.
    # HIPAA context will remain empty unless direct mapping exists.
    return block


def build_nist_cui_block(control_id):
    """
    Builds 171 & 172 mappings for a given control.
    """
    block = json.loads(json.dumps(EMPTY_NIST_CUI_BLOCK))

    if control_id in MAP_171:
        block["nist_sp_800_171_r3"]["requirements"].extend(
            MAP_171[control_id]
        )

    if control_id in MAP_172:
        block["nist_sp_800_172"]["requirements"].extend(
            MAP_172[control_id]
        )

    return block


def build_hitrust_block(control_id):
    """
    Based on HITRUST crosswalk (CCI-driven).
    """
    block = json.loads(json.dumps(EMPTY_HITRUST_CONTEXT))

    if control_id in MAP_HITRUST:
        block["controls"].extend(MAP_HITRUST[control_id])

    return block


def build_soc_block(control_id, actions):
    """
    SOC 1 and SOC 2 mappings are indirectly determined via CCI.
    For now, Option 1 requires uniform blocks regardless of mapping availability.
    """
    block = json.loads(json.dumps(EMPTY_SOC_BLOCK))
    return block


# ------------------------------------------------------------
# CONTROL ASSEMBLER
# ------------------------------------------------------------

def assemble_control(control_id, actions):
    """
    Builds a FULL AC-2-style JSON block for a single control across all contexts.
    """

    # Normalize all action schemas
    norm_actions = [enforce_action_schema(a) for a in actions]

    assembled = {
        "fedramp_context": build_fedramp_block(norm_actions),
        "hipaa_context": build_hipaa_block(control_id, norm_actions),
        "nist_cui_context": build_nist_cui_block(control_id),
        "soc_context": build_soc_block(control_id, norm_actions),
        "hitrust_context": build_hitrust_block(control_id)
    }

    return assembled


# ------------------------------------------------------------
# FAMILY ASSEMBLER
# ------------------------------------------------------------

def assemble_family(family):
    """
    Builds all controls within a NIST family.
    """
    controls_raw = build_family_controls(family)
    family_output = {}

    for ctrl_id, actions in controls_raw.items():
        family_output[ctrl_id] = assemble_control(ctrl_id, actions)

    return family_output


# ------------------------------------------------------------
# MASTER ASSEMBLER
# ------------------------------------------------------------

def assemble_all_families():
    """
    Returns nested JSON structure for FULL NIST 800-53 catalog.
    """
    output = {}

    families = get_all_families()
    for fam in families:
        output[fam] = assemble_family(fam)

    return output
    