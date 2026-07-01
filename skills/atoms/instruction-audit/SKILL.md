# instruction-audit

Detect contradictions and drift *within and across* a skill's instruction files — the class
of mistake no type checker catches, where two rules quietly disagree and the executing model
resolves the conflict silently. Read-only; never edits instructions.

## Scope

Given a skill directory, decompose its `SKILL.md` + `MAINTAINER.md` into classified blocks
(scope, constraint, procedure, do_not_use, io_contract, reference) using the deterministic
backer `skills/health-auditor/scripts/instruction_blocks.py`, then check the enumerated
high-risk block pairs against five interference rules — **direct contradiction, goal
conflict, constraint violation, scope mismatch, precedence ambiguity** — plus dbz cross-file
rules: SKILL.md's declared input/output vs the `atoms.json` schema; "Do NOT use for" vs
Scope; SKILL.md's claimed behavior vs the backing script's actual output keys.

Judgment is done by an **adversarial-consensus** pass, not a single read: fan out read-only
agents over the pairs (mode `read-fanout`), then run `finding-verify` skeptics on each flagged
contradiction and keep only the convergent (confirmed) ones. This is the multi-pass consensus
that lifts catch-rate and cuts false positives versus a single model pass. Reuses the
orchestration bucket verbatim (envelope schema, consolidate, verify, judge).

## Input Schema

```json
{
  "skill_dir": "string — path to the skill/atom directory to audit",
  "num_skeptics": "integer? — independent verifiers per flagged contradiction (default 3)"
}
```

## Output Schema

```json
{
  "skill_dir": "string",
  "contradictions": "array — [{rule, severity, a_section, b_section, summary, provenance}] confirmed only",
  "block_histogram": "object — class -> count from decomposition",
  "pairs_checked": "integer",
  "minority_report": "object or null — disagreements the skeptics could not resolve",
  "human_review_required": "boolean — always true"
}
```

## Do NOT use for

- Auto-editing or rewriting instructions — this atom reports; a human fixes.
- Structural/reference checks (use `tools/health_audit.py`) — this atom is semantic only.
- Judging correctness of the skill's *domain* claims (that is `quality-review`'s job).
- Single-pass judgment — a contradiction must survive adversarial verification before it is
  reported, to keep false positives low.

## References

- `skills/health-auditor/scripts/instruction_blocks.py` — deterministic block decomposition + pair enumeration
- `skills/multi-agent-orchestrator/scripts/verify.py` — adversarial-consensus tally
- `skills/shared/orchestration-envelope.schema.json` — the return contract agents use
- `skills/shared/minority-report.md` — unresolved disagreements are preserved, never fabricated
