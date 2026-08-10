#!/usr/bin/env python3
"""
test_alias_contract.py — the cross-resolver alias contract.

dbz has four framework-name resolvers, each serving a different surface:

  1. dbz_query._resolve_fw        -> unified_mappings   (reverse, forward)
  2. dbz_query._master_fw_set     -> master_mappings    (master)
  3. spine_overlap.resolve_framework -> projection/ER   (overlap)
  4. master_surface.LabelResolver -> build time         (label registry)

Three of them carry their own alias dictionaries. Nothing reconciled them and no
test compared them, so the same word could mean different frameworks on different
subcommands: 'csf' answered HITRUST CSF on `master` and NIST CSF 2.0 on `overlap`,
'fedramp' resolved to a label with zero master rows (a silent empty answer), and
'nist-csf' errored on `master` while working elsewhere. Those are three instances of
one class; the phase-34 CMMC fix closed a fourth. This test is the gate for the CLASS.

Contract (per canonical-sources/framework_vocab.json, the single alias authority):
  A. AGREEMENT — SHORTHAND never means DIFFERENT FRAMEWORK FAMILIES on two surfaces.
     Divergence is allowed only when mechanically justified: the family the other
     resolver picked genuinely has no rows on this resolver's surface. The
     justification is re-measured here, never taken on trust. Exact canonical and
     deliberately-distinct labels are exempt — they resolve to THEMSELVES by design
     (framework_aliases._note), so a surface that lacks the exact label legitimately
     falls back to something else.
  B. NON-EMPTINESS — a registered alias resolves to a label that actually carries
     rows on that surface, or is a DECLARED data gap (framework_aliases.data_gaps).
  C. EXPLICITNESS — a registered alias resolves from a registry row, not from the
     ordering-dependent substring fallback (that fallback is what made 'csf' answer
     HITRUST: "HITRUST CSF" sorts before "NIST CSF").
  D. AMBIGUITY HONORED — every framework_aliases.ambiguous term errors and names all
     of its candidates on every surface, instead of silently picking one.

Needs a built grc.db. Runs in the gate battery and in CI (health.yml).
"""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "cross-mapping" / "output" / "grc.db"
VOCAB = ROOT / "canonical-sources" / "framework_vocab.json"

FAILS = []


def check(cond, label):
    print(("  ok:  " if cond else "  FAIL:") + " " + label)
    if not cond:
        FAILS.append(label)


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
    spec.loader.exec_module(mod)
    return mod


def _exact_labels(vocab: dict) -> set:
    """Canonical names + deliberately-distinct labels — the strings that ARE frameworks
    rather than shorthand for one. Exempt from the cross-surface agreement rule."""
    block = vocab["framework_aliases"]["canonical"]
    distinct = vocab["framework_aliases"].get("deliberately_distinct", {}).get("labels", [])
    return {c.lower() for c in block} | {d.lower() for d in distinct}


def _families(vocab: dict) -> dict:
    """label/alias (lowercased) -> family key. Canonical block members share the
    canonical's family; deliberately-distinct labels are their own family (the repo
    never merges version-ambiguous labels — framework_aliases._note)."""
    fam = {}
    block = vocab["framework_aliases"]["canonical"]
    for canonical, spec in block.items():
        fam[canonical.lower()] = canonical
        for a in spec.get("aliases", []):
            fam[a.lower()] = canonical
    for label in vocab["framework_aliases"].get("deliberately_distinct", {}).get("labels", []):
        fam[label.lower()] = label
    return fam


def _surface_labels(conn) -> dict:
    q = lambda sql: {r[0] for r in conn.execute(sql)}
    return {
        "unified": q("SELECT DISTINCT framework FROM unified_mappings"),
        "master": q("SELECT DISTINCT fw_a FROM master_mappings "
                    "UNION SELECT DISTINCT fw_b FROM master_mappings"),
        "projection": q("SELECT DISTINCT framework FROM framework_projection")
                      | q("SELECT DISTINCT framework FROM er_mappings"),
    }


