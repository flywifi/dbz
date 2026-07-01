# MAINTAINER — claim-and-output-validator

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`claim-and-output-validator` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Fails closed on missing required keys — never passes a structurally incomplete output.
- Blocks unsupported superiority claims ("best-in-class"), guarantees, and blurred audit/automation language.
- Deterministic local checks run before any external eval path.
- Validation result must include a `verdict` (pass / fail / needs_review) and a list of `findings`.
- `human_review_required: true` in every output that triggers `needs_review` or `fail`.
- Never passes output that fabricates a compliance certification, audit opinion, or framework conclusion.

## Known failure modes
- **False pass on weak evidence**: approving a claim like "our system is SOC 2 compliant" without flagging the need for an actual audit opinion. Claims about compliance status must be flagged for human review unless the source document is an actual audit report.
- **Scope creep**: being asked to generate or rewrite content. This skill validates only — redirect generation requests to the appropriate skill.
- **Blurred automation/audit boundary**: approving language that implies an AI tool can substitute for an auditor opinion. Always flag and block.
- **Missing-field silent pass**: returning a `pass` verdict when a required output key is absent but populated with a falsy default. Fail closed.

## Fragile fallbacks that must not become defaults
- External eval credentials (LLM-as-judge endpoints) may not be available — always implement deterministic rule checks as the first validation layer, not the fallback.
- `verdict: "needs_review"` is not a soft pass — it means human action is required before the output is used.

## Regression cases to preserve
1. Returns `fail` when a required output key is missing, null, or empty string.
2. Blocks "our tool achieves SOC 2 compliance" framing (automation ≠ certification).
3. Returns `human_review_required: true` for all `fail` and `needs_review` verdicts.
4. Returns a `findings[]` list even on `pass` verdicts (may be empty, but field must exist).
5. Never rewrites or corrects the content being validated — only flags.

## Approval-gated changes
- Adding new validation rules or blocking patterns.
- Changing the verdict vocabulary (pass/fail/needs_review).
- Adding external eval paths (LLM-as-judge integrations).
- Modifying required-key definitions for any output schema this skill validates.

## Minority-report policy
When two validation rules conflict on the same claim (e.g., one rule flags it, another would pass it),
emit `minority_report.conflicts` with both rules and their rationale rather than silently picking one.
See canonical policy: `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] Confirm blocking patterns list is current (especially audit/automation blurring patterns).
- [ ] Verify deterministic checks still run before any external eval path.
- [ ] Test fail-closed behavior: pass an output with one required key set to `null`.
- [ ] Confirm `human_review_required: true` present in all non-pass output paths.
- [ ] Confirm `findings[]` field present in all output paths (including clean passes).
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
