#!/usr/bin/env python3
"""
health_audit.py — deterministic health auditor for the dbz skills, atoms, and catalog.

Goes beyond structural drift: it verifies layouts, reference integrity, eval shape,
controlled vocabularies, and contract conformance, then scores readiness and emits an
ordered repair plan (mechanical-vs-judgment) that tools/health_repair.py can act on.

This is the fast, dependency-free (stdlib only), fully deterministic layer — safe to run
in a pre-commit hook and in CI. The LLM instruction-level checker (skills/health-auditor)
is a separate, human-gated layer.

Every check returns findings shaped as:
    {severity, area, issue, action, mechanical, provenance}
severity ∈ {blocking, warning, info}; mechanical=True means safe to auto-fix.

Run:
    python3 tools/health_audit.py --scan          # skills + atoms + refs (fast; pre-commit)
    python3 tools/health_audit.py --full          # scan + data/catalog vocab checks
    python3 tools/health_audit.py --data-target FILE  # vocab-check one JSON file
    python3 tools/health_audit.py --json           # machine-readable report to stdout
Exit: 0 if no blocking findings, 1 otherwise (so it gates CI / pre-commit).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
ATOMS_DIR = ROOT / "skills" / "atoms"
SKILLS_DIR = ROOT / "skills"
REGISTRY = ATOMS_DIR / "atoms.json"
VOCAB_PATH = ROOT / "canonical-sources" / "framework_vocab.json"
LEDGER_PATH = ROOT / "canonical-sources" / "uncertainty_ledger.jsonl"
CONFIRMATIONS_PATH = ROOT / "canonical-sources" / "confirmations.jsonl"
SKIP_ATOM_DIRS = {"atom-template"}

CODE_EXTS = (".py", ".md", ".json", ".yaml", ".yml", ".txt", ".csv")
PATH_ANCHORS = ("skills/", "tools/", "cross-mapping/", "canonical-sources/",
                "overlap-data/", "docs/", "references/", "scripts/", "evals/", "tests/")
# Placeholder markers are flagged only as whole words (so prose like "human TODOs" is fine);
# git conflict markers are matched as literal directional runs.
_MARKER_RE = re.compile(r"\b(TODO|FIXME|PLACEHOLDER)\b")
_CONFLICT_MARKERS = ("<<<<<<<", ">>>>>>>")
# Bare filenames that live in known homes — resolved leniently to avoid false positives.
COMMON_DIRS = [ROOT, ROOT / "canonical-sources", ROOT / "skills" / "shared",
               ROOT / "cross-mapping" / "engine", ROOT / "docs"]

_ALL_BASENAMES: set | None = None


def _all_basenames() -> set:
    """Every filename in the repo (basename), cached — for lenient bare-filename resolution."""
    global _ALL_BASENAMES
    if _ALL_BASENAMES is None:
        _ALL_BASENAMES = set()
        for p in ROOT.rglob("*"):
            if ".git" in p.parts:
                continue
            if p.is_file():
                _ALL_BASENAMES.add(p.name)
    return _ALL_BASENAMES


def _f(severity: str, area: str, issue: str, action: str,
       mechanical: bool, provenance: str) -> Dict[str, Any]:
    return {"severity": severity, "area": area, "issue": issue,
            "action": action, "mechanical": mechanical, "provenance": provenance}


def _excluded(path: Path) -> bool:
    """Golden-set fixtures are intentionally broken test data — never scan them in a normal run."""
    parts = path.parts
    return "golden" in parts and "tests" in parts


# ── discovery ────────────────────────────────────────────────────────────────
def atom_dirs() -> List[Path]:
    if not ATOMS_DIR.exists():
        return []
    return sorted(d for d in ATOMS_DIR.iterdir()
                  if d.is_dir() and d.name not in SKIP_ATOM_DIRS and not d.name.startswith("."))


def composite_skill_dirs() -> List[Path]:
    """Skill dirs directly under skills/ (not skills/atoms, not shared) that have a SKILL.md."""
    out = []
    for d in sorted(SKILLS_DIR.iterdir()) if SKILLS_DIR.exists() else []:
        if d.is_dir() and d.name not in ("atoms", "shared") and not d.name.startswith("."):
            if (d / "SKILL.md").exists():
                out.append(d)
    return out


# ── reference-integrity helpers ──────────────────────────────────────────────
_BACKTICK = re.compile(r"`([^`\n]+)`")


def _looks_like_path(tok: str) -> bool:
    tok = tok.strip()
    if tok.startswith("{{") or tok.startswith("--"):
        return False
    if " " in tok:
        if not tok.endswith(CODE_EXTS):
            return False
        first = tok.split(" ", 1)[0]
        if first in ("python3", "python", "bash", "sh", "cd", "cat", "schema:"):
            return False
        return True
    if any(tok.startswith(a) for a in PATH_ANCHORS):
        return True
    return tok.endswith(CODE_EXTS)


def _resolve(tok: str, skill_dir: Path, md_dir: Path) -> bool:
    tok = tok.strip().split("#", 1)[0]  # drop in-page anchors
    tok = re.sub(r":\d+$", "", tok)                 # strip ':NN' line reference
    tok = re.sub(r":[A-Za-z_]\w*(\(\))?$", "", tok)  # strip ':func()' / ':symbol' suffix
    if not tok:
        return True
    if "*" in tok:  # glob — resolve the directory portion instead
        parent = tok.rsplit("/", 1)[0] if "/" in tok else ""
        return not parent or (ROOT / parent).exists() or (md_dir / parent).exists()
    if "/" in tok:  # anchored path — resolve from repo root, skill dir, or the file's own dir
        return any((b / tok).exists() for b in (ROOT, skill_dir, md_dir))
    # bare filename — resolve if it exists anywhere in the repo (lenient; avoids prose noise)
    bases = [md_dir, skill_dir, ROOT] + COMMON_DIRS
    return tok in _all_basenames() or any((b / tok).exists() for b in bases)


def check_backtick_refs(md: Path, skill_dir: Path) -> List[Dict[str, Any]]:
    findings = []
    for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        for tok in _BACKTICK.findall(line):
            t = tok.strip()
            if not _looks_like_path(t) or _resolve(t, skill_dir, md.parent):
                continue
            sev = "blocking" if "/" in t and not t.rstrip("`").endswith("/") else "warning"
            findings.append(_f(
                sev, f"ref:{skill_dir.name}",
                f"backtick path does not resolve: `{t}`",
                "fix the path or create the referenced file",
                False, f"{md.relative_to(ROOT)}:{i}"))
    return findings


def check_forbidden_tokens(md: Path) -> List[Dict[str, Any]]:
    findings = []
    for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        for tok in set(_MARKER_RE.findall(line)):
            findings.append(_f("blocking", "hygiene",
                               f"forbidden token '{tok}' present",
                               "remove the placeholder / resolve the merge marker",
                               False, f"{md.relative_to(ROOT)}:{i}"))
        for tok in _CONFLICT_MARKERS:
            if tok in line:
                findings.append(_f("blocking", "hygiene",
                                   f"forbidden token '{tok}' present",
                                   "resolve the merge conflict marker",
                                   False, f"{md.relative_to(ROOT)}:{i}"))
    return findings


# ── structural checks (absorb + extend sync_check) ──────────────────────────
def check_atoms(reg_ids: set) -> List[Dict[str, Any]]:
    findings = []
    dirs = atom_dirs()
    names = {d.name for d in dirs}
    for d in dirs:
        for fname in ("SKILL.md", "MAINTAINER.md"):
            if not (d / fname).exists():
                findings.append(_f("blocking", f"atom:{d.name}", f"missing {fname}",
                                   f"create {fname}", True, f"skills/atoms/{d.name}/"))
        skill_md = d / "SKILL.md"
        if skill_md.exists() and "minority-report" not in skill_md.read_text(encoding="utf-8"):
            findings.append(_f("blocking", f"atom:{d.name}",
                               "SKILL.md does not reference minority-report",
                               "add a minority-report reference", False,
                               f"skills/atoms/{d.name}/SKILL.md"))
        evals = d / "evals" / "evals.json"
        if not evals.exists():
            findings.append(_f("blocking", f"atom:{d.name}", "missing evals/evals.json",
                               "add evals with >=3 cases", False, f"skills/atoms/{d.name}/"))
        else:
            findings += check_evals_shape(evals, d.name)
        # reference integrity across the atom's markdown
        for md in (d / "SKILL.md", d / "MAINTAINER.md"):
            if md.exists():
                findings += check_backtick_refs(md, d)
                findings += check_forbidden_tokens(md)
    # registry <-> directory
    for aid in reg_ids:
        if aid not in names:
            findings.append(_f("blocking", "registry",
                               f"atoms.json entry '{aid}' has no directory",
                               "create the atom dir or remove the entry", False,
                               "skills/atoms/atoms.json"))
    return findings


def check_evals_shape(evals: Path, owner: str) -> List[Dict[str, Any]]:
    findings = []
    try:
        data = json.loads(evals.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [_f("blocking", f"atom:{owner}", f"evals.json invalid JSON ({e})",
                   "fix the JSON", False, str(evals.relative_to(ROOT)))]
    cases = data.get("cases", data.get("evals", []))
    if len(cases) < 3:
        findings.append(_f("blocking", f"atom:{owner}",
                           f"evals has {len(cases)} cases (need >=3)",
                           "add pass/fail/edge cases", False, str(evals.relative_to(ROOT))))
    for j, c in enumerate(cases):
        if not isinstance(c, dict) or "id" not in c or "input" not in c:
            findings.append(_f("warning", f"atom:{owner}",
                               f"eval case [{j}] missing id/input",
                               "give each case an id and input", False,
                               str(evals.relative_to(ROOT))))
        elif not any(k in c for k in ("expected_output", "expected", "expected_error")):
            findings.append(_f("warning", f"atom:{owner}",
                               f"eval case '{c.get('id', j)}' states no expected outcome",
                               "add expected_output or expected_error", False,
                               str(evals.relative_to(ROOT))))
    return findings


def registry_script_findings(reg: Dict[str, Any], base: Path, rel: str = "skills/atoms/atoms.json") -> List[Dict[str, Any]]:
    """Pure: every atom's `script` field must resolve under `base`. (Testable in isolation.)"""
    findings = []
    for a in reg.get("atoms", []):
        script = a.get("script")
        if script and not (base / script).exists():
            findings.append(_f("blocking", f"atom:{a['id']}",
                               f"atoms.json script does not resolve: {script}",
                               "fix the script path or restore the file", False, rel))
    return findings


