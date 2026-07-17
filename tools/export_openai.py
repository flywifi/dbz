#!/usr/bin/env python3
"""
export_openai.py — generate OpenAI-function-format tool schemas from the atom registry.

dbz's query power lives inside "clone the repo and run python". This generator emits
the same six high-value operations as OpenAI-function schemas so they can ride on a
ChatGPT Action / Gemini function / any OpenAI-function-format consumer — no
hand-written schemas, no drift. Output is deterministic (sorted keys) so regeneration
is diffable and `--check` can be a drift guard.

SCOPE (recorded, honest): this ships *schemas + docs*, NOT a hosted HTTP service. The
operator hosts `dbz_query.py` behind their own action endpoint; we ship the contract.
Format is JSON (not YAML) because pyyaml is outside the stdlib+pandas/openpyxl deps
policy — JSON is a valid subset and `implementation/README.md` states this.

Each exported atom's parameter schema is built from the atom's EXISTING `input_schema`
in skills/atoms/atoms.json (the "type — description" strings are parsed; a trailing '?'
or the word 'optional' marks a parameter non-required), plus an optional per-atom
`export` block ({name, description, invocation}) that overrides display fields. The
generator NEVER restructures atoms.json.

Usage:
  python3 tools/export_openai.py            # (re)write implementation/gpt/api/
  python3 tools/export_openai.py --check    # exit 1 if committed output would change
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATOMS = ROOT / "skills" / "atoms" / "atoms.json"
OUT_DIR = ROOT / "implementation" / "gpt" / "api"
SKILLS_DIR = OUT_DIR / "skills"

EXPORT_IDS = ["overlap-query", "master-crosswalk", "compliance-crosswalk",
              "gap-analysis", "control-search", "cfr-lookup"]

_TYPE_MAP = {"string": "string", "str": "string", "integer": "integer", "int": "integer",
             "number": "number", "float": "number", "boolean": "boolean", "bool": "boolean",
             "array": "array", "object": "object"}


def _parse_field(spec: str):
    """'string? — optional NIST family filter' -> ('string', desc, required?)."""
    head, _, desc = spec.partition("—")
    head = head.strip()
    desc = desc.strip() or spec.strip()
    optional = head.endswith("?") or "optional" in spec.lower()
    base = head.rstrip("?").strip().split()[0].lower() if head else "string"
    return _TYPE_MAP.get(base, "string"), desc, not optional


def _atom_to_function(atom: dict) -> dict:
    exp = atom.get("export", {})
    props, required = {}, []
    for key, spec in (atom.get("input_schema") or {}).items():
        typ, desc, req = _parse_field(spec if isinstance(spec, str) else json.dumps(spec))
        props[key] = {"type": typ, "description": desc}
        if req:
            required.append(key)
    return {
        "name": exp.get("name", atom["id"].replace("-", "_")),
        "description": exp.get("description", atom.get("label", atom["id"])),
        "parameters": {
            "type": "object",
            "properties": props,
            "required": sorted(required),
            "additionalProperties": False,
        },
        "x-dbz": {
            "atom_id": atom["id"],
            "script": atom.get("script"),
            "invocation": exp.get("invocation",
                                  f"python3 {atom.get('script')} (see the atom's SKILL.md)"),
            "note": "GENERATED from skills/atoms/atoms.json — edit the atom, not this file.",
        },
    }


def build():
    reg = json.loads(ATOMS.read_text(encoding="utf-8"))
    by_id = {a["id"]: a for a in reg["atoms"]}
    missing = [i for i in EXPORT_IDS if i not in by_id]
    if missing:
        raise SystemExit(f"atoms.json is missing export targets: {missing}")
    functions = [_atom_to_function(by_id[i]) for i in EXPORT_IDS]
    combined = {
        "_generated_by": "tools/export_openai.py",
        "_note": "OpenAI-function schemas generated from the atom registry. Operator hosts "
                 "dbz_query.py behind their own endpoint; these are the tool contracts only.",
        "schema_version": reg.get("schema_version"),
        "functions": functions,
    }
    per_atom = {f["x-dbz"]["atom_id"]: f for f in functions}
    return combined, per_atom


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write():
    combined, per_atom = build()
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "tools.json").write_text(_dump(combined), encoding="utf-8")
    for atom_id, fn in per_atom.items():
        (SKILLS_DIR / f"{atom_id}.json").write_text(_dump(fn), encoding="utf-8")
    print(f"wrote {OUT_DIR / 'tools.json'} + {len(per_atom)} per-atom schemas")


def check():
    combined, per_atom = build()
    stale = []
    tj = OUT_DIR / "tools.json"
    if not tj.exists() or tj.read_text(encoding="utf-8") != _dump(combined):
        stale.append("tools.json")
    for atom_id, fn in per_atom.items():
        p = SKILLS_DIR / f"{atom_id}.json"
        if not p.exists() or p.read_text(encoding="utf-8") != _dump(fn):
            stale.append(f"skills/{atom_id}.json")
    # any committed schema file no longer produced by the generator is also drift
    for p in sorted(SKILLS_DIR.glob("*.json")) if SKILLS_DIR.exists() else []:
        if p.stem not in per_atom:
            stale.append(f"skills/{p.name} (orphaned)")
    if stale:
        print("[export drift] regenerate with tools/export_openai.py:")
        for s in stale:
            print("  stale:", s)
        return 1
    print(f"[export OK] {len(per_atom)} schemas + tools.json match the registry")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="generate OpenAI-function schemas from atoms.json")
    ap.add_argument("--check", action="store_true", help="fail if committed output would change")
    a = ap.parse_args(argv)
    if a.check:
        return check()
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
