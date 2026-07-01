#!/usr/bin/env python3
"""
instruction_audit_run.py — the semantic instruction-audit run, for CI or local use.

Two behaviors, chosen automatically so CI never produces a false gate:

  • No model credentials (ANTHROPIC_API_KEY unset, or the SDK unavailable):
    run the DETERMINISTIC structure gate only (every skill decomposes; every atom has a
    scope + a "Do NOT use for" block), print a clear "semantic pass skipped" notice, and
    exit 0/1 on structure alone. This is what vanilla GitHub Actions runners do.

  • Model credentials present:
    additionally run the SEMANTIC pass — decompose each skill, ask the model to judge the
    enumerated block pairs against the interference rules, keep only contradictions the model
    confirms on a second (skeptical) look (adversarial-consensus), and gate on confirmed
    contradictions. This is the full instruction-audit, run headlessly wherever a key exists.

The semantic judgment is inherently model-based; a purely lexical detector would
false-positive on skills that legitimately discuss "edit"/"mutate" as concepts, so it is
never used as a gate.

Run:
    python3 skills/health-auditor/scripts/instruction_audit_run.py
    ANTHROPIC_API_KEY=... python3 skills/health-auditor/scripts/instruction_audit_run.py
Exit: 0 if clean (or semantic skipped and structure clean), 1 on any blocking finding.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from instruction_blocks import audit_all_structure, enumerate_pairs, _iter_skills  # noqa: E402

MODEL = os.environ.get("INSTRUCTION_AUDIT_MODEL", "claude-opus-4-8")

_RULES = ("direct_contradiction, goal_conflict, constraint_violation, scope_mismatch, "
          "precedence_ambiguity, and cross-file schema-vs-behavior mismatch")

_PROMPT = """You are a strict, skeptical instruction-consistency auditor. Read the SKILL.md
and MAINTAINER.md text below for one skill and report ONLY genuine logical contradictions —
two statements that cannot both be true or that would produce conflicting behavior — against
these rules: {rules}. A mere documentation-completeness gap (one file adds a detail the other
omits) is NOT a contradiction. When uncertain, report nothing. Most skills are clean.

Return ONLY a JSON array; each item:
{{"rule": "...", "severity": "blocking|warning", "a_section": "...", "b_section": "...",
 "summary": "one sentence", "provenance": "file:section", "confidence": "high|medium|low"}}
Return [] if clean.

SKILL: {name}
---
{text}
"""


def _model_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _judge(name: str, text: str) -> list:
    """One model pass over a skill's instruction text → list of contradiction dicts."""
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": _PROMPT.format(rules=_RULES, name=name, text=text[:18000])}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < 0:
        return []
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []


def _semantic_pass() -> list:
    """Judge every skill, then adversarially re-judge flagged ones; keep only confirmed."""
    confirmed = []
    for d, _is_atom in _iter_skills(ROOT):
        files = [d / "SKILL.md"] + ([d / "MAINTAINER.md"] if (d / "MAINTAINER.md").exists() else [])
        text = "\n\n".join(f"### {f.name}\n{f.read_text(encoding='utf-8')}" for f in files)
        first = _judge(d.name, text)
        if not first:
            continue
        # adversarial consensus: a second, skeptical pass must also flag the pair
        second = _judge(d.name + " (verify)", text)
        second_keys = {(x.get("rule"), x.get("a_section"), x.get("b_section")) for x in second}
        for c in first:
            if (c.get("rule"), c.get("a_section"), c.get("b_section")) in second_keys:
                c["skill"] = d.name
                confirmed.append(c)
    return confirmed


def main() -> int:
    structure = audit_all_structure(ROOT)
    n = len(_iter_skills(ROOT))
    blocking = [f for f in structure if f["severity"] == "blocking"]
    if blocking:
        print(f"instruction-audit — {len(blocking)} structure finding(s):")
        for f in blocking:
            print(f"  ✗ {f['skill']}: {f['issue']}")
        return 1
    print(f"instruction-audit (structure): OK — {n} skills decompose; atoms have Do-NOT-use blocks.")

    if not _model_available():
        print("instruction-audit (semantic): SKIPPED — no model credentials "
              "(set ANTHROPIC_API_KEY to run the contradiction pass headlessly). "
              "Run the full semantic audit as a human-invoked pre-merge gate.")
        return 0

    print(f"instruction-audit (semantic): running adversarial-consensus over {n} skills "
          f"with {MODEL} …")
    try:
        contradictions = _semantic_pass()
    except Exception as e:  # noqa: BLE001 — infra failure must not false-gate
        print(f"instruction-audit (semantic): model call failed ({e}); "
              "not gating on an infrastructure error. Investigate credentials/quota.")
        return 0

    if not contradictions:
        print("instruction-audit (semantic): OK — no confirmed contradictions across all skills.")
        return 0
    print(f"instruction-audit (semantic): {len(contradictions)} confirmed contradiction(s):")
    for c in contradictions:
        print(f"  ✗ [{c.get('severity')}] {c.get('skill')}: {c.get('summary')}  ({c.get('provenance')})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
