# MAINTAINER — attack-mapper

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for
`attack-mapper` so a future maintainer keeps the intended scope.

## Non-negotiable invariants
- Technique IDs must follow ATT&CK format: 'T' + digits (+ optional '.' + sub-technique digits).
- Never fabricate NIST control mappings — all from attack_techniques table only.
- Tactics must be returned as a JSON array, never a semicolon-delimited string.
  (Bug fix: attack_stix_loader.py originally wrote tactics as strings; now requires list.)
- `mapping_source` field must always be populated.
- References `skills/shared/minority-report.md` policy.

## Known failure modes
- **Tactic as string**: if the DB was built with the old loader bug (tactics as semicolon string),
  the atom must split and normalize to an array before returning.
- **Fabricated controls**: returning NIST controls not in the mapping source. Must return
  empty `nist_controls: []` if the technique has no mapped controls.

## Regression cases to preserve
1. T1078 (Valid Accounts) → nist_controls includes 'AC-2', 'IA-2'; tactics is an array (pass-01)
2. Invalid technique format → error (fail-01)
3. Sub-technique T1078.001 → returns sub-technique data if present, else parent (edge-01)

## Approval-gated changes
- Changing the NIST mapping source (e.g., updating from v13 to v16 mapping).
- Adding reverse lookup (control → techniques) — requires output schema change.

## Minority-report policy
When NIST XLSX and another source disagree on control mappings for the same technique,
NIST XLSX is primary. Emit `minority_report.conflicts` if the divergence is material (>2 controls).
See `skills/shared/minority-report.md`.

## Update checklist
- [ ] SKILL.md "Do NOT use for…" clause intact
- [ ] `python3 tools/sync_check.py` passes
- [ ] evals/evals.json has ≥3 cases
- [ ] Tactics confirmed to be array (not string) in output
## Confirmation-sync & durable logging
Uncertainties this skill emits (conflicts, partials, inferred edges, ODP clashes, agent
dissent) carry a deterministic `uncertainty_id`, log the competing citations plus
`why_conflict` / `winning_citation` / `why_it_won`, and are recorded in
`canonical-sources/uncertainty_ledger.jsonl`. Human confirmations live in
`canonical-sources/confirmations.jsonl`; on confirm, `status`, `needs_confirmation`,
`confidence`, and any partial->full reclassification re-derive at build. Never resolve an
uncertainty in place — only via the confirmations ledger. See `skills/shared/minority-report.md`.
