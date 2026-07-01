# health-auditor

Catch mistakes in the dbz skills, atoms, and catalog **before they are pushed or used** —
across layout, references, contracts, controlled vocabularies, and instruction-level
consistency. Goes beyond structural drift: it verifies that references resolve, that data
uses canonical names, and that a skill's own instructions do not contradict each other.

## Scope

Runs four layers, deterministic-first so the fast layers can gate every commit and push:

1. **Deterministic scan** — `tools/health_audit.py --scan` (fast, stdlib-only): backtick
   paths resolve; `atoms.json` `script` fields resolve; `workflow.json` atom references are
   registered atoms or installed skills; eval cases are well-shaped; no forbidden tokens.
2. **Controlled vocabulary / schema** — `tools/health_audit.py --full` +
   `--data-target FILE`: framework names, CCI ids, relationship types checked against
   `canonical-sources/framework_vocab.json`; catalog conformance via the existing
   `cross-mapping/nist-catalog/ingestion/validate_catalog.py`.
3. **Instruction-level contradiction/drift** — the `instruction-audit` atom: decompose each
   skill's `SKILL.md` + `MAINTAINER.md` into classified blocks and check high-risk pairs with
   an **adversarial-consensus** LLM pass (only convergent contradictions are reported).
   Read-only, never edits instructions. In CI this runs in two parts:
   `instruction_blocks.py --audit-all` is a deterministic, headless **structure gate** (every
   atom must keep a scope + a "Do NOT use for" block) that always runs on push/PR; the
   **semantic** contradiction pass (`instruction_audit_run.py`) is **on-demand** — triggered
   manually via the `instruction-audit` GitHub Actions workflow, or run locally. It performs
   the full adversarial-consensus judgment when `ANTHROPIC_API_KEY` is set and skips cleanly
   otherwise, so triggering it is always safe.
4. **Repair** — `tools/health_repair.py`: dry-run by default; `--apply` performs only
   mechanical fixes; contradictions and schema/vocab violations are surfaced as human TODOs.

Every layer emits a readiness score with `severity` + `mechanical`-vs-`judgment` tags, and
`human_review_required: true`. Blocking findings return exit 1 so the pre-commit hook and CI
gate can block the change.

## The auditor is itself verified

`skills/health-auditor/tests/run_golden.py` runs the real detectors over a golden set of
intentionally-broken fixtures and a clean control, validated against a hand-authored
independent oracle with a pinned hash — so the auditor must catch every planted defect and
produce zero false positives on clean input. This is the same "validate independent of the
answer" discipline used by the orchestration harness.

## Do NOT use for

- Auto-fixing contradictions or semantic content — the auditor reports; a human resolves.
- Judging the *correctness* of GRC domain claims (framework mappings) — that is the overlap
  engine's and a human reviewer's job; the auditor checks structure, references, and consistency.
- Replacing `tools/sync_check.py` — the auditor composes and extends it, it does not remove it.

## References

- `tools/health_audit.py` — deterministic scan / vocab / scoring
- `tools/health_repair.py` — mechanical-only, human-gated repair
- `skills/health-auditor/scripts/instruction_blocks.py` — deterministic block decomposition + `--audit-all` structure gate
- `skills/health-auditor/scripts/instruction_audit_run.py` — CI runner: structure always, semantic when credentialed
- `skills/atoms/instruction-audit/SKILL.md` — the adversarial-consensus instruction checker
- `skills/health-auditor/tests/run_golden.py` — the auditor's self-test
- `canonical-sources/framework_vocab.json` — controlled vocabularies
- `skills/shared/minority-report.md` — disagreements are preserved, never fabricated
