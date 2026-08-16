# Audit-obligation ledger

The regulatory-phase closing gate (`protocol-layer/quality-gates.md`) requires an
adversarial-audit document from any phase that changes regulatory-currency data
(`feed_registry.json`, `anticipated_updates.json`, `framework_changelog.json`, or regulatory
claims in `docs/`). **This ledger exists because the gate failed twice with no list to look
at** — phases 34 and 35 both shipped without their audits, and both misses were discovered by
later archaeology, not by inspection of any record. A phase that creates an obligation adds
its row here in the same change; an unfilled obligation is a visible **GAP** row, never a
silent absence.

Honest label: this remains procedural — no clean CI-evaluable hook exists without git-history
heuristics. The corrective is visibility, not automation.

| Phase | Regulatory writes (commits) | Audit owed? | Audit document | Status |
|---|---|---|---|---|
| 32 | CMMC absorption, HIPAA refresh, 76-record backfill (`c1f5f3b`, `1a8ca33`, `075dc74`, `670d9a2`) | YES | `phase-32-adversarial-audit.md` | satisfied |
| 33 | none (read-only audit of phase 32) | no | — (it is itself an audit) | n/a |
| 34 | three record repairs (`38b69f0`) + regulatory doc claims (`74f022a`) | YES | `phase-34-adversarial-audit.md` | **satisfied-late** (written by phase 35; the miss recorded as finding 34-B) |
| 35 | FedRAMP re-harvest (`55ffa93`), two overdue-record resolutions (`1b7b8f3`), 18 HIPAA FR verbatims (`3399a48`) | YES | `phase-35-adversarial-audit.md` | **satisfied-late** (written by phase 42, three phases after close) |
| 36 | none (read-only accuracy audit) | no | `phase-36-master-accuracy-audit.md` (it is itself an audit) | n/a |
| 37 | none of the three registries; BENCHMARK/STATE changes are accuracy claims, not regulatory-currency claims | no | — | n/a |
| 38 | none | no | — | n/a |
| 39 | none | no | — | n/a |
| 40 | none | no | — | n/a |
| 41 | none (tooling + docs) | no | — | n/a |
| 42 | five elapsed-window outcome checks in `anticipated_updates.json` (WS-2) | YES | `phase-35-adversarial-audit.md` (its scope line covers the 35+42 registry surface jointly) | satisfied |
| 43 | trigger/detection corrections in `anticipated_updates.json` (WS-5) | YES | `phase-43-adjudication.md` (its scope line covers the two adjudications and this phase's registry writes jointly) | satisfied |
| 44 | no regulatory-currency registry touched; `framework_vocab.json` labels + claims about 45 CFR Part 164's subpart structure | YES (voluntarily — the phase makes checkable claims about a regulation) | `phase-44-adjudication.md` | satisfied |

`feed_registry.json` and `framework_changelog.json` have zero touches since the gate has
existed (verified by per-file `git log`, 2026-08-15), so no hidden obligations exist beyond
this table.
