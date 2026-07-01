# health-auditor — Maintainer Notes

## Non-Negotiable Invariants

- **Deterministic layers stay deterministic and dependency-free.** `tools/health_audit.py`
  and `tools/health_repair.py` are stdlib-only and produce byte-identical `--json` output for
  the same tree, so they can gate pre-commit and CI.
- **Zero false positives on a clean repo.** A clean tree must score in the `strong` band with
  no blocking findings; the golden self-test enforces zero findings on the clean fixtures.
  Any new check must be tuned to this bar before it ships.
- **The auditor never auto-edits semantic content.** Repair applies only mechanical fixes;
  contradictions, missing evals, and vocab/schema violations are human TODOs.
- **The instruction checker uses adversarial-consensus**, not single-pass — a contradiction
  is reported only after independent skeptics confirm it.
- **The auditor is self-verified.** `tests/run_golden.py` must pass (every planted defect
  caught, clean fixtures clean, negative control silent, pinned hash matches) before release.

## Known Failure Modes

- A new detector that is too aggressive will flag real skills → run `health_audit.py --scan`
  on the whole repo and confirm it stays `strong` before committing the detector.
- The golden pinned hash changes whenever a detector's message text changes → re-emit and
  re-pin intentionally (`run_golden.py --emit`), never loosen the assertion to make it pass.
- The instruction layer needs model access → in headless CI only its deterministic backer
  (`instruction_blocks.py --self-test`) runs; the live LLM scan is a human-invoked pre-merge gate.

## Approval-Gated Changes

- `canonical-sources/framework_vocab.json` allow-lists, the golden oracle, and the pinned
  hash are contracts — changing them requires re-running the golden self-test and updating
  the pin deliberately.

## Regression Cases

See `evals/evals.json`:
- pass-01: clean repo scans `strong` with exit 0
- fail-01: a planted defect (missing script path) goes blocking with exit 1
- edge-01: the golden self-test catches every defect and stays clean on the control
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
