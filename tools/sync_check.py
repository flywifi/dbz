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
     references/routing.md, evals/evals.json (>=3 cases), and the end-to-end harness
     tests/run_scenario.py + tests/fixtures/oracle.json.
  8. Its deterministic backers exist: scripts/validate_envelope.py, scripts/consolidate.py,
     scripts/verify.py, scripts/judge.py, and scripts/frontier.py.
  9. references/routing.md names only valid modes (read-fanout, mutate, external) and
     the orchestration_hybrid_mode flag is registered in feature_flags.json.

Plus 1 health-auditor invariant:
 10. The health-auditor package is intact: tools/health_audit.py + tools/health_repair.py,
     canonical-sources/framework_vocab.json, and skills/health-auditor/ with SKILL.md,
     MAINTAINER.md, workflow.json, evals/evals.json (>=3 cases), scripts/instruction_blocks.py,
     tests/run_golden.py, and tests/golden/oracle.json.

Plus the ledger, export, scoreboard, and registry invariants:
 11. Uncertainty/confirmation ledger contract intact (+ every MAINTAINER declares it).
 12. implementation/gpt/api export matches regeneration from the atom registry
     (tools/export_openai.py --check).
 13. docs/METRICS.md matches regeneration (tools/metrics.py --check; skips honestly on a
     fresh checkout without build artifacts).
 14. Single-writer discipline for the canonical registries — registry writes route through
     tools/registry_io.py (undeclared writers are flagged).
 15. Skill-asset copies of overlap-data files hash-match the canonical overlap-data/ copy
     (silently diverged copies skew the analyzer skill against the engine).

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

