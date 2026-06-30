#!/usr/bin/env python3
"""
JSON-Schema validation for the generated catalog.

Validates every generated control record against the formal handoff contract
schema (cross-mapping/schema/handoff_contract_v1.1.0.schema.json) using the
jsonschema library. This is the authoritative gate: if a record fails here,
the handoff contract is broken for downstream consumers.

Usage:
    python3 validate_schema.py [--family AC] [--schema PATH] [--out-dir DIR]
"""
import glob
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent
_OUTPUT_DIR = _HERE.parent / "output"
_SCHEMA = _REPO_ROOT / "cross-mapping" / "schema" / "handoff_contract_v1.1.0.schema.json"


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--family", "-f", default=None,
                        help="validate only this family's output file")
    parser.add_argument("--schema", "-s", default=str(_SCHEMA))
    parser.add_argument("--out-dir", "-o", default=str(_OUTPUT_DIR))
    args = parser.parse_args()

    try:
        import jsonschema
    except ImportError:
        print("[✗] jsonschema not installed. Run: pip install jsonschema")
        return 2

    schema = json.load(open(args.schema, encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    out_dir = Path(args.out_dir)

    if args.family:
        files = [out_dir / f"NIST_800_53_{args.family}.json"]
    else:
        files = [Path(p) for p in sorted(glob.glob(str(out_dir / "NIST_800_53_*.json")))
                 if "FULL" not in p]

    total, errs = 0, 0
    err_samples = []
    for fp in files:
        if not fp.exists():
            print(f"[!] missing: {fp}")
            continue
        catalog = json.load(open(fp, encoding="utf-8"))
        for cid, record in catalog.items():
            total += 1
            for e in validator.iter_errors(record):
                errs += 1
                if len(err_samples) < 25:
                    err_samples.append(f"{cid}: {e.message[:100]} @ {list(e.path)[:4]}")

    print(f"[*] Validated {total} control records against {Path(args.schema).name}")
    if errs:
        print(f"\n[✗] SCHEMA VALIDATION FAILED — {errs} errors:")
        for s in err_samples:
            print(f"    {s}")
        return 1
    print("\n[✓] SCHEMA VALIDATION PASSED — all records conform to handoff contract v1.1.0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
