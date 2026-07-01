# Minority Report Policy — GRC Cross-Mapping Skills (canonical)

The GRC engine must **preserve disagreement in a structured way** whenever ambiguity materially
affects which control applies, what relationship type is warranted, or what version of a framework
governs. A minority report is **not optional** when disagreement changes which mapping is reported,
what coverage percentage is displayed, or what action a compliance team would take as a result.
It must appear in the skill's output JSON — never buried in prose caveats.

## Required buckets (output record)

### `minority_report.decision_log` — the chosen interpretation and why it won
`chosen_interpretation` · `why_it_won` · `winning_source` · `winning_version` ·
`supporting_claim_ids` · `confidence` (high / medium / low / uncertain).

### `minority_report.conflicts` — direct disagreements between meaningful sources
`source_a` · `source_b` · `conflict_summary` · `materiality` (high / medium / low) ·
`affected_control_ids`.

### `minority_report.failed_to_merge` — plausible interpretations that must NOT be blended
`interpretation_a` · `interpretation_b` · `why_not_mergeable` · `affected_control_ids`.
Canonical examples: OLIR STRM says "Superset" while HITRUST hub-bridge implies "Equal"; or
NIST Rev 4 CCI text and Rev 5 control intent diverge on scope (Confirmed-Subject vs.
Implied-Bridge provenance tier).

### `minority_report.residual_uncertainty` — open ambiguity that does not block the answer
`statement` · `what_would_resolve_it` · `impact_if_wrong`.

## Trigger conditions (emit a minority report when ANY is true)
- Two authoritative crosswalk sources assign different relationship types to the same
  control pair (e.g., NIST OLIR says "Subset" while ER crosswalk says "mapped_to");
- A framework version change materially alters the scope or wording of a control and the
  canonical-sources pin has not been updated to reflect it;
- A CCI's provenance tier is Implied-Bridge or Implied-Heuristic — meaning the connection
  to an external publication is not confirmed in DISA source text;
- The `feed_registry.json` version pin and the source file version differ;
- Overlap or gap percentages change by more than 5 percentage points depending on which
  relationship types are counted as "covered";
- A control's `fedramp_levels` baseline conflicts between 800-53B and FedRAMP OSCAL baselines;
- The same ER maps to controls in two frameworks that NIST OLIR says are not equivalent.

## GRC-specific hard rules
- **Never** fabricate a control ID, crosswalk relationship, or overlap percentage.
  An invented mapping is excluded and flagged in `residual_uncertainty` — it can never
  populate `mappings[]` (Quality Gate equivalent of §37 in educator-tools).
- **Never** merge two conflicting mapping sources by averaging or blending their relationship
  types. Record both in `conflicts` and let the human or orchestrator resolve.
- **Never** promote a `transitive_via_hitrust` relationship to a direct mapping without noting
  the provenance chain in `minority_report.decision_log`.
- **Never** report CCI coverage as "Confirmed-Direct" when the provenance tier is
  "Implied-Bridge" or "Implied-Heuristic" — always surface the actual tier.
- When `human_review_required: true` is set, the minority report is the primary signal that
  tells a compliance specialist exactly *where* their review should focus.

## Provenance tiers (CCI-specific)
| Tier | Meaning | Minority report trigger? |
|---|---|---|
| Confirmed-Direct | CCI text explicitly names the publication | No — no ambiguity |
| Confirmed-Subject | CCI text explicitly references the subject matter | No — subject match is unambiguous |
| Implied-Bridge | Rev 4 CCI → r4→r5 bridge → Rev 5 control that cites the pub | **Yes** — emit `conflicts` noting the bridge |
| Implied-Heuristic | Keyword match only; no explicit DISA source language | **Yes** — emit `failed_to_merge` noting heuristic origin |
| Not-Applicable | No CCI coverage for this control/publication | No — absence is not ambiguity |

