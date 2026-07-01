# finding-verify

Adversarially verify a high-materiality finding before it is trusted in the consolidated
result: spawn independent skeptics prompted to **refute** it, then tally their votes
deterministically. A finding survives only with a strict majority of confirming votes.

## Scope

For each key in the consolidated `pending_verification` list (conflicts, or findings
merged at low/uncertain confidence), the manager runs N independent skeptic agents — each
told to try to refute the finding and to default to "refuted" when uncertain. Their
judgments are tallied by `skills/multi-agent-orchestrator/scripts/verify.py` (arithmetic only — the agents judge, the
script computes), and `apply_verdicts` folds the outcome back: confirmed findings stay,
unverified findings stay but are flagged, refuted findings leave `findings[]` and are
recorded in `minority_report.failed_to_merge`. Never silently dropped, never fabricated
back in.

## Input Schema

```json
{
  "finding": "object — {key, value, provenance, confidence} the finding under scrutiny",
  "why_material": "string — why this finding warrants verification (conflict / low confidence / high stakes)",
  "skeptic_votes": "object — {refuting, confirming, unable} tallied from independent skeptic agents"
}
```

## Output Schema

```json
{
  "key": "string — the finding key",
  "verdict": "string — confirmed | refuted | unverified",
  "refuting_votes": "integer",
  "confirming_votes": "integer",
  "unable_votes": "integer",
  "human_review_required": true
}
```

## Verdict rules (adversarial)

- **unverified** when skeptics could not check it (a majority "unable" — e.g. unreachable
  source). Unverifiable is never treated as refuted.
- **refuted** on a refuting majority OR a tie — the burden of proof is on the finding.
- **confirmed** only on a strict confirming majority.

## Do NOT use for

- Verifying every finding — only the `pending_verification` set (verifying all is wasteful;
  the 15× token reality means skeptics are reserved for what matters)
- Deciding coverage/stop (use `wave-judge`)
- Overturning a `refuted` verdict without new evidence — re-run skeptics, do not hand-wave

## References

- `skills/multi-agent-orchestrator/scripts/verify.py` — deterministic tally + apply_verdicts
- `skills/shared/consolidation.md` — how pending_verification is computed
- `skills/shared/minority-report.md` — refuted findings are preserved, never fabricated back
