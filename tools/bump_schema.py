#!/usr/bin/env python3
"""
bump_schema.py — bump SCHEMA_VERSION everywhere it is restated, atomically (phase 41).

Why this exists: the schema version lives in build_db.py AND is restated in every doc
listed in doc_claims.json -> schema_version.cited_in. Bumping it was a manual 5-file
ritual; the drift window that ritual opens was entered four times in one working session
(3.15, 3.16, 3.17 caught locally, 3.18 escaped to a red CI run). This tool makes a
half-landed bump impossible: either every restatement moves, or nothing does.

Usage:
    python3 tools/bump_schema.py 3.19 "one-line note for the version-history comment"
    python3 tools/bump_schema.py --selftest

Rules:
  * The doc list comes from doc_claims.json — the SAME authority count_truth checks
    against, so the updater and the checker can never disagree about which files
    restate the version. No hardcoded doc list (CLAUDE.md rule).
  * All-or-nothing: every file is rewritten in memory first; a cited doc with no recognised
    current-version statement aborts with nothing written. Never guesses.
  * Only a doc's CURRENT-version statement moves: the spans captured by doc_claims.json ->
    schema_version.context_patterns whose value equals the current version (count_truth reads
    the same patterns in every-occurrence mode). Any other mention is history — a phase row
    recording which schema that phase shipped — and is never touched. Until phase 53 the rule
    was text.replace(cur, new), which turned STATE's phase-40 row from "Schema 3.18" into
    "Schema 3.19" at the 3.18 -> 3.19 bump (commit e4a1d3f).
  * Finishes by running count_truth and reporting its verdict — the bump is only done
    when the checker this tool exists to satisfy passes.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_DB = ROOT / "cross-mapping" / "engine" / "build_db.py"
CLAIMS = ROOT / "canonical-sources" / "doc_claims.json"

_VER_RE = re.compile(r"^\d+\.\d+$")


def fail(msg: str) -> int:
    print(f"[bump-schema ABORT] {msg} — nothing written")
    return 1


def plan_rewrite(text: str, cur: str, new: str, patterns: list) -> tuple:
    """(rewritten text, statements rewritten). Only spans captured by a context pattern whose
    captured value equals `cur` are current-version statements; every other mention of `cur` is
    history and stays. The rule before phase 53 was text.replace(cur, new), which turned STATE's
    phase-40 row from 'Schema 3.18' into 'Schema 3.19' at the 3.18 -> 3.19 bump (commit e4a1d3f)."""
    spans = sorted({m.span(1) for pat in patterns for m in re.finditer(pat, text) if m.group(1) == cur})
    out, last = [], 0
    for a, b in spans:
        out += [text[last:a], new]
        last = b
    out.append(text[last:])
    return "".join(out), len(spans)


def selftest() -> int:
    """The phase-50 defect as the fixture: one current statement beside two historical mentions."""
    pats = [r"\*\*DB schema:\*\* (\d+\.\d+)"]
    doc = ("- **DB schema:** 3.19 (phase 50: stig lifecycle)\n"
           "| 40 | SCF fan-out witness | Schema 3.18 (this row said 3.19 until phase 52) |\n"
           "| 50 | STIG retention | 20 DISA-dropped STIGs kept, flagged — schema 3.19 |\n")
    got, n = plan_rewrite(doc, "3.19", "3.20", pats)
    old_rule = doc.replace("3.19", "3.20")
    cases = [
        ("the current statement moves", "- **DB schema:** 3.20 (phase 50" in got and n == 1),
        ("both historical mentions stay", "said 3.19 until phase 52" in got and "schema 3.19 |" in got),
        ("the old replace-all rule rewrote history (the e4a1d3f defect)", old_rule.count("3.20") == 3 and old_rule != got),
        ("a doc with no recognised statement is refused, not guessed",
         plan_rewrite("schema 3.19 somewhere", "3.19", "3.20", pats)[1] == 0),
        ("a statement of another version is not touched",
         plan_rewrite("- **DB schema:** 3.18", "3.19", "3.20", pats) == ("- **DB schema:** 3.18", 0)),
    ]
    bad = [label for label, good in cases if not good]
    for label, good in cases:
        print(f"  [{'ok' if good else 'FAIL'}] {label}")
    print(f"[selftest] bump-schema: {len(cases) - len(bad)}/{len(cases)} passed")
    return 1 if bad else 0


def main() -> int:
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    new, note = sys.argv[1].strip(), sys.argv[2].strip()
    if not _VER_RE.match(new):
        return fail(f"{new!r} is not a well-formed version (expected N.NN)")
    if not note or "\n" in note:
        return fail("the note must be a single non-empty line")

    src = BUILD_DB.read_text(encoding="utf-8")
    m = re.search(r'SCHEMA_VERSION\s*=\s*"([^"]+)"\s*#\s*(.*)', src)
    if not m:
        return fail("SCHEMA_VERSION assignment not found in build_db.py")
    cur, history = m.group(1), m.group(2)
    if new == cur:
        return fail(f"already at {cur}")
    cur_major, cur_minor = (int(x) for x in cur.split("."))
    new_major, new_minor = (int(x) for x in new.split("."))
    if (new_major, new_minor) <= (cur_major, cur_minor):
        return fail(f"{new} does not increment {cur}")

    claims = json.loads(CLAIMS.read_text(encoding="utf-8"))
    entry = claims.get("claims", claims).get("schema_version", {})
    cited = entry.get("cited_in", [])
    if not cited:
        return fail("doc_claims.json carries no schema_version.cited_in list")
    patterns = entry.get("context_patterns") or []
    if not patterns:
        return fail("doc_claims.json schema_version carries no context_patterns (the statements to rewrite)")

    # Stage every rewrite in memory; nothing touches disk until all pass.
    staged: dict[Path, str] = {}
    new_line = f'SCHEMA_VERSION = "{new}"  # v{new}: {note}; ' + history.lstrip()
    staged[BUILD_DB] = src[:m.start()] + new_line + src[m.end():]

    for rel in cited:
        p = ROOT / rel
        if not p.exists():
            return fail(f"cited doc missing on disk: {rel}")
        text = p.read_text(encoding="utf-8")
        rewritten, n = plan_rewrite(text, cur, new, patterns)
        if n == 0:
            return fail(f"{rel} carries no current-version statement of {cur} that "
                        f"schema_version.context_patterns recognises (register its pattern in "
                        f"doc_claims.json, or run count_truth first if the doc already drifted)")
        staged[p] = rewritten

    for p, text in staged.items():
        p.write_text(text, encoding="utf-8")
        print(f"  updated {p.relative_to(ROOT)}")

    print(f"[bump-schema] {cur} -> {new} across {len(staged)} file(s); verifying:")
    rc = subprocess.run([sys.executable, str(ROOT / "tools" / "count_truth.py")],
                        cwd=ROOT).returncode
    if rc != 0:
        print("[bump-schema] count_truth FAILED after the bump — inspect before committing")
        return rc
    print("[bump-schema] count_truth PASS — bump complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
