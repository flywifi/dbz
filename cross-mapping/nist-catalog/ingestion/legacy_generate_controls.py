# ============================================================
# generate_controls.py
# CLI wrapper for full NIST 800-53 Rev5 control generator
# ============================================================

import argparse
import json
from pathlib import Path

from generate_controls_core import get_all_families
from generate_controls_builder import (
    assemble_family,
    assemble_all_families
)


# ------------------------------------------------------------
# OUTPUT DIRECTORIES
# ------------------------------------------------------------

OUTPUT_ROOT = Path("output")
OUTPUT_FAMILIES = OUTPUT_ROOT / "families"
OUTPUT_MASTER = OUTPUT_ROOT / "master"

OUTPUT_FAMILIES.mkdir(parents=True, exist_ok=True)
OUTPUT_MASTER.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# WRITE HELPERS
# ------------------------------------------------------------

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"[✓] Wrote {path}")


# ------------------------------------------------------------
# GENERATION MODES
# ------------------------------------------------------------

def generate_single_family(fam):
    """
    Builds and exports one NIST 800-53 family.
    """
    print(f"[*] Generating family {fam}…")
    data = assemble_family(fam)
    out_path = OUTPUT_FAMILIES / f"{fam}.json"
    write_json(out_path, data)


def generate_multiple_families(families):
    """
    Builds and exports multiple families.
    """
    for fam in families:
        generate_single_family(fam)


def generate_all():
    """
    Builds and exports ALL NIST 800-53 controls across all families.
    """
    print("[*] Generating ALL NIST families…")
    data = assemble_all_families()

    # Write master file
    master_path = OUTPUT_MASTER / "NIST_800_53_FULL_ALL_FAMILIES.json"
    write_json(master_path, data)

    # Also write per-family files
    for fam, fam_data in data.items():
        out_path = OUTPUT_FAMILIES / f"{fam}.json"
        write_json(out_path, fam_data)


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="NIST SP 800-53 Rev5 Full Control Generator"
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate full 800-53 database (all families)"
    )

    parser.add_argument(
        "--family",
        type=str,
        help="Generate a single family (e.g., AC)"
    )

    parser.add_argument(
        "--families",
        nargs="+",
        help="Generate multiple families (e.g., AC AU CM)"
    )

    args = parser.parse_args()

    if args.all:
        generate_all()
        return

    if args.family:
        generate_single_family(args.family.upper())
        return

    if args.families:
        fams = [f.upper() for f in args.families]
        generate_multiple_families(fams)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
    