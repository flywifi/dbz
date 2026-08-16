# Audit evidence artifacts

Machine-readable evidence behind the audits in `docs/audits/`. Committed so the audits can be
**re-run by someone who does not trust the author** — the point of a seeded sample is lost if
the seed and keys live only in the session that drew them.

## `phase-36-frame.json` — the phase-36 sampling frame

The reproducible frame behind `phase-36-master-accuracy-audit.md`.

- **seed** `20360810`; the sample is the head of each stratum ranked by
  `md5(seed|fw_a|native_a|fw_b|native_b)`, so it is re-derivable in any language.
- **`strata_sql`** — the exact SQL defining each of the 9 strata. The partition was asserted
  exhaustive and disjoint when drawn (0 unassigned rows).
- **`sample`** — 220 keys: `spoke_hub_transitive` 60 · `spoke_hub_hitrust` 50 ·
  `cross_consensus` 40 · `cross_production` 25 · `spoke_bundled` 20 · `spoke_authoritative` 15 ·
  `cross_nist_stated` 10. Keys are `fw_a|native_a|fw_b|native_b`.
- **Verified 2026-08-16: 220/220 keys still resolve** against the current build.

**Why the keys are committed rather than re-derived.** `master_mappings` was 97,906 rows at the
audit and is 97,668 today (phase 37 rewrote the 800-171 native ids, which are part of the key).
Re-deriving from the seed now would produce a *different* sample and silently break the link to
the published report. These keys are the only way to re-label *that* sample.

## `phase-36-adjudication-worksheet.json` — the 40-edge worksheet

Per-edge context as it was presented to the labeler: stratum, key, framework, native id, the
800-53 anchor with its title and text, tier, provenance, confidence.

**The `verdict` field is null on all 40 entries, and it ships that way deliberately.** The
phase-36 audit adjudicated 65 edges, but the verdicts were only ever written as prose in
`phase-36-master-accuracy-audit.md` — they were never persisted machine-readably, and phase 43
did not back-fill them from the report. A null worksheet is also the better starting point for
an independent re-label: it does not anchor a second labeler to the first one's calls.

## Re-labelling procedure

1. Load the keys from `phase-36-frame.json → sample[stratum].keys`.
2. For each edge, pull both sides' control text (the 800-53 side from `controls`; the framework
   side from its published standard) and judge whether a competent auditor would accept the
   pair as shared work.
3. Record `SUPPORTED` / `SCOPE_MISMATCH` / `UNSUPPORTED` / `UNDECIDABLE` with the evidence
   quoted. `UNDECIDABLE` is a legitimate verdict and must not be pushed into a decision.
4. Compare against the report's published rates (hub stratum: 63.2% unsupported, n=38, 95% CI
   [47.9%, 78.5%]; authoritative control stratum: 25.0% unsupported, n=12).

Judge from the control text with tier and confidence hidden where practical — the phase-36
report records that its own blind protocol was only partial, and that is the bias channel an
independent re-label exists to close.
