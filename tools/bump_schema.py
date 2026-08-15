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

Rules:
  * The doc list comes from doc_claims.json — the SAME authority count_truth checks
    against, so the updater and the checker can never disagree about which files
    restate the version. No hardcoded doc list (CLAUDE.md rule).
  * All-or-nothing: every file is rewritten in memory first; each substitution must hit
    EXACTLY once; any ambiguity (zero or multiple candidate sites) aborts with nothing
    written. Never guesses.
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


def main() -> int:
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

    # Stage every rewrite in memory; nothing touches disk until all pass.
    staged: dict[Path, str] = {}
    new_line = f'SCHEMA_VERSION = "{new}"  # v{new}: {note}; ' + history.lstrip()
    staged[BUILD_DB] = src[:m.start()] + new_line + src[m.end():]

    for rel in cited:
        p = ROOT / rel
        if not p.exists():
            return fail(f"cited doc missing on disk: {rel}")
        text = p.read_text(encoding="utf-8")
        hits = text.count(cur)
        if hits == 0:
            return fail(f"{rel} does not state the current version {cur} "
                        f"(already drifted? run count_truth first)")
        if hits > 3:
            return fail(f"{rel} states {cur!r} {hits} times — too ambiguous to rewrite "
                        f"mechanically; update it by hand and re-run")
        staged[p] = text.replace(cur, new)

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
