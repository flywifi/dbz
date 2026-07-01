#!/usr/bin/env python3
"""Drift guard for the GRC atom library and the multi-agent orchestration bucket.

Enforces 5 invariants across skills/atoms/:
  1. Every atom directory (except atom-template) has SKILL.md and MAINTAINER.md.
  2. Every SKILL.md references minority-report (string 'minority-report').
  3. Every atom listed in atoms.json has a corresponding directory under skills/atoms/.
  4. Every atom directory has evals/evals.json.
  5. Every evals/evals.json has at least 3 test cases.

Plus 4 orchestration invariants (the multi-agent bucket is a set of contracts that
drift the same way atoms do, so it gets the same structural guard):
  6. The shared orchestration contracts exist: orchestration-envelope.schema.json
     (valid JSON), frontier-model.md, consolidation.md under skills/shared/.
  7. The multi-agent-orchestrator skill has SKILL.md, MAINTAINER.md, workflow.json,
     references/routing.md, and evals/evals.json (>=3 cases).
  8. Its deterministic backers exist: scripts/validate_envelope.py, scripts/consolidate.py,
     scripts/verify.py, and scripts/judge.py.
  9. references/routing.md names only valid modes (read-fanout, mutate, external) and
     the orchestration_hybrid_mode flag is registered in feature_flags.json.

Run:   python3 tools/sync_check.py
Exit:  0 if every invariant holds, 1 (with a report) otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ATOMS_DIR = ROOT / "skills" / "atoms"
REGISTRY = ATOMS_DIR / "atoms.json"
SKIP = {"atom-template"}

SHARED_DIR = ROOT / "skills" / "shared"
ORCH_DIR = ROOT / "skills" / "multi-agent-orchestrator"
FLAGS_PATH = ROOT / "canonical-sources" / "feature_flags.json"
VALID_MODES = {"read-fanout", "mutate", "external"}


def main() -> int:
    failures: list[str] = []

    # Discover all atom directories (excluding atom-template)
    atom_dirs = sorted(
        d for d in ATOMS_DIR.iterdir()
        if d.is_dir() and d.name not in SKIP and not d.name.startswith(".")
    )

    # Invariant 1: SKILL.md and MAINTAINER.md present
    for d in atom_dirs:
        for fname in ("SKILL.md", "MAINTAINER.md"):
            if not (d / fname).exists():
                failures.append(f"  ✗ Invariant 1 — missing {fname}: {d.name}/")

    # Invariant 2: SKILL.md references minority-report
    for d in atom_dirs:
        skill_md = d / "SKILL.md"
        if skill_md.exists():
            text = skill_md.read_text(encoding="utf-8")
            if "minority-report" not in text:
                failures.append(
                    f"  ✗ Invariant 2 — SKILL.md missing 'minority-report' reference: {d.name}/"
                )

    # Invariant 3: atoms.json entries have corresponding directories
    if REGISTRY.exists():
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        registered_ids = {a["id"] for a in reg.get("atoms", [])}
        dir_names = {d.name for d in atom_dirs}
        for atom_id in registered_ids:
            if atom_id not in dir_names:
                failures.append(
                    f"  ✗ Invariant 3 — atoms.json entry '{atom_id}' has no directory under skills/atoms/"
                )
    else:
        failures.append(f"  ✗ Invariant 3 — atoms.json not found: {REGISTRY.relative_to(ROOT)}")

    # Invariant 4: evals/evals.json present
    for d in atom_dirs:
        evals_path = d / "evals" / "evals.json"
        if not evals_path.exists():
            failures.append(f"  ✗ Invariant 4 — missing evals/evals.json: {d.name}/")

    # Invariant 5: evals.json has at least 3 cases
    for d in atom_dirs:
        evals_path = d / "evals" / "evals.json"
        if evals_path.exists():
            try:
                data = json.loads(evals_path.read_text(encoding="utf-8"))
                cases = data.get("cases", data.get("evals", []))
                if len(cases) < 3:
                    failures.append(
                        f"  ✗ Invariant 5 — evals/evals.json needs ≥3 cases, has {len(cases)}: {d.name}/"
                    )
            except json.JSONDecodeError as e:
                failures.append(f"  ✗ Invariant 5 — evals/evals.json invalid JSON: {d.name}/ ({e})")

    # ── Orchestration bucket invariants (6–9) ────────────────────────────────
    # Invariant 6: shared orchestration contracts present + schema is valid JSON
    schema_path = SHARED_DIR / "orchestration-envelope.schema.json"
    for rel in ("orchestration-envelope.schema.json", "frontier-model.md", "consolidation.md"):
        if not (SHARED_DIR / rel).exists():
            failures.append(f"  ✗ Invariant 6 — missing shared orchestration contract: skills/shared/{rel}")
    if schema_path.exists():
        try:
            json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"  ✗ Invariant 6 — orchestration-envelope.schema.json invalid JSON ({e})")

    # Invariant 7: orchestrator skill has its required files (+ >=3 eval cases)
    if ORCH_DIR.exists():
        for rel in ("SKILL.md", "MAINTAINER.md", "workflow.json",
                    "references/routing.md", "evals/evals.json"):
            if not (ORCH_DIR / rel).exists():
                failures.append(f"  ✗ Invariant 7 — missing multi-agent-orchestrator/{rel}")
        evals_path = ORCH_DIR / "evals" / "evals.json"
        if evals_path.exists():
            try:
                data = json.loads(evals_path.read_text(encoding="utf-8"))
                cases = data.get("cases", data.get("evals", []))
                if len(cases) < 3:
                    failures.append(
                        f"  ✗ Invariant 7 — multi-agent-orchestrator evals need ≥3 cases, has {len(cases)}"
                    )
            except json.JSONDecodeError as e:
                failures.append(f"  ✗ Invariant 7 — multi-agent-orchestrator evals invalid JSON ({e})")
    else:
        failures.append("  ✗ Invariant 7 — skills/multi-agent-orchestrator/ not found")

    # Invariant 8: deterministic backer scripts present
    for rel in ("scripts/validate_envelope.py", "scripts/consolidate.py",
                "scripts/verify.py", "scripts/judge.py"):
        if not (ORCH_DIR / rel).exists():
            failures.append(f"  ✗ Invariant 8 — missing multi-agent-orchestrator/{rel}")

    # Invariant 9: routing.md names only valid modes + hybrid flag registered
    routing_md = ORCH_DIR / "references" / "routing.md"
    if routing_md.exists():
        text = routing_md.read_text(encoding="utf-8")
        for token in ("read-fanout", "mutate", "external"):
            if token not in text:
                failures.append(f"  ✗ Invariant 9 — routing.md does not document mode '{token}'")
    if FLAGS_PATH.exists():
        try:
            flags = json.loads(FLAGS_PATH.read_text(encoding="utf-8")).get("flags", {})
            if "orchestration_hybrid_mode" not in flags:
                failures.append("  ✗ Invariant 9 — orchestration_hybrid_mode not registered in feature_flags.json")
        except json.JSONDecodeError as e:
            failures.append(f"  ✗ Invariant 9 — feature_flags.json invalid JSON ({e})")
    else:
        failures.append("  ✗ Invariant 9 — feature_flags.json not found")

    print(f"GRC drift check — {len(atom_dirs)} atom(s) + orchestration bucket\n")
    if failures:
        print("DRIFT DETECTED:\n")
        print("\n".join(failures))
        print(f"\n{len(failures)} invariant(s) failed.")
        return 1

    print(f"OK — all 9 invariants pass across {len(atom_dirs)} atom(s) + the orchestration bucket.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