def main() -> int:
    if not DB.exists():
        print("test_alias_contract: grc.db not built — run build_db.py first")
        return 1
    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    fam = _families(vocab)
    exact = _exact_labels(vocab)
    aliases_block = vocab["framework_aliases"]
    # '_'-prefixed keys are the repo's metadata convention (_note), never terms
    ambiguous = {k: v for k, v in aliases_block.get("ambiguous", {}).items()
                 if not k.startswith("_")}
    data_gaps = {k: v for k, v in aliases_block.get("data_gaps", {}).items()
                 if not k.startswith("_")}

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    dq = _load("dbz_query", "cross-mapping/engine/dbz_query.py")
    so = _load("spine_overlap", "cross-mapping/engine/spine_overlap.py")
    fa_mod = _load("framework_alias", "cross-mapping/engine/framework_alias.py")
    registry = fa_mod.load_registry(conn)
    surfaces = _surface_labels(conn)

    def fam_of(labels):
        return {fam.get(str(l).lower(), str(l)) for l in labels if l}

    def resolve_all(term):
        """(labels, ambiguity_flag) per surface. A resolver that raises the shared
        ambiguity error reports ambiguous=True rather than a label set."""
        out = {}
        for key, fn in (("unified", lambda t: dq._resolve_fw(t, conn)),
                        ("master", lambda t: dq._master_fw_set(conn, t)[0]),
                        ("projection", lambda t: [so.resolve_framework(conn, t)])):
            try:
                got = [x for x in (fn(term) or []) if x]
                out[key] = (got, False)
            except getattr(dq, "AmbiguousFrameworkError", ()) or ():
                out[key] = ([], True)
            except Exception as exc:  # a resolver must never crash on a registered alias
                out[key] = ([f"__EXC__{type(exc).__name__}"], False)
        return out

    # every registered alias string, plus the canonicals themselves
    terms = sorted({a.lower() for a in fam})

    print(f"alias contract: {len(terms)} registered terms, "
          f"{len(ambiguous)} declared ambiguous, {len(data_gaps)} declared data gaps\n")

    # ── D. declared-ambiguous terms must error everywhere, naming their candidates ──
    for term, spec in sorted(ambiguous.items()):
        res = resolve_all(term)
        flagged = [k for k, (labels, amb) in res.items() if amb]
        check(len(flagged) == 3,
              f"D: ambiguous {term!r} errors on all three surfaces (got {sorted(flagged)})")
        cands = spec.get("candidates", [])
        check(len(cands) >= 2, f"D: ambiguous {term!r} declares >=2 candidates")

    # ── A/B/C over every non-ambiguous registered term ──
    for term in terms:
        if term in ambiguous:
            continue
        res = resolve_all(term)
        crashed = [k for k, (labels, _) in res.items()
                   if any(str(l).startswith("__EXC__") for l in labels)]
        check(not crashed, f"no resolver crashes on registered alias {term!r} ({crashed})")
        if crashed:
            continue

        # B. non-emptiness: a resolution must point at a label with rows on that surface,
        #    unless the alias is a declared data gap for it.
        for key, (labels, _) in res.items():
            if not labels:
                continue
            live = [l for l in labels if l in surfaces[key]]
            gap = term in data_gaps and key in data_gaps[term].get("surfaces", [])
            check(bool(live) or gap,
                  f"B: {term!r} on {key} resolves to a label with rows "
                  f"(got {labels}; declared gap={gap})")

        # A. agreement (SHORTHAND ONLY — exact labels resolve to themselves by design):
        #    no two surfaces may resolve the term to disjoint families, unless the
        #    missing family genuinely has no rows on that surface.
        if term in exact:
            continue
        fams = {k: fam_of(v[0]) for k, v in res.items() if v[0]}
        keys = sorted(fams)
        for i, ka in enumerate(keys):
            for kb in keys[i + 1:]:
                if fams[ka] & fams[kb]:
                    continue
                # a declared family group makes its members one thing (framework_vocab
                # framework_aliases.family_groups, e.g. cmmc = CMMC 2.0 + 800-171 r2):
                # a surface that can only carry one label per answer (overlap computes a
                # pairwise percentage) legitimately returns a single member.
                if any(fa_mod.compatible_families(x, y, registry)
                       for x in fams[ka] for y in fams[kb]):
                    continue
                # justified? every family kb picked is absent from ka's surface (and vice versa)
                def absent(from_key, families):
                    for f in families:
                        members = {l for l, fm in fam.items() if fm == f}
                        if any(lbl.lower() in members for lbl in surfaces[from_key]):
                            return False
                    return True
                justified = absent(ka, fams[kb]) and absent(kb, fams[ka])
                check(justified,
                      f"A: {term!r} means {sorted(fams[ka])} on {ka} but {sorted(fams[kb])} "
                      f"on {kb} — different frameworks, not surface-justified")

        # C. explicitness: a registered alias must resolve via a registry row, never via
        #    the ordering-dependent substring fallback.
        canon = fam.get(term)
        m_labels = res["master"][0]
        if canon and m_labels and canon in surfaces["master"]:
            check(canon in set(m_labels) or fam_of(m_labels) == {canon},
                  f"C: {term!r} resolves on master to its registry family {canon!r} "
                  f"(got {m_labels})")

    # ── E. historical regressions: the exact inputs that shipped wrong answers. These
    #    are pinned by input string, not derived from the registry, so a future registry
    #    edit cannot quietly retire the guard. Each names the phase that found it.
    print()
    for term, rule, why in (
        ("csf", "ambiguous_or_nist",
         "phase-35: resolved to HITRUST CSF on master (substring, alphabetical) while "
         "overlap answered NIST CSF 2.0 — same word, two frameworks"),
        ("nist-csf", "resolves_everywhere",
         "phase-35: errored as unknown on master while working on reverse/forward"),
        ("fedramp", "no_silent_empty",
         "phase-35: resolved to a label with zero master rows — a silent empty answer"),
        ("cmmc", "no_silent_empty",
         "phase-33 finding B-1: master answered 0 while 105 SOC 2 pairs existed"),
    ):
        res = resolve_all(term)
        if rule == "ambiguous_or_nist":
            # acceptable: every surface errors as ambiguous, OR every surface that
            # answers lands in the NIST CSF family — never HITRUST for a bare 'csf'.
            amb = all(a for (_, a) in res.values())
            answered = {k: fam_of(v[0]) for k, v in res.items() if v[0]}
            nist_only = answered and all(
                f & {"NIST CSF 2.0", "NIST CSF"} and not (f & {"HITRUST CSF"})
                for f in answered.values())
            check(amb or nist_only, f"E: {term!r} — {why} (got {answered or 'ambiguous'})")
        elif rule == "resolves_everywhere":
            missing = [k for k, (labels, amb) in res.items() if not labels and not amb]
            check(not missing, f"E: {term!r} resolves on every surface — {why} "
                               f"(unresolved on {missing})")
        elif rule == "no_silent_empty":
            for key, (labels, amb) in res.items():
                if amb or not labels:
                    continue
                live = [l for l in labels if l in surfaces[key]]
                gap = term in data_gaps and key in data_gaps[term].get("surfaces", [])
                check(bool(live) or gap,
                      f"E: {term!r} on {key} answers from real rows or a declared gap "
                      f"— {why} (got {labels})")

    conn.close()
    print("\nALIAS CONTRACT:", "PASS" if not FAILS else f"FAIL ({len(FAILS)})")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
