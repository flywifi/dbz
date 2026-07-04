# MAINTAINER — master-crosswalk

## Purpose
`SKILL.md` is the runtime contract; this file preserves non-negotiable behavior for the
master mapping surface so a future maintainer keeps the intended scope. The atom queries
`master_mappings` — the tier-arbitrated union of every mapping surface — never a single
source in isolation.

## Non-negotiable invariants
- **Tier arbitration is fixed**: `owner_direct(0.95) > nist_stated(0.85) >
  owner_stated(ccm_oscal 0.85 / scf_direct 0.80) > hub(0.65) > bundled(0.60) > consensus >
  production_aggregate`. The order lives in ONE place — `master_surface.TIER_ORDER`
  (dbz_query imports it). The strongest tier wins the primary row; every non-winning
  surface's claim is preserved verbatim in `corroboration` (JSON) — dissent is never
  dropped (minority-report policy). Phase 20 added `owner_stated` (owner-of-source mapping
  to a foreign target, scope-relative per the acceptance-authority model) — an
  approval-gated change, approved via the Phase 20 plan.
- **No fabrication.** Every master row traces to a committed source (`source_ref`); the
  assembly refuses provider-proprietary ids (`ER-N`/`REQ-N`) by raising, and test_spine +
  validate_spine (check 8) + health_audit each independently scan for leaks. Absent pairs
  are absent — never guessed, never interpolated.
- **SOC 1 = structured data gap** (`no_public_control_layer`), never id-level rows.
- **One canonical label per framework** via `framework_labels` (explicit aliases from
  framework_vocab.json's `framework_aliases`; unregistered surface labels self-register as
  identities at build). Version-ambiguous labels (bare "ISO/IEC 27001", hub-era "NIST CSF")
  stay deliberately distinct — merging them would fabricate a version equivalence.
- **HIPAA citation granularities are source-faithful**: section (consensus), CPRT standard
  (800-66 direct), full citation (hub) — all canonical bare form (`normalize_hipaa_citation`),
  never rewritten across granularities.
- **Aggregate-only production evidence**: `production_support` counts, public canonical ids
  only (ISO / PCI / HITRUST ER sides); SOC 1/SOC 2/HIPAA ER natives are firm-local and never
  eligible.
- Results are advisory: `human_review_required: true` on every output path;
  `needs_confirmation` stays 1 below `nist_stated`.

## Known failure modes
- **Tier inflation** — reading a `bundled`/`consensus` row as if it were owner-stated.
  The tier + provenance are on every row; keep them in any downstream rendering.
- **Label drift** — a new surface label bypassing the registry. The build self-registers
  identities and validate_spine 8c fails on multi-resolution; never hand-merge labels.
- **Granularity conflation** — treating the three HIPAA citation granularities as
  disagreement. They are complementary depths of the same rule.
- **FedRAMP as pairs** — FedRAMP r5 hub natives are baseline-annotated 800-53 ids and are
  deliberately excluded from pair rows; the audit-scope mode (baseline flags) owns that
  question.

## Fragile fallbacks that must not become defaults
- `production_aggregate` primaries exist only where NO stated/derived surface covers the
  pair — a corroboration signal promoted for visibility, never comparable to a crosswalk.
- Single-voter consensus pairs are excluded by design; do not "enrich" the master surface
  with them without a new gate.

## Regression cases to preserve
1. Pair mode SOC 2 × PCI DSS orders rows by tier rank and shows corroboration counts.
2. Control mode returns both orientations of a pair (unordered canonical key).
3. Audit-scope mode reports "n of m requirements touch the in-scope set" and marks it advisory.
4. SOC 1 in any mode returns the structured data gap, exit 0.
5. Proprietary-id leak scans return zero across all master text columns.
6. Double-build `table_digests.master_mappings` identical (deterministic assembly).

## Approval-gated changes
- Changing the tier order, any tier's confidence, or the arbitration/dedup rule.
- Adding a projection source or master pair source (new provenance) — requires a
  validate_spine check-8 extension and a measured, pinned gate before it ships.
- Including FedRAMP pair rows or single-voter consensus pairs.

## Confirmation-sync & durable logging
Master rows carry deterministic `uncertainty_id`s (kind `master_pair`). Uncertainties this
skill surfaces (tier conflicts, corroboration disagreements) follow the confirmations
ledger flow: human confirmations live in `canonical-sources/confirmations.jsonl`; on
confirm, dependent fields re-derive at the next build. Never resolve an uncertainty in
place — only via the confirmations ledger. See `skills/shared/minority-report.md`.

## Update checklist (every version bump)
- [ ] SKILL.md description still specific + scoped, with the "Do NOT use for…" clause intact.
- [ ] `python3 tools/sync_check.py` passes.
- [ ] `python3 cross-mapping/tests/test_spine.py` + `validate_spine.py` pass (check 8 green).
- [ ] evals/evals.json has at least 3 cases; a case was added for any new behavior.
- [ ] Leak scans still zero; SOC 1 data-gap contract intact.