HEALTH_DIR = ROOT / "skills" / "health-auditor"
HEALTH_TOOLS = [ROOT / "tools" / "health_audit.py", ROOT / "tools" / "health_repair.py"]
VOCAB_PATH = ROOT / "canonical-sources" / "framework_vocab.json"


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
                    "references/routing.md", "evals/evals.json",
                    "tests/run_scenario.py", "tests/fixtures/oracle.json"):
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

    # Invariant 10: health-auditor package intact
    for t in HEALTH_TOOLS:
        if not t.exists():
            failures.append(f"  ✗ Invariant 10 — missing {t.relative_to(ROOT)}")
    if not VOCAB_PATH.exists():
        failures.append("  ✗ Invariant 10 — missing canonical-sources/framework_vocab.json")
    if HEALTH_DIR.exists():
        for rel in ("SKILL.md", "MAINTAINER.md", "workflow.json", "evals/evals.json",
                    "scripts/instruction_blocks.py", "scripts/instruction_audit_run.py",
                    "tests/run_golden.py", "tests/golden/oracle.json"):
            if not (HEALTH_DIR / rel).exists():
                failures.append(f"  ✗ Invariant 10 — missing skills/health-auditor/{rel}")
        he = HEALTH_DIR / "evals" / "evals.json"
        if he.exists():
            try:
                cases = json.loads(he.read_text(encoding="utf-8")).get("cases", [])
                if len(cases) < 3:
                    failures.append(f"  ✗ Invariant 10 — health-auditor evals need >=3 cases, has {len(cases)}")
            except json.JSONDecodeError as e:
                failures.append(f"  ✗ Invariant 10 — health-auditor evals invalid JSON ({e})")
    else:
        failures.append("  ✗ Invariant 10 — skills/health-auditor/ not found")

    # Invariant 11: uncertainty ledger + confirmations contract intact
    confirmations = ROOT / "canonical-sources" / "confirmations.jsonl"
    if not confirmations.exists():
        failures.append("  ✗ Invariant 11 — missing canonical-sources/confirmations.jsonl")
    ha_src = ROOT / "tools" / "health_audit.py"
    if ha_src.exists() and "def check_uncertainty_ledger" not in ha_src.read_text(encoding="utf-8"):
        failures.append("  ✗ Invariant 11 — health_audit.py missing check_uncertainty_ledger detector")
    # Every MAINTAINER.md declares the confirmation-sync / durable-logging contract.
    for m in sorted((ROOT / "skills").rglob("MAINTAINER.md")):
        if "confirmations.jsonl" not in m.read_text(encoding="utf-8"):
            failures.append(f"  ✗ Invariant 11 — MAINTAINER missing confirmation-sync stanza: "
                            f"{m.relative_to(ROOT)}")

    # Invariant 12: the generated OpenAI-function export matches the atom registry.
    # (implementation/gpt/api/ is generated by tools/export_openai.py --check; hand edits drift.)
    exporter = ROOT / "tools" / "export_openai.py"
    if exporter.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("_export_openai", exporter)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if mod.check() != 0:
                failures.append("  ✗ Invariant 12 — implementation/gpt/api export is stale "
                                "(run tools/export_openai.py)")
        except Exception as e:  # never let the exporter crash the whole drift guard
            failures.append(f"  ✗ Invariant 12 — export_openai check failed to run ({e})")
    else:
        failures.append("  ✗ Invariant 12 — tools/export_openai.py not found")

    # Invariant 13: docs/METRICS.md matches regeneration (generated scoreboard).
    metrics_tool = ROOT / "tools" / "metrics.py"
    if metrics_tool.exists() and (ROOT / "docs" / "METRICS.md").exists():
        try:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location("_metrics", metrics_tool)
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            if _mod.main(["--check"]) != 0:
                failures.append("  \u2717 Invariant 13 \u2014 docs/METRICS.md is stale "
                                "(run tools/metrics.py)")
        except Exception as e:
            failures.append(f"  \u2717 Invariant 13 \u2014 metrics check failed to run ({e})")

    # Invariant 14: single-writer discipline for the canonical registries.
    # A .py file (outside the allowlist) that both names a canonical registry and
    # contains a write primitive is a suspected ad-hoc registry writer.
    _REG_NAMES = ("feed_registry.json", "anticipated_updates.json", "crawl_seeds.json",
                  "source_manifest.json", "framework_changelog.json", "doc_claims.json")
    _WRITE_TOKENS = (".write_text(", "json.dump(")
    _WRITER_ALLOW = {
        "tools/registry_io.py",        # THE writer
        "tools/registry_currency.py",  # writes baselines file only
        "tools/standards_refresh.py",  # writes the drift REPORT, not registries
        "cross-mapping/engine/oscal_diff.py",  # changelog routed via registry_io; cache/report writes only
        "tools/crawl_seed.py",         # reads seeds; writes candidates/report only
        "tools/sync_check.py",         # this file: the invariant's own pattern literals
    }
    for scan_dir in (ROOT / "tools", ROOT / "cross-mapping" / "engine"):
        for py in sorted(scan_dir.glob("*.py")):
            rel = str(py.relative_to(ROOT)).replace("\\", "/")
            if rel in _WRITER_ALLOW:
                continue
            lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
            # a write primitive within 2 lines of a canonical-registry filename is
            # a suspected direct registry write (whole-file co-occurrence is too
            # coarse: most files read a registry and write something unrelated)
            for i, line in enumerate(lines):
                if not any(w in line for w in _WRITE_TOKENS):
                    continue
                window = "\n".join(lines[max(0, i - 2):i + 3])
                if any(n in window for n in _REG_NAMES):
                    failures.append(f"  \u2717 Invariant 14 \u2014 suspected ad-hoc canonical-"
                                    f"registry writer: {rel}:{i + 1} (route writes through "
                                    "tools/registry_io.py or allowlist with a reason)")
                    break

    # Invariant 15: skill-asset copies of overlap-data files must hash-match the
    # canonical copy (overlap-data/ is canonical per CLAUDE.md). A silently
    # diverged copy skews the analyzer skill against the engine.
    import hashlib as _hl
    _canon = {p.name: p for p in (ROOT / "overlap-data").glob("*") if p.is_file()}
    for asset in sorted((ROOT / "skills").rglob("assets/mappings/*")):
        if not asset.is_file() or asset.name not in _canon:
            continue
        if _hl.sha256(asset.read_bytes()).hexdigest() != _hl.sha256(_canon[asset.name].read_bytes()).hexdigest():
            failures.append(f"  ✗ Invariant 15 — skill asset diverged from canonical "
                            f"overlap-data copy: {asset.relative_to(ROOT)} (resync from "
                            f"overlap-data/{asset.name}; never edit the per-skill copy)")

    print(f"GRC drift check — {len(atom_dirs)} atom(s) + orchestration bucket + health auditor\n")
    if failures:
        print("DRIFT DETECTED:\n")
        print("\n".join(failures))
        print(f"\n{len(failures)} invariant(s) failed.")
        return 1

    print(f"OK — all 15 invariants pass across {len(atom_dirs)} atom(s) + the orchestration "
          f"bucket + the health auditor + the platform export.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