def check_atoms_json_scripts() -> List[Dict[str, Any]]:
    if not REGISTRY.exists():
        return [_f("blocking", "registry", "atoms.json not found",
                   "create skills/atoms/atoms.json", False, "skills/atoms/atoms.json")]
    return registry_script_findings(json.loads(REGISTRY.read_text(encoding="utf-8")), ROOT)


def workflow_findings(data: Dict[str, Any], valid_targets: set, skill_name: str, rel: str) -> List[Dict[str, Any]]:
    """Pure: duplicate step ids + references to unknown atoms/skills. (Testable in isolation.)"""
    findings = []
    seen_ids = set()
    for step in data.get("steps", []):
        sid = step.get("id")
        if sid in seen_ids:
            findings.append(_f("blocking", f"skill:{skill_name}",
                               f"duplicate workflow step id '{sid}'",
                               "make step ids unique", False, rel))
        seen_ids.add(sid)
        atom = step.get("atom")
        if atom and atom not in valid_targets:
            findings.append(_f("blocking", f"skill:{skill_name}",
                               f"workflow references unknown atom/skill '{atom}'",
                               "register the atom/skill or fix the reference", False, rel))
    return findings


def check_workflows(reg_ids: set) -> List[Dict[str, Any]]:
    findings = []
    for d in composite_skill_dirs():
        wf = d / "workflow.json"
        if not wf.exists():
            continue
        try:
            data = json.loads(wf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            findings.append(_f("blocking", f"skill:{d.name}", f"workflow.json invalid JSON ({e})",
                               "fix the JSON", False, str(wf.relative_to(ROOT))))
            continue
        # A workflow step may target a registered atom OR another installed skill
        # (composite skills — possibly nested — are valid step targets).
        skill_names = {p.name for p in SKILLS_DIR.iterdir()
                       if p.is_dir() and p.name not in ("shared",) and not p.name.startswith(".")}
        valid_targets = reg_ids | skill_names | {p.name for p in atom_dirs()}
        findings += workflow_findings(data, valid_targets, d.name, str(wf.relative_to(ROOT)))
        # reference integrity + hygiene for the composite skill's markdown
        for md in d.rglob("*.md"):
            if _excluded(md):
                continue
            findings += check_backtick_refs(md, d)
            findings += check_forbidden_tokens(md)
    return findings


# ── data / controlled-vocabulary checks ─────────────────────────────────────
def check_vocab_file(target: Path) -> List[Dict[str, Any]]:
    """Validate framework names / relationship types / CCI IDs in a JSON file against the allow-lists."""
    findings = []
    if not VOCAB_PATH.exists():
        return [_f("blocking", "data", "framework_vocab.json missing",
                   "restore the controlled vocabulary", False,
                   "canonical-sources/framework_vocab.json")]
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    allowed_fw = set(vocab["framework_names"]["allowed"])
    allowed_rt = set(vocab["relationship_types"]["allowed"])
    cci_re = re.compile(vocab["cci_pattern"])
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [_f("blocking", "data", f"{target.name} invalid JSON ({e})",
                   "fix the JSON", False, str(target))]

    def walk(node: Any, path: str):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("framework", "target_framework", "source_framework") and isinstance(v, str) and v:
                    if v not in allowed_fw:
                        findings.append(_f("blocking", "data",
                                           f"framework name not in controlled vocab: '{v}'",
                                           "use the canonical name from framework_vocab.json",
                                           False, f"{target.name}:{path}.{k}"))
                if k == "relationship_type" and isinstance(v, str) and v not in allowed_rt:
                    findings.append(_f("blocking", "data",
                                       f"relationship_type not allowed: '{v}'",
                                       "use a valid relationship_type", False,
                                       f"{target.name}:{path}.{k}"))
                if k in ("cci", "cci_id") and isinstance(v, str) and not cci_re.match(v):
                    findings.append(_f("blocking", "data",
                                       f"malformed CCI id: '{v}'",
                                       "use CCI-NNNNNN format", False,
                                       f"{target.name}:{path}.{k}"))
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(data, "$")
    return findings


# ── scoring ──────────────────────────────────────────────────────────────────
_PENALTY = {"blocking": 10, "warning": 4, "info": 1}


def check_uncertainty_ledger(ledger_path: Path | None = None,
                             confirmations_path: Path | None = None) -> List[Dict[str, Any]]:
    """
    Audit the durable uncertainty ledger + confirmations so the record the engine
    relies on cannot silently rot: referential integrity, citation resolvability,
    schema completeness, and staleness.  The ledger is a build artifact — its absence
    is not a defect (only present after build_db runs).
    """
    ledger_path = ledger_path or LEDGER_PATH
    confirmations_path = confirmations_path or CONFIRMATIONS_PATH
    findings: List[Dict[str, Any]] = []
    if not ledger_path.exists():
        return findings
    ledger_ids: set = set()
    for i, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            findings.append(_f("blocking", "ledger", f"uncertainty_ledger line {i} is not valid JSON",
                               "fix the malformed line", False, f"uncertainty_ledger.jsonl:{i}"))
            continue
        uid = e.get("uncertainty_id")
        if not uid:
            findings.append(_f("warning", "ledger", f"ledger line {i} has no uncertainty_id",
                               "every entry needs a stable uncertainty_id", False, f"uncertainty_ledger.jsonl:{i}"))
        else:
            ledger_ids.add(uid)
        # citation resolvability — no fabricated sources/figures survive
        cit = (e.get("citation") or {}).get("file", "")
        if not cit:
            findings.append(_f("warning", "ledger", f"ledger entry {uid or i} has no citation",
                               "add a resolvable source citation", False, f"uncertainty_ledger.jsonl:{i}"))
        elif not (ROOT / cit).exists():
            findings.append(_f("blocking", "ledger", f"ledger citation does not resolve: {cit}",
                               "point the citation at a real committed source (no fabricated sources)",
                               False, f"uncertainty_ledger.jsonl:{i}"))
        # schema completeness — a resolved conflict must name its winner + why
        if e.get("status") == "confirmed" and e.get("kind") in ("conflict", "overlap_pair"):
            if not e.get("winning_citation") or not e.get("why_it_won"):
                findings.append(_f("warning", "ledger", f"confirmed {uid} missing winning_citation/why_it_won",
                                   "record which source won and why on confirmation", False,
                                   f"uncertainty_ledger.jsonl:{i}"))
        # staleness — surface open high-materiality items for review
        if e.get("status") == "open" and e.get("materiality") == "high":
            findings.append(_f("info", "ledger", f"open high-materiality uncertainty {uid}",
                               "review and confirm/refute via confirmations.jsonl", False,
                               f"uncertainty_ledger.jsonl:{i}"))
    # referential integrity — every confirmation points to a real ledger entry
    if confirmations_path.exists():
        for i, line in enumerate(confirmations_path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                continue
            cuid = c.get("uncertainty_id")
            if cuid and cuid not in ledger_ids:
                findings.append(_f("blocking", "ledger",
                                   f"confirmation references unknown uncertainty_id {cuid}",
                                   "confirmations must point to a real ledger entry", False,
                                   f"confirmations.jsonl:{i}"))
    return findings


def score(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    val = 100 - sum(_PENALTY.get(f["severity"], 0) for f in findings)
    val = max(0, val)
    band = ("strong" if val >= 90 else "usable_with_warnings" if val >= 70
            else "partial" if val >= 40 else "not_ready")
    blocking = sum(1 for f in findings if f["severity"] == "blocking")
    gate = "proceed" if blocking == 0 else "block_until_resolved"
    return {"readiness_score": val, "readiness_band": band,
            "blocking": blocking,
            "warnings": sum(1 for f in findings if f["severity"] == "warning"),
            "info": sum(1 for f in findings if f["severity"] == "info"),
            "release_gate_recommendation": gate}


def run_audit(full: bool = False, data_target: Path | None = None) -> Dict[str, Any]:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {"atoms": []}
    reg_ids = {a["id"] for a in reg.get("atoms", [])}
    findings: List[Dict[str, Any]] = []
    findings += check_atoms(reg_ids)
    findings += check_atoms_json_scripts()
    findings += check_workflows(reg_ids)
    findings += check_uncertainty_ledger()
    if data_target is not None:
        findings += check_vocab_file(data_target)
    elif full:
        # In --full mode with no explicit target, vocab-check the small canonical data files
        # that use controlled names (kept conservative to avoid false positives).
        for name in ("framework_changelog.json",):
            p = ROOT / "canonical-sources" / name
            if p.exists():
                findings += check_vocab_file(p)
    # deterministic ordering: severity, then provenance
    order = {"blocking": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["provenance"], f["issue"]))
    report = {"tool": "health-audit", "scope": "full" if full else "scan"}
    report.update(score(findings))
    report["findings"] = findings
    report["repair_plan"] = [f for f in findings]  # already ordered; mechanical flag per finding
    report["human_review_required"] = True
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic health auditor for dbz skills/atoms/catalog")
    ap.add_argument("--scan", action="store_true", help="skills + atoms + refs (fast)")
    ap.add_argument("--full", action="store_true", help="scan + data/catalog vocab checks")
    ap.add_argument("--data-target", metavar="FILE", help="vocab-check one JSON file")
    ap.add_argument("--json", action="store_true", help="machine-readable report to stdout")
    a = ap.parse_args(argv)

    target = Path(a.data_target).resolve() if a.data_target else None
    report = run_audit(full=a.full or target is not None, data_target=target)

    if a.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(f"health-audit [{report['scope']}] — score {report['readiness_score']}/100 "
              f"({report['readiness_band']}) — {report['blocking']} blocking, "
              f"{report['warnings']} warning, {report['info']} info\n")
        if report["findings"]:
            for f in report["findings"]:
                mech = "auto" if f["mechanical"] else "human"
                print(f"  [{f['severity']:8}] {f['area']:20} {f['issue']}")
                print(f"             ↳ {f['action']}  ({mech}; {f['provenance']})")
        else:
            print("  no findings — clean.")
        print(f"\n  gate: {report['release_gate_recommendation']}")
    return 0 if report["blocking"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