## How it is produced
Each skill script (or Claude response) that performs mapping, overlap, or gap analysis must:
1. Track every source consulted and its provenance tier.
2. When two sources conflict, do NOT silently pick one — record both in `conflicts`.
3. Populate `minority_report` before returning the result object.
4. Set `minority_report: null` only when every mapping is Confirmed-Direct/Subject, all
   sources agree, and no version drift is detected.

The `minority_report` field must appear at the top level of every output object defined in
the skill's SKILL.md output schema, alongside `human_review_required: true`.

## v2 — uncertainty ids, competing citations, agent dissent, and the confirmation cascade

Every recorded uncertainty carries a **deterministic** id so it can be referenced and resolved
across runs: `uncertainty_id = sha256(canon(salient fields))[:16]` (see
`cross-mapping/engine/uncertainty.py`). Same inputs → same id, so a confirmation made once still
matches on the next build.

### `conflicts` entry (v2) — n-way, with why + winner + competing citations
```
{
  "uncertainty_id": "…",
  "why_conflict": "version_drift | granularity_mismatch | derived_vs_stated | odp_value_divergence | provenance_tier",
  "positions": [
    { "agent_role": "…", "claim_value": "…",
      "citation": { "file": "…", "locator": "…", "url": "…?" },
      "provenance_tier": "direct_olir | cmmc171 | hitrust_hub | inferred_er | transitive" },
    …                                   // two or more positions, not just source_a/source_b
  ],
  "winning_citation": { "file": "…", "locator": "…" },
  "why_it_won": "…",                    // resolution_basis: direct>hub>ER>transitive | oracle_ground_truth | source_recency
  "materiality": "high|medium|low",
  "affected_ids": ["AC-2 a", …],
  "status": "open | confirmed | refuted",
  "needs_confirmation": true,
  "confidence": "high|medium|low|uncertain"
}
```
The legacy `source_a`/`source_b` shape stays valid; `positions[]` supersedes it when more than two
sources disagree.

### `agent_dissent` bucket — named minority technical opinions
```
{ "uncertainty_id": "…", "agent_role": "…",
  "position": "recommendation | research | suggestion",
  "claim": "…", "disagrees_with": "…",
  "citation": { "file": "…", "locator": "…" }, "provenance": "…",
  "disposition": "adopted | noted | overruled", "why": "…" }
```
When agents or sub-agents produce disagreeing recommendations, research, or suggestions, the dissent
is logged here (and in the durable ledger). A dissent — or any `positions[]` entry — with **no
resolvable citation** is itself a flaggable finding: agents must cite their sources.

### Citations rule
Full provenance lives on every finding. The minority report logs **only the competing / dissenting
citations** — that is what makes "which won and why" auditable. Winner selection is deterministic:
compare each position's `provenance_tier` by precedence (`direct/cmmc171 > hitrust_hub > inferred_er
> transitive`), with `oracle_ground_truth` trumping all.

### Confidence tier mapping
Engines store a float internally and map it to this vocabulary when emitting into a minority report:
`>=0.9 high · 0.7–0.9 medium · 0.5–0.7 low · <0.5 uncertain`.

### Confirmation cascade (the sync guarantee)
Human confirmations live in `canonical-sources/confirmations.jsonl`, one record per
`uncertainty_id` (`decision: confirmed|refuted`, `resolution_note`, `winning_citation`,
`decided_by`, `decided_ref` — no wall-clock, so the file stays deterministic). At build time
`build_db.py` applies them and **re-derives every dependent field**: `confirmed` flips
`needs_confirmation`→0, lifts `confidence`≥0.9, and sets `status='confirmed'`; `refuted` drops
`confidence`≤0.3 and sets `status='refuted'` (refuted edges are excluded from overlap footprints).
Because every dependent field keys off `uncertainty_id`, **confirming once cascades everywhere** on
the next build — an uncertainty is never resolved in place, only via the ledger.
