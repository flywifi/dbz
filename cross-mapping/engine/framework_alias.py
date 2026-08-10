#!/usr/bin/env python3
"""
framework_alias.py — the ONE framework-name resolution authority.

Before this module, dbz had three query-time resolvers, each with its own
hand-maintained alias dictionary and each ending in a "first substring match wins"
fallback over a list whose order came from SQL. Nothing reconciled them and no test
compared them, which produced (all measured, phase 35):

  * 'csf'      -> HITRUST CSF on the master surface (because "HITRUST CSF" sorts
                  before "NIST CSF") while `overlap` answered NIST CSF 2.0 — the same
                  word meaning two different frameworks in one session;
  * 'fedramp'  -> a label carrying zero master rows: a silent empty answer;
  * 'nist-csf' -> unknown framework on master, fine everywhere else.

The rules here are deliberately conservative, because a wrong framework answer is
worse than no answer:

  1. The registry wins. `framework_labels` (built from framework_vocab.json by
     master_surface.load_label_rows) maps alias -> canonical. An exact hit resolves.
  2. Deliberately-distinct labels resolve to THEMSELVES — version-ambiguous names
     ('ISO/IEC 27001', hub-era 'NIST CSF') are never merged into a versioned
     canonical (framework_vocab framework_aliases._note).
  3. Declared-ambiguous terms NEVER resolve silently: they raise
     AmbiguousFrameworkError naming every candidate, so the caller can tell the user
     what to type instead.
  4. The substring fallback collects ALL matches instead of taking the first. One
     match resolves; several matching DIFFERENT families raise the same ambiguity
     error; several matching one family resolve to it. Ordering can no longer decide
     which framework the user meant.
  5. Resolution is always relative to a surface's own label pool, so a resolver can
     only ever return a label that exists where it is about to query.

`tools`-free, stdlib-only, and safe to import from any engine module.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VOCAB_PATH = REPO_ROOT / "canonical-sources" / "framework_vocab.json"


class AmbiguousFrameworkError(ValueError):
    """A term matches more than one framework family. Carries the candidates so the
    caller can print them — never resolved by guessing."""

    def __init__(self, term: str, candidates, reason: str = ""):
        self.term = term
        self.candidates = sorted(set(candidates))
        self.reason = reason
        detail = f" — {reason}" if reason else ""
        super().__init__(
            f"{term!r} is ambiguous: it can mean {', '.join(self.candidates)}{detail}. "
            f"Re-run with the exact label you mean.")


def _vocab() -> dict:
    with open(VOCAB_PATH, encoding="utf-8") as f:
        return json.load(f).get("framework_aliases", {})


def load_registry(conn=None) -> dict:
    """{'alias_lower': canonical} plus the ambiguity and data-gap declarations.

    Prefers the framework_labels DB table (what the build actually loaded); falls back
    to the vocab file when the table is absent (fresh checkout, tooling contexts)."""
    v = _vocab()
    alias_map: dict[str, str] = {}
    if conn is not None:
        try:
            for alias, canonical in conn.execute(
                    "SELECT alias, canonical FROM framework_labels"):
                alias_map[str(alias).lower()] = canonical
        except Exception:
            alias_map = {}
    if not alias_map:
        for canonical, spec in v.get("canonical", {}).items():
            alias_map[canonical.lower()] = canonical
            for a in spec.get("aliases", []):
                alias_map[a.lower()] = canonical
        for label in v.get("deliberately_distinct", {}).get("labels", []):
            alias_map[label.lower()] = label
    groups = {k.lower(): val for k, val in v.get("family_groups", {}).items()
              if not k.startswith("_")}
    return {
        "alias_map": alias_map,
        "ambiguous": {k.lower(): val for k, val in v.get("ambiguous", {}).items()
                      if not k.startswith("_")},
        "data_gaps": {k.lower(): val for k, val in v.get("data_gaps", {}).items()
                      if not k.startswith("_")},
        "family_groups": groups,
    }


def group_for(term: str, registry: dict) -> list[str]:
    """The declared multi-label family group for a shorthand, or []. A group exists only
    where an external authority makes two labels one thing (e.g. CMMC Level 2 assesses
    against 800-171 r2 under the May-2024 class deviation) — never as a convenience."""
    spec = registry.get("family_groups", {}).get(str(term).strip().lower())
    return list(spec.get("labels", [])) if spec else []


def compatible_families(a: str, b: str, registry: dict) -> bool:
    """True when two canonical families may answer the same query: identical, or both
    named by one declared family group."""
    if a == b:
        return True
    for spec in registry.get("family_groups", {}).values():
        labels = set(spec.get("labels", []))
        if a in labels and b in labels:
            return True
    return False


def declared_gap(term: str, surface: str, registry: dict) -> dict | None:
    """The data-gap declaration for this term on this surface, if any — the honest
    'this framework has no rows here, and that is a known fact, not a bug' record."""
    spec = registry["data_gaps"].get(str(term).strip().lower())
    if spec and surface in spec.get("surfaces", []):
        return spec
    return None


def resolve(term: str, pool, registry: dict, *, surface: str = "") -> list[str]:
    """Resolve `term` to labels that EXIST in `pool` (a surface's own label list).

    Returns [] when nothing matches — callers keep their existing not-found handling.
    Raises AmbiguousFrameworkError for declared-ambiguous terms and for substring
    matches spanning more than one family.
    """
    if not term:
        return []
    t = str(term).strip()
    tl = t.lower()
    pool = list(pool)
    pool_lower = {p.lower(): p for p in pool}
    alias_map = registry["alias_map"]

    amb = registry["ambiguous"].get(tl)
    if amb:
        present = [c for c in amb.get("candidates", []) if c in pool]
        raise AmbiguousFrameworkError(t, present or amb.get("candidates", []),
                                      amb.get("reason", ""))

    # 1. the label itself, exactly (case-insensitive) — an exact label is never fanned
    #    out; asking for "CMMC 2.0" means that label, not its family group.
    if tl in pool_lower:
        return [pool_lower[tl]]

    canonical = alias_map.get(tl)

    # 2. a declared family group fans out to every member present on this surface (the
    #    CMMC case: two labels, one assessment basis, by legal instrument). Checked
    #    BEFORE the single-canonical shortcut, or the group would resolve to one member.
    group = [g for g in group_for(tl, registry) if g.lower() in pool_lower]
    if group:
        return [pool_lower[g.lower()] for g in group]

    # 3. the registry's canonical for this alias, if that canonical is in the pool
    if canonical and canonical.lower() in pool_lower:
        return [pool_lower[canonical.lower()]]

    # 3. bounded substring fallback — every match, never "the first one". A hit whose
    #    family differs from the term's registered family is REJECTED, not returned:
    #    substituting a neighbouring label is how 'hipaa' answered with the Privacy
    #    Rule and '800-53' with the Rev 4 Appendix J catalog. Version-ambiguous labels
    #    are never silently accepted for a versioned query (framework_aliases._note).
    hits = [p for p in pool if tl in p.lower() or p.lower() in tl]
    if canonical:
        hits = [h for h in hits
                if compatible_families(alias_map.get(h.lower(), h), canonical, registry)]
    if len(hits) == 1:
        return hits
    if len(hits) > 1:
        fams = {alias_map.get(h.lower(), h) for h in hits}
        if len(fams) > 1 and not all(
                compatible_families(f, next(iter(fams)), registry) for f in fams):
            raise AmbiguousFrameworkError(
                t, hits, "matches several unrelated framework labels")
        return hits

    # 4. registry knows the alias but this surface has no row for it: report nothing
    #    rather than substituting a different framework (the 'hipaa' -> Privacy Rule
    #    substitution this module exists to prevent).
    return []
