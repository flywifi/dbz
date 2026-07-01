#!/usr/bin/env python3
"""
instruction_blocks.py — deterministic decomposition of a skill's instruction files into
classified blocks, and enumeration of the block pairs an LLM should check for interference.

This is the deterministic scaffolding for the instruction-level checker (Arbiter's key
step): segment SKILL.md / MAINTAINER.md by section, classify each section, and enumerate
the high-risk pairs. The semantic contradiction *judgment* is done by the LLM adversarial
pass (skills/atoms/instruction-audit) — this file does NOT judge; it only prepares the
work so the judgment is reliable and the same input always yields the same pairs.

Block classes (dbz-adapted from Arbiter's Objectives/Constraints/Instructions/Examples/Context):
    scope        — what the skill is for
    constraint   — non-negotiables, hard rules, "never/always"
    procedure     — the steps / the loop / how it runs
    do_not_use   — the "Do NOT use for" exclusions
    io_contract  — input/output schema
    reference    — references, examples, notes

Interference rules the enumerated pairs are checked against (by the LLM layer):
    direct_contradiction · goal_conflict · constraint_violation · scope_mismatch · precedence_ambiguity

Run:
    python3 instruction_blocks.py path/to/SKILL.md [MAINTAINER.md ...]
    python3 instruction_blocks.py --self-test
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")

# Deterministic heading→class rules, checked in order (first match wins).
_CLASS_RULES = [
    ("do_not_use", ("do not use", "do not use for", "don't use")),
    ("io_contract", ("input schema", "output schema", "input/output", "contract", "schema")),
    ("constraint", ("non-negotiable", "constraint", "hard rule", "must", "never", "always", "policy")),
    ("procedure", ("procedure", "the loop", "steps", "workflow", "how it works", "how to", "process")),
    ("reference", ("reference", "example", "notes", "see also")),
    ("scope", ("scope", "purpose", "overview", "what this")),
]

# High-risk pairs to hand the LLM (which class-pairs most often carry contradictions).
_CHECK_PAIRS = [
    ("scope", "do_not_use"),      # affirmed use vs excluded use
    ("scope", "constraint"),      # goal vs hard rule
    ("constraint", "procedure"),  # rule vs the steps that might breach it
    ("io_contract", "scope"),     # declared shape vs described behavior
    ("constraint", "do_not_use"), # overlapping/again-contradictory limits
]


def _classify(heading: str) -> str:
    h = heading.strip().lower()
    for cls, keys in _CLASS_RULES:
        if any(k in h for k in keys):
            return cls
    return "reference"


def decompose(md_text: str) -> List[Dict[str, Any]]:
    """Split markdown into classified blocks by heading. Deterministic."""
    blocks: List[Dict[str, Any]] = []
    cur = {"heading": "(preamble)", "cls": "scope", "start": 1, "lines": []}
    for i, line in enumerate(md_text.splitlines(), 1):
        m = _HEADING.match(line)
        if m:
            if cur["lines"]:
                blocks.append(cur)
            cur = {"heading": m.group(2).strip(), "cls": _classify(m.group(2)), "start": i, "lines": []}
        else:
            cur["lines"].append(line)
    if cur["lines"]:
        blocks.append(cur)
    # The opening block (H1 title + intro) states the skill's purpose — that is its scope.
    if blocks and blocks[0]["cls"] == "reference":
        blocks[0]["cls"] = "scope"
    for b in blocks:
        b["text"] = "\n".join(b.pop("lines")).strip()
    return blocks


def enumerate_pairs(files: List[Path]) -> Dict[str, Any]:
    """Decompose each file and enumerate the block pairs to check (cross-file included)."""
    by_file = {}
    for f in files:
        by_file[str(f)] = decompose(f.read_text(encoding="utf-8"))
    # index blocks by class across all files
    by_class: Dict[str, List[Dict[str, Any]]] = {}
    for fpath, blocks in by_file.items():
        for b in blocks:
            b2 = {"file": fpath, "heading": b["heading"], "cls": b["cls"], "start": b["start"], "text": b["text"]}
            by_class.setdefault(b["cls"], []).append(b2)
    pairs = []
    for a_cls, b_cls in _CHECK_PAIRS:
        for a in by_class.get(a_cls, []):
            for b in by_class.get(b_cls, []):
                if a is b:
                    continue
                pairs.append({
                    "rule_candidates": ["direct_contradiction", "goal_conflict", "constraint_violation",
                                        "scope_mismatch", "precedence_ambiguity"],
                    "a": {"file": a["file"], "section": a["heading"], "cls": a["cls"]},
                    "b": {"file": b["file"], "section": b["heading"], "cls": b["cls"]},
                })
    # deterministic ordering
    pairs.sort(key=lambda p: (p["a"]["cls"], p["a"]["section"], p["b"]["cls"], p["b"]["section"]))
    return {"files": [str(f) for f in files],
            "block_count": sum(len(v) for v in by_file.values()),
            "class_histogram": {k: len(v) for k, v in sorted(by_class.items())},
            "pairs_to_check": pairs,
            "human_review_required": True}


_ROOT = Path(__file__).resolve().parents[3]


def _iter_skills(root: Path):
    """(dir, is_atom) for every real skill — atoms under skills/atoms/, composite skills
    under skills/ — excluding templates, shared, and golden test fixtures."""
    out = []
    adir = root / "skills" / "atoms"
    if adir.exists():
        out += [(d, True) for d in sorted(adir.iterdir())
                if d.is_dir() and d.name != "atom-template" and not d.name.startswith(".")]
    sdir = root / "skills"
    if sdir.exists():
        out += [(d, False) for d in sorted(sdir.iterdir())
                if d.is_dir() and d.name not in ("atoms", "shared") and not d.name.startswith(".")
                and (d / "SKILL.md").exists()]
    return [(d, a) for d, a in out if "golden" not in d.parts]


def audit_all_structure(root: Path = _ROOT) -> List[Dict[str, Any]]:
    """Deterministic structure gate: every skill decomposes; every atom has scope + do_not_use.
    FP-free and headless — the part of instruction-audit that can gate CI/pre-commit."""
    findings = []
    for d, is_atom in _iter_skills(root):
        files = [d / "SKILL.md"] + ([d / "MAINTAINER.md"] if (d / "MAINTAINER.md").exists() else [])
        try:
            cls = set()
            for f in files:
                for b in decompose(f.read_text(encoding="utf-8")):
                    cls.add(b["cls"])
        except Exception as e:  # noqa: BLE001
            findings.append({"skill": d.name, "severity": "blocking",
                             "issue": f"instruction decomposition error: {e}"})
            continue
        if "scope" not in cls:
            findings.append({"skill": d.name, "severity": "blocking",
                             "issue": "no scope/purpose block found in SKILL.md"})
        if is_atom and "do_not_use" not in cls:
            findings.append({"skill": d.name, "severity": "blocking",
                             "issue": "atom SKILL.md has no 'Do NOT use for' block (dbz convention)"})
    findings.sort(key=lambda x: (x["severity"], x["skill"], x["issue"]))
    return findings


def _audit_all(root: Path = _ROOT) -> int:
    findings = audit_all_structure(root)
    n = len(_iter_skills(root))
    if findings:
        print(f"instruction-audit (structure) — {len(findings)} blocking finding(s) across {n} skill(s):")
        for f in findings:
            print(f"  ✗ [{f['severity']}] {f['skill']}: {f['issue']}")
        return 1
    print(f"instruction-audit (structure): OK — all {n} skills decompose; every atom has "
          f"scope + a 'Do NOT use for' block.")
    return 0


def _self_test() -> int:
    sample = ("# demo\nUse this to edit files.\n\n## Do NOT use for\n- reading files\n\n"
              "## Non-negotiables\n- never edit files\n\n## Input Schema\n```json\n{}\n```\n")
    blocks = decompose(sample)
    classes = {b["cls"] for b in blocks}
    ok = {"scope", "do_not_use", "constraint", "io_contract"} <= classes
    # a Scope↔DoNotUse and Scope↔Constraint pair must be enumerated for the LLM to judge
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
        tf.write(sample); p = Path(tf.name)
    try:
        pairs = enumerate_pairs([p])["pairs_to_check"]
    finally:
        p.unlink()
    have = {(x["a"]["cls"], x["b"]["cls"]) for x in pairs}
    ok = ok and ("scope", "do_not_use") in have and ("scope", "constraint") in have
    print("instruction_blocks self-test:", "PASS" if ok else "FAIL",
          f"(classes={sorted(classes)}, pairs={len(pairs)})")
    return 0 if ok else 1


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--self-test" in argv:
        return _self_test()
    if "--audit-all" in argv:
        return _audit_all()
    if not argv:
        print("usage: instruction_blocks.py <SKILL.md> [MAINTAINER.md ...] | --self-test | --audit-all",
              file=sys.stderr)
        return 2
    out = enumerate_pairs([Path(a) for a in argv])
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
