# Phase-55 closing adversarial audit — 2026-11-23

**Scope.** Canonical data (FedRAMP consolidated rules and schema, the SP 800-53 OSCAL catalog,
eleven FedRAMP reporting schemas); `source_manifest.json` (pins, dates, six `upstream_check`
methods); `feed_registry.json` (`fedramp-20x`, `fedramp-schemas`, `nist-800-53`);
`framework_changelog.json` (two confirmed entries). Written to satisfy the regulatory-phase closing
gate (`protocol-layer/quality-gates.md`).

**Origin.** The user asked for a full-format plan for the changes phase 54 reported and approved
it. The plan followed `protocol-layer/planning-standard.md`: every stage ran first in a throwaway
clone with a real commit, a rebuild, the gate battery and the CI rehearsal.

## Pass 1 — source integrity
- **Every installed file is the issuer's bytes,** fetched once through fetchkit on 2026-11-23. The
  rules file states its own version (`2026.11.02.01`, `last_updated` 2026-11-02); the catalog its
  own metadata (release 5.2.0, `last-modified` 2026-10-22, OSCAL 1.2.3).
- **Three reported changes were not changes** (the CSF 2.0 export, two community CCI files): equal
  as sets of records, different order. Nothing was ingested for them.
- **The catalog differences were read control by control:** SA-15(13), SA-24, SI-2(7), plus
  metadata. The rest of the byte difference is formatting.

## Pass 2 — claim support
- **Every restated number comes from the two builds** (the pre-ingest database and the new one);
  the docs stage computes them.
- **The implementation reproduced the rehearsal:** the same digests, counts and percentages.
- **The re-pinned gate is below both measurements** (98.6% before, 99.0% after; pin 95%).

## Pass 3 — chain / mutation integrity
- **Commits:** `a8eb636` anchor, `9737a21` fingerprint, `cb0a7e2` FedRAMP rules, `bd2c6c8` catalog,
  `f68257a` schemas, then this close-out. Each rehearsed package-free (22 steps) at commit time.
- **Digests:** rules, 3 tables (`fedramp_ksi`, `fedramp_ksi_controls`, `fedramp_rules`); catalog,
  `assessment_objectives`, `overlap_matrix`, `controls` (generator timestamp) and two registry
  tables; schemas, the registry table only.
- **Registries** written only through `tools/registry_io.py`; all round-trip identical.

## Pass 4 — adversary, run
1. **"All 18 reported rows are changes."** Multiset comparison: three are reorderings. **Overturned.**
2. **"Ignoring order hides real changes."** Selftest: a reordered set with one altered record
   reads `changed`; the strict method still reads `changed` on a pure reordering. **Holds.**
3. **"The FedRAMP refresh touches only FedRAMP tables."** 3 digests, all FedRAMP. **Holds.**
4. **"Lower the carry-over pin."** The Moderate share fell because FedRAMP widened the scope; a 70%
   pin would assert nothing. The share in FedRAMP's Rev 5 baselines is stable. **Overturned.** The
   shipped pin was shown red on the new rules first (218/302).
5. **"The catalog swap is formatting only."** Three controls carry errata. **Overturned.**
6. **"The errata change mapping verdicts."** All four counts equal. **Does not hold.**

## Residual risk
- **The documentation corpus is still the July copy;** its drift row stays.
- **33 KSI-cited controls are in no NIST baseline;** 30 of them are in FedRAMP's Rev 5 projection.
  Recorded as stated by the issuer, not interpreted.
- **A source past the run budget is unchecked that week** and says so.
- **NIST may republish the catalog again without a release number;** the Monday check reports it.
