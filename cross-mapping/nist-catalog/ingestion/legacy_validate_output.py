# ============================================================
# validate_output.py
# Validation suite for full NIST 800-53 Rev5 JSON database
# ============================================================

import json
from pathlib import Path
from generate_controls_core import (
    DF_53,
    CCI_MAP,
    MAP_171,
    MAP_172,
    MAP_HITRUST,
    ACTION_FIELDS,
)
from generate_controls_builder import EMPTY_FEDRAMP_BLOCK


# ------------------------------------------------------------
# PATHS
# ------------------------------------------------------------

OUTPUT_MASTER = Path("output/master/NIST_800_53_FULL_ALL_FAMILIES.json")
VALIDATION_REPORT = Path("output/master/validation_report.json")


# ------------------------------------------------------------
# LOAD GENERATED DATA
# ------------------------------------------------------------

def load_generated():
    if not OUTPUT_MASTER.exists():
        raise FileNotFoundError(
            f"Cannot find generated master file: {OUTPUT_MASTER}"
        )
    with open(OUTPUT_MASTER, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------
# VALIDATION HELPERS
# ------------------------------------------------------------

def validate_schema_for_action(action):
    """
    Ensure required schema fields exist with proper type.
    """
    errors = []

    for field in ACTION_FIELDS:
        if field not in action:
            errors.append(f"Missing field '{field}'")
        else:
            # Validate type for key fields
            if field == "mapped_ccis" and not isinstance(action[field], list):
                errors.append("mapped_ccis must be a list")

            if field == "nist_examination_method" and not isinstance(action[field], list):
                errors.append("nist_examination_method must be a list")

    return errors


def validate_fedramp_block(block):
    """
    Option A: Every control must include FedRAMP context even if empty.
    """
    errors = []

    required_keys = list(EMPTY_FEDRAMP_BLOCK.keys())

    for k in required_keys:
        if k not in block:
            errors.append(f"Missing FedRAMP field '{k}'")

    # Validate baselines structure
    for baseline in ["li_saas", "low", "moderate", "high"]:
        if baseline not in block["baselines"]:
            errors.append(f"Missing baseline '{baseline}'")
        else:
            if "base_control_requirements" not in block["baselines"][baseline]:
                errors.append(f"Missing base_control_requirements in baseline '{baseline}'")

    return errors


# ------------------------------------------------------------
# MAIN VALIDATION
# ------------------------------------------------------------

def run_validation():
    print("[*] Starting validation…")

    data = load_generated()

    errors = []

    # VALIDATE EACH FAMILY
    for fam, fam_controls in data.items():
        # Validate existence of controls
        df_family = DF_53[DF_53["Family"] == fam]

        for _, row in df_family.iterrows():
            ctrl_id = row["Control ID"]

            if ctrl_id == "AC-2":
                # AC-2 is from template; skip
                continue

            if ctrl_id not in fam_controls:
                errors.append(f"[MISSING CONTROL] {fam} → {ctrl_id}")
                continue

            ctrl_obj = fam_controls[ctrl_id]

            # Validate FedRAMP context
            if "fedramp_context" not in ctrl_obj:
                errors.append(f"[NO FEDRAMP CONTEXT] {ctrl_id}")
            else:
                fedramp_errs = validate_fedramp_block(ctrl_obj["fedramp_context"])
                for e in fedramp_errs:
                    errors.append(f"[FEDRAMP] {ctrl_id}: {e}")

            # Validate action schemas in LI-SaaS
            actions = ctrl_obj["fedramp_context"]["baselines"]["li_saas"]["base_control_requirements"]
            for act in actions:
                errs = validate_schema_for_action(act)
                for e in errs:
                    errors.append(f"[ACTION SCHEMA] {ctrl_id}: {e}")

            # Validate 171 mapping count
            if ctrl_id in MAP_171:
                expected = len(MAP_171[ctrl_id])
                actual = len(ctrl_obj["nist_cui_context"]["nist_sp_800_171_r3"]["requirements"])
                if expected != actual:
                    errors.append(
                        f"[171 MISMATCH] {ctrl_id}: expected {expected}, got {actual}"
                    )

            # Validate 172 mapping count
            if ctrl_id in MAP_172:
                expected = len(MAP_172[ctrl_id])
                actual = len(ctrl_obj["nist_cui_context"]["nist_sp_800_172"]["requirements"])
                if expected != actual:
                    errors.append(
                        f"[172 MISMATCH] {ctrl_id}: expected {expected}, got {actual}"
                    )

            # Validate HITRUST mapping
            if ctrl_id in MAP_HITRUST:
                if "controls" not in ctrl_obj["hitrust_context"]:
                    errors.append(f"[HITRUST MISSING] {ctrl_id}")

    # Output report
    if not errors:
        print("[✓] VALIDATION PASSED – No issues detected.")
    else:
        print(f"[!] VALIDATION FAILED – {len(errors)} issues found:")
        for e in errors:
            print("   -", e)

    # Write JSON report
    with open(VALIDATION_REPORT, "w", encoding="utf-8") as f:
        json.dump({"errors": errors}, f, indent=2)

    print(f"[✓] Validation report saved to {VALIDATION_REPORT}")


# ------------------------------------------------------------
# CLI ENTRY
# ------------------------------------------------------------

if __name__ == "__main__":
    run_validation()
