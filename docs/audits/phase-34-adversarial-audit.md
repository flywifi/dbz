# Phase 34 closing adversarial audit — remediation of the phase-33 findings

**Run 2026-08-10** against the phase-34 diff (`f50ef1e..d00954b`: `f50ef1e`, `49aedce`,
`38b69f0`, `cd1449c`, `74f022a`, `28ff354`, `d00954b`; 15 files). Required by the
regulatory-phase closing gate (`protocol-layer/quality-gates.md`) because phase 34 changed
`anticipated_updates.json` and regulatory claims in `docs/`. Pass structure and evidence rules
per `protocol-layer/regulatory-provenance.md`.

**This audit is late, and that is its first finding.** The gate says the audit closes the
phase; phase 34 shipped without one and phase 35 discovered the omission. The rule was written
in phase 32, broken by the phase whose entire subject was fixing audit findings — recorded here
rather than quietly satisfied after the fact.

**This audit also starts from a known miss.** Phase 35's opening survey showed phase 34's
headline fix (B-1) closed one instance of a defect class it did not sweep. An audit written by
the author of the work it audits is worth little if it goes looking for reassurance; this one
begins from the thing that was already proven wrong.

## Input ledger

- 3 repaired horizon records (`38b69f0`): `au-iso-15408`, `au-fedramp-class-a`, `au-eu-ai-act`.
- 1 loader validation + 1 protocol line (`cd1449c`).
- 1 alias fix + 1 pinned scenario (`49aedce`).
- 1 workflow fix + 1 rehearsal mode (`28ff354`).
- Record-keeping edits across 7 files (`74f022a`) and the 0.5.1 close-out (`d00954b`).

## Pass 1 — source integrity

Re-fetched all three URLs phase 34 wrote (2026-08-10):

| Record | Result |
|---|---|
| `au-fedramp-class-a` | HTTP 200, verbatim present — holds |
| `au-eu-ai-act` | HTTP 200, verbatim present — holds |
| `au-iso-15408` | HTTP **403** — the Common Criteria portal bot-wall, exactly the obstacle the record's `DEAD_END`/`THIN` state describes. Consistent, not a defect: the phase-34 repair replaced an *empty* URL with the attempted hop, and a wall page at that hop is what the record predicts |

Conformance walker over all 76 records: **zero violations**, and the build-time URL rule
(`cd1449c`) now makes the phase-33 C-1 defect unshippable — verified by negative test in
phase 35's own gate runs (empty and relative URLs both raise `SystemExit`).

## Pass 2 — claim support

- The three repaired records state no more than their evidence; the `au-eu-ai-act` artifact
  reword and the `au-fedramp-class-a` version correction both narrow claims toward what the
  verbatims prove.
- **FINDING 34-A (MED) — the CHANGELOG's B-1 entry reads as a complete fix and is not.** It
  says "the `framework_labels` authority maps an alias to ONE canonical, but CMMC's program
  reality spans two labels", then describes the CMMC fan-out — accurate about CMMC, silent
  about the fact that the same one-canonical limitation applies to every other alias. The
  phase-33 audit had explicitly named the sweep ("survey `framework_labels` for multi-label
  families") and phase 34 neither did it nor recorded that it had not. Measured consequence
  (phase 35, 2026-08-10): `csf` resolved to **HITRUST CSF** on the master surface while
  `overlap` answered **NIST CSF 2.0**; `fedramp` resolved to a label with zero master rows;
  `nist-csf` errored as unknown on master. **Disposition: REMEDIATED in phase 35** — one shared
  registry (`framework_alias.py`), declared ambiguity, family-aware substring, and a contract
  test that fails on the pre-fix code (15 failures, including all three of the above).
- The workflow fix's claims check out: the `FileNotFoundError` was reproduced locally under
  hidden artifacts before the fix, and run 31340970701 completed **success** — the workflow's
  first green run since 2026-07-03.

## Pass 3 — chain and mutation integrity

- Domain-trap sweep over all 15 changed files: no `[FROM RECALL` in canonical files; "CMMC 3.0"
  appears only inside the phase-32 audit doc's own description of the trap list; no
  rescind/cancel language about the program.
- **The frozen CMMC set was not touched** — zero `au-cmmc-*` record lines changed in the phase-34
  diff, as required while the task-force report is pending.
- Support labels and terminal states unchanged except where evidence changed; no
  `ORPHAN_CONFIRMED` claimed anywhere.
- Commit hygiene: 7/7 commits carry no trailers, links, model ids, or personal emails, and all
  sit within the 1–2-sentence rule that phase 34 itself adopted after the phase-33 finding.

## Pass 4 — adversary output (mandatory)

**The claim most likely to be wrong:** *that phase 34 closed the phase-33 finding set.* It
closed each finding as written, but B-1 was written as an instance and the class stayed live —
so the honest reading is that the phase closed its ticket list, not its defect. The evidence
that overturns the stronger reading already exists: phase 35's measurements above.

**Runner-up, still open:** *that the alias class is now fully closed by phase 35.* The contract
test enforces agreement, non-emptiness, explicitness and declared ambiguity across three
resolvers — but it walks only terms **registered in the vocab**. An unregistered string a user
invents (`"cyber framework"`, `"iso 27k"`) still reaches the substring fallback; that fallback
is now family-aware and refuses cross-family matches, so it can return nothing, but the space
of unregistered inputs is not enumerable and therefore not fully tested. Overturning evidence
would be any unregistered input that resolves to a family other than the one a competent user
means. Where to look: the fallback in `framework_alias.resolve()` step 3, exercised with
adversarial inputs rather than registry terms.

## Findings → fixes

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 34-A | MED | CHANGELOG's B-1 entry reads as a class fix; only the CMMC instance was fixed, and the unswept ripple was not recorded | REMEDIATED phase 35 (`ae99dd7`, `c84f509`); this audit records the overclaim |
| 34-B | LOW | The phase closed without this audit, violating the gate it inherited | Recorded here; phase 35's close-out adds the gate to the phase checklist so the omission cannot repeat silently |

## Residual risk (never an all-clear)

1. **Unregistered alias inputs** (adversary runner-up) remain untested by construction.
2. **`au-iso-15408` is verified only as an obstacle** — the Common Criteria portal has refused
   this environment on every attempt across three phases, so the record's currency rests on the
   obstacle being real, not on a read of the source.
3. **This audit shares its author with the work** — mitigated by starting from a proven miss and
   by every mechanical claim being re-measured today, but not eliminated.
4. **Two horizon records remain OVERDUE** (`au-cms-arc-ampe`, `au-canada-itsg-33`) and are out
   of this audit's scope; phase 35 WS-7 addresses them.
