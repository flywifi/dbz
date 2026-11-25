#!/usr/bin/env python3
"""
cfr_versions.py — two versions of one regulation, paragraph by paragraph (phase 57).

The HIPAA Privacy Rule final rule of 2026 (FR doc 2026-23429, 91 FR 74848, RIN 0945-AA00; published
2026-11-19, effective 2027-01-19, compliance 2027-07-19) amends 45 CFR 164 Subpart E. This module
builds both versions as paragraph trees and the paragraph-level difference between them:

  in force   the eCFR point-in-time XML of Subpart E as of 2026-11-18 (source_manifest
             'ecfr-45cfr164e-2026-11-18-xml')
  amended    the in-force tree with the rule's numbered amendatory instructions applied in order;
             the text of a revised or added paragraph is the Federal Register's own (source_manifest
             'hhs-hipaa-privacy-final-rule-2026-regtext')

Legal effect is the instructions. Text the FR reprints without an instruction is context only; where
it differs from what the instructions produce, the paragraph is 'reprint_differs' and is never
carried, until the eCFR codifies the rule on the effective date and `--verify-ecfr` settles it.

A mapping on an in-force paragraph is carried to the amended version only when the provision's text is
unchanged: its whole subtree is identical (at the same id, or at the id an instruction redesignates it
to), every ancestor's lead-in and heading is identical, and no reprint disagrees. Carry is by paragraph
identity, never by citation string: the rule removes 164.520(c)(2)(ii) and redesignates (c)(2)(iii) as
(c)(2)(ii), so the string '164.520(c)(2)(ii)' names a different requirement in each version.

Usage:
    python3 cross-mapping/engine/cfr_versions.py --report
    python3 cross-mapping/engine/cfr_versions.py --selftest
    python3 cross-mapping/engine/cfr_versions.py --verify-ecfr 2027-01-19   # network, report-only
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_INGEST = _HERE.parent / "nist-catalog" / "ingestion"
for _p in (str(_INGEST), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OLD_LABEL = "HIPAA Privacy Rule"
NEW_LABEL = "HIPAA Privacy Rule (2026 Final Rule)"
REGULATION = "45 CFR 164 Subpart E"
IN_FORCE_SRC = "ecfr-45cfr164e-2026-11-18-xml"
AMENDMENT_SRC = "hhs-hipaa-privacy-final-rule-2026-regtext"
VERSIONS = {
    OLD_LABEL: "45 CFR 164 Subpart E as in force 2026-11-18 (eCFR point-in-time)",
    NEW_LABEL: "45 CFR 164 Subpart E as amended by 91 FR 74848 (FR doc 2026-23429; published 2026-11-19; "
               "effective 2027-01-19; compliance 2027-07-19)",
}
SUBPART_INSTRUCTIONS = range(4, 13)   # 1-3 are Part 160 and the two authority citations
ECFR_URL = "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-45.xml?part=164&subpart=E"
CARRY = ("unchanged", "unchanged_redesignated")
STATUSES = ("unchanged", "unchanged_redesignated", "lead_in_changed", "reprint_differs", "changed",
            "removed", "not_in_amended_text", "added")

# ---------------------------------------------------------------------------------------------------
# Paragraph trees. Ids follow the repo's native citation form: '164.502(a)(5)(ii)(B)(2)(vii)';
# definitions are '164.501[Term]' with their numbered paragraphs nested under the term.
# ---------------------------------------------------------------------------------------------------
ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv",
         "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv", "xxvi", "xxvii",
         "xxviii", "xxix", "xxx"]
LOWER = [chr(c) for c in range(ord("a"), ord("z") + 1)] + ["aa", "bb", "cc", "dd"]
UPPER = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
DIGIT = [str(n) for n in range(1, 120)]
LEVEL_SEQ = {1: LOWER, 2: DIGIT, 3: ROMAN, 4: UPPER, 5: DIGIT, 6: ROMAN}
DEF_SEQ = {1: DIGIT, 2: ROMAN, 3: UPPER, 4: DIGIT, 5: ROMAN}
DES = r"\((?:<I>)?(?:[a-z]{1,4}|\d{1,3}|[A-Z])(?:</I>)?\)"


def norm(s: str) -> str:
    """Rendering-neutral text: eCFR XML and FR plain text differ in quotes, dashes and the section sign."""
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = s.replace("—", "--").replace("–", "-").replace("``", '"').replace("''", '"')
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = re.sub(r"\bSecs\.\s+", "§§ ", s)
    s = re.sub(r"\bSec\.\s+", "§ ", s)
    return re.sub(r"\s+", " ", s).strip()


def _candidates(d, stack, seqs):
    out = []
    for L, seq in seqs.items():
        if d not in seq:
            continue
        if L == len(stack) + 1 and seq.index(d) == 0:
            out.append(("child", L))
        if L <= len(stack) and stack[L - 1][0] == L and stack[L - 1][1] in seq \
                and seq.index(stack[L - 1][1]) + 1 < len(seq) and seq[seq.index(stack[L - 1][1]) + 1] == d:
            out.append(("sibling", L))
    return out


def place(d, stack, lookahead=None, italic=None, seqs=None):
    """Level of designator d given the open path. '(i)' as letter vs roman is settled by what follows:
    a roman (i) is followed by (ii) before any (j); a letter (i) by (j) before any (ii)."""
    seqs = seqs or LEVEL_SEQ
    c = _candidates(d, stack, seqs)
    if italic is not None:
        c = [x for x in c if (x[1] in (5, 6)) == italic] or c
    if not c:
        return None
    if len(c) > 1:
        roman = [x for x in c if seqs[x[1]] is ROMAN]
        other = [x for x in c if seqs[x[1]] is not ROMAN]
        if roman and other:
            nxt = next((x for x in (lookahead or []) if x in ("ii", "j")), None)
            c = roman if nxt == "ii" else other
        c = sorted(c, key=lambda x: -x[1]) if all(x[0] == "sibling" for x in c) \
            else sorted(c, key=lambda x: (x[0] != "child", -x[1]))
    return c[0][1]


def _chain(text, xml):
    """Leading designators of one paragraph -> ([(designator, heading, italic)], rest).
    eCFR: '(a) <I>Standard: X</I>&#x2014;(1) <I>Right to notice.</I> text'; FR: '(a) Standard: X--(1) ...'."""
    s = (html.unescape(text) if xml else text).strip()
    out = []
    while True:
        m = re.match(r"(<I>)?\((<I>)?([a-z]{1,4}|\d{1,3}|[A-Z])(</I>)?\)(</I>)?\s*", s)
        if not m:
            break
        d, ital = m.group(3), bool((m.group(1) and m.group(5)) or (m.group(2) and m.group(4)))
        s = s[m.end():]
        head = ""
        if re.match(r"(?:<I>)?" + DES, s):                      # '(e)(1) ...' back to back
            out.append((d, "", ital))
            continue
        if xml:
            h = re.match(r"<I>(.*?)</I>\s*", s, re.S)
            if h and not re.match(DES, h.group(1).strip()):
                head, s = h.group(1), s[h.end():]
            dash = re.match("(?:—|--)\\s*(?=(?:<I>)?" + DES + ")", s)
            if dash:
                s = s[dash.end():]
                out.append((d, head, ital))
                continue
            if head and re.match(r"(?:<I>)?" + DES + r"(?:</I>)?\s+(?:<I>|[A-Z“\"`])", s):
                out.append((d, head, ital))
                continue
        else:
            h = re.match(r"([^.;()]{1,160}?)--\s*(?=" + DES + ")", s)
            if h:
                head, s = h.group(1), s[h.end():]
                out.append((d, head, ital))
                continue
            h2 = re.match(r"([^()]{1,140}?\.)\s+(?=" + DES + r"\s+[A-Z\"`])", s)
            if h2:
                head, s = h2.group(1), s[h2.end():]
                out.append((d, head, ital))
                continue
        out.append((d, head, ital))
        break
    return out, s


def _definition_term(p, xml):
    m = re.match(r"\s*<I>([^<]{2,80})</I>\s+(?:means|has the meaning|includes|is)\b", p) if xml else \
        re.match(r"\s*([A-Z][A-Za-z ,'\-]{1,80}?)\s+(?:means|has the meaning|includes)\b", p)
    return m.group(1).strip() if m else None


def parse_definitions(sec, paras, xml):
    nodes, cur, sub = {}, None, []
    for p in paras:
        term = _definition_term(p, xml)
        if term:
            cur = f"{sec}[{term}]"
            nodes[cur] = {"head": term, "text": norm(p)}
            sub = []
            continue
        if cur is None:
            nodes.setdefault(sec, {"head": "", "text": ""})["text"] += " " + norm(p)
            continue
        ch, rest = _chain(p, xml)
        if not ch:
            nodes[sub[-1] if sub else cur]["text"] += " " + norm(rest)
            continue
        for d, head, _ital in ch:
            stack = [(i + 1, x.rsplit("(", 1)[1][:-1]) for i, x in enumerate(sub)]
            L = place(d, stack, None, None, DEF_SEQ)
            if L is None:
                raise ValueError(f"{cur}: cannot place ({d})")
            sub = sub[:L - 1] + [(sub[L - 2] if L > 1 else cur) + f"({d})"]
            nodes[sub[-1]] = {"head": norm(head), "text": norm(rest)}
    nodes.setdefault(sec, {"head": "", "text": ""})
    for v in nodes.values():
        v["text"] = v["text"].strip()
    return nodes


def parse_section(sec, paras, xml):
    if sec.endswith(".501") or sec.endswith(".103"):
        return parse_definitions(sec, paras, xml)
    return _parse_labelled(sec, paras, xml)


def _parse_labelled(sec, paras, xml):
    """Ordered {citation: {'head','text'}}. Unlabelled paragraphs join the previous labelled one."""
    nodes, order, stack, flat = {}, [], [], []
    for p in paras:
        q = html.unescape(p) if xml else p
        rng = re.match(r"\s*\(([a-z]{1,2}|\d{1,3}|[A-Z])\)\s*(?:-|–|through)\s*"
                       r"\(([a-z]{1,2}|\d{1,3}|[A-Z])\)\s*\[Reserved\]", q)
        if rng:                                                  # '(b)-(d) [Reserved]'
            a, b = rng.group(1), rng.group(2)
            seq = next(sq for sq in (LOWER, DIGIT, UPPER) if a in sq and b in sq)
            for d in seq[seq.index(a):seq.index(b) + 1]:
                flat.append(([(d, "", False)], "[Reserved]"))
            continue
        flat.append(_chain(p, xml))
    designators = [d for ch, _ in flat for d, _, _ in ch]
    k = 0
    for ch, rest in flat:
        if not ch:
            target = order[-1] if order else sec
            nodes.setdefault(target, {"head": "", "text": ""})["text"] += " " + norm(rest)
            continue
        for j, (d, head, ital) in enumerate(ch):
            k += 1
            la = designators[k:k + 400]
            L = place(d, stack, la, ital if xml else None)
            if L is None:
                # implied first child: the CFR omits a '(1)' (164.502(b) reads 'Minimum necessary--
                # Minimum necessary applies. ...' then '(2)'); the parent's own text is that paragraph.
                Lc = len(stack) + 1
                seq = LEVEL_SEQ.get(Lc)
                if seq and d in seq and seq.index(d) == 1 and order \
                        and order[-1] == sec + "".join(f"({x[1]})" for x in stack):
                    parent = order[-1]
                    first = parent + f"({seq[0]})"
                    nodes[first] = {"head": "", "text": nodes[parent]["text"], "implied": True}
                    nodes[parent]["text"] = ""
                    order.append(first)
                    stack = stack + [(Lc, seq[0])]
                    L = place(d, stack, la, ital if xml else None)
                if L is None:
                    raise ValueError(f"{sec}: cannot place ({d}) after {''.join('(' + x[1] + ')' for x in stack)}")
            stack = stack[:L - 1] + [(L, d)]
            cid = sec + "".join(f"({x[1]})" for x in stack)
            if cid in nodes:
                raise ValueError(f"duplicate {cid}")
            nodes[cid] = {"head": norm(head), "text": norm(rest) if j == len(ch) - 1 else ""}
            order.append(cid)
    nodes.setdefault(sec, {"head": "", "text": ""})
    out = {c: nodes[c] for c in [sec] + order}
    for v in out.values():
        v["text"] = v["text"].strip()
    return out


def ecfr_sections(xml_text: str) -> dict:
    """{section: {'title', 'paras': tree}} from eCFR versioner XML (DIV8 = section)."""
    out = {}
    for m in re.finditer(r'<DIV8 N="([^"]+)"[^>]*>(.*?)</DIV8>', xml_text, re.S):
        sec, body = m.group(1), m.group(2)
        heads = re.findall(r"<HEAD>(.*?)</HEAD>", body, re.S)
        ps = re.findall(r"<P>(.*?)</P>", body, re.S)
        out[sec] = {"title": norm(heads[0]) if heads else "", "paras": parse_section(sec, ps, xml=True)}
    return out


def ancestors(cid: str) -> list:
    """Proper ancestors that are paragraphs: '164.501[T](1)(i)' -> ['164.501[T]', '164.501[T](1)'];
    '164.520(c)(2)(ii)' -> ['164.520(c)', '164.520(c)(2)'] (the section node is not a lead-in)."""
    m = re.match(r"^(\d+\.\d+(?:\[[^\]]+\])?)((?:\([^)]+\))*)$", cid)
    base, path = m.group(1), m.group(2)
    toks = re.findall(r"\([^)]+\)", path)
    out = [base] if "[" in base and toks else []
    return out + [base + "".join(toks[:k]) for k in range(1, len(toks))]


def parent_of(cid: str) -> str:
    m = re.match(r"^(\d+\.\d+)(\[[^\]]+\])?((?:\([^)]+\))*)$", cid)
    sec, term, path = m.group(1), m.group(2) or "", m.group(3)
    toks = re.findall(r"\([^)]+\)", path)
    if toks:
        return sec + term + "".join(toks[:-1])
    return sec if term else ""


def order_key(cid: str):
    """Document order from the id alone (level-aware: '(i)' at depth 3 is roman, at depth 1 a letter)."""
    m = re.match(r"^(\d+)\.(\d+)(?:\[([^\]]+)\])?((?:\([^)]+\))*)$", cid)
    part, sec, term, path = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    seqs = DEF_SEQ if term is not None else LEVEL_SEQ
    idx = []
    for depth, tok in enumerate(re.findall(r"\(([^)]+)\)", path), start=1):
        seq = seqs.get(depth, [])
        idx.append(seq.index(tok) if tok in seq else 999)
    return (part, sec, (term or "").lower(), idx)


def own(v: dict) -> str:
    """A paragraph's wording for comparison: heading and text as one string, because the eCFR sets a heading
    apart in italics while the Federal Register runs it into the text; and a hyphen that a Federal Register
    line break left before a space closed up ('cost- management' = 'cost-management'). Both versions go
    through the same function, so a difference that remains is a difference in wording."""
    s = re.sub(r"\s+", " ", f"{v.get('head') or ''} {v.get('text') or ''}").strip()
    s = re.sub(r"\s*(?:--|\u2014)$", "", s)          # a heading's dash before sub-paragraphs on the next line
    return re.sub(r"(?<=\w)- (?=\w)", "-", s)


def subtree(tree: dict, cid: str) -> dict:
    """The provision as a whole: {relative id: wording} for the paragraph and every descendant."""
    return {c[len(cid):]: own(v) for c, v in tree.items() if c == cid or c.startswith(cid + "(")}


def subtree_sha256(tree: dict, cid: str) -> str:
    st = subtree(tree, cid)
    body = "\n".join(f"{rel}|{w}" for rel, w in sorted(st.items(), key=lambda kv: order_key(cid + kv[0])))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------------
# The Federal Register document: amendatory instructions and their regulatory text.
# ---------------------------------------------------------------------------------------------------
def extract_regtext(page: str) -> str:
    """The amendatory part of a govinfo FR HTML page: from 'For the reasons stated in the preamble' to the
    last '* * * * *' (the signature block after it is not part of the regulatory text)."""
    t = html.unescape(re.sub(r"<[^>]+>", "", page))
    start = t.find("For the reasons stated in the preamble")
    end = t.rfind("* * * * *")
    if start < 0 or end < start:
        raise ValueError("not an FR rule page with amendatory text")
    return t[start:end + len("* * * * *")] + "\n"


def split_instructions(regtext: str) -> dict:
    """{n: (instruction, section block)} for the numbered amendatory instructions."""
    out = {}
    for part in re.split(r"\n0\n(?=\d{1,2}\.\s)", regtext):
        m = re.match(r"(\d{1,2})\.\s(.*)", part, re.S)
        if not m:
            continue
        n, body = int(m.group(1)), m.group(2)
        k = re.search(r"\n\s*Sec\.\s+1\d\d\.\d+\s{2,}", body)
        instr, block = (body[:k.start()], body[k.start():]) if k else (body, "")
        out[n] = (re.sub(r"\s+", " ", instr.replace("\n0\n", " ")).strip(), block)
    return out


PATH = r"((?:\([a-zA-Z0-9]{1,5}\))+)"


def _expand(paths):
    """'(k)(1)(i) and (ii)' -> (k)(1)(i), (k)(1)(ii): a shorter path inherits the previous path's prefix."""
    out, prev = [], None
    for p in paths:
        toks = re.findall(r"\([^)]+\)", p)
        if prev and len(toks) < len(prev):
            toks = prev[:len(prev) - len(toks)] + toks
        out.append("".join(toks))
        prev = toks
    return out


def parse_ops(sec: str, instr: str) -> list:
    """Ordered operations of one instruction: (op, [paths], [new paths], item letter)."""
    if re.search(r"Revise and republish Sec\.", instr):
        return [("republish_section", [], [], "")]
    if re.search(r"Add Sec\.", instr):
        return [("add_section", [], [], "")]
    ops = []
    pieces = re.split(r"\b([a-z])\.\s+(?=[A-Z])", instr)
    items = list(zip(pieces[1::2], pieces[2::2])) if len(pieces) > 1 else [("", instr)]
    for letter, it in items:
        paths = _expand(re.findall(PATH, it))
        if "definition" in it:
            term = re.search(r"definitions? (?:for|of) [`\"]+([^`'\"]+)['\"]+", it)
            kind = "def_revise" if re.search(r"\b[Rr]evising\b", it) else "def_add"
            ops.append((kind, [term.group(1)] if term else [], [], letter))
        elif re.match(r"(?:Amend .*?by\s+)?Redesignating", it.strip()) or "Redesignating" in it[:40]:
            k = it.find(" as ")
            src, dst = _expand(re.findall(PATH, it[:k])), _expand(re.findall(PATH, it[k:]))
            ops.append(("redesignate", [sec + p for p in src], [sec + p for p in dst], letter))
        elif re.search(r"\bRemoving\b", it[:40]):
            ops.append(("remove", [sec + p for p in paths], [], letter))
        elif re.search(r"heading for paragraph", it):
            ops.append(("revise_heading", [sec + p for p in paths], [], letter))
        elif re.search(r"\b(Revising|revising)\b", it[:60]):
            ops.append(("revise", [sec + p for p in paths], [], letter))
        elif re.search(r"\b(Adding|adding)\b", it[:60]):
            ops.append(("add", [sec + p for p in paths], [], letter))
    return ops


def fr_paragraphs(block: str) -> list:
    """FR plain-text block -> paragraph strings (an indented line starts a paragraph)."""
    block = re.sub(r"\[\[Page \d+\]\]", "", block)
    paras, cur = [], None
    for ln in block.split("\n")[1:]:
        if re.match(r"\s*\*\s\*\s\*\s\*\s\*\s*$", ln):
            if cur is not None:
                paras.append(cur)
            paras.append("* * * * *")
            cur = None
            continue
        if re.match(r"    \S|     \S", ln):
            if cur is not None:
                paras.append(cur)
            cur = ln.strip()
        elif ln.strip() and cur is not None:
            cur += " " + ln.strip()
    if cur is not None:
        paras.append(cur)
    return [p for p in paras if p]


def fragment_tree(sec, block, hints, old_ids):
    """An FR fragment ('(b) * * *' path markers, '* * * * *' gaps). Placement allows forward jumps; a level
    is preferred when the resulting id is an instruction target (or its ancestor), else an in-force id."""
    nodes, stack = {}, []
    for p in fr_paragraphs(block):
        if p == "* * * * *":
            continue
        ch, rest = _chain(p, False)
        if not ch:
            if nodes:
                last = list(nodes)[-1]
                nodes[last]["text"] = (nodes[last]["text"] + " " + norm(rest)).strip()
            continue
        for j, (d, head, _ital) in enumerate(ch):
            cands = []
            for L, seq in LEVEL_SEQ.items():
                if d not in seq or L > len(stack) + 1:
                    continue
                if L <= len(stack) and (stack[L - 1][1] not in seq or seq.index(d) <= seq.index(stack[L - 1][1])):
                    continue
                cid = sec + "".join(f"({x[1]})" for x in stack[:L - 1]) + f"({d})"
                score = 2 if any(h == cid or h.startswith(cid + "(") for h in hints) else 1 if cid in old_ids else 0
                cands.append((score, L, cid))
            if not cands:
                raise ValueError(f"{sec}: fragment cannot place ({d}) after {stack}")
            _score, L, cid = sorted(cands, key=lambda x: (-x[0], -x[1]))[0]
            stack = stack[:L - 1] + [(L, d)]
            txt = norm(rest) if j == len(ch) - 1 else ""
            placeholder = txt.replace(" ", "") in ("***", "") and j == len(ch) - 1 and "* * *" in rest
            nodes[cid] = {"head": norm(head), "text": "" if placeholder else txt, "placeholder": placeholder}
    return nodes


def _ids_under(tree, cid):
    return [c for c in tree if c == cid or c.startswith(cid + "(")]


def apply_section(sec, old_tree, ops, block, ref):
    """-> (new tree, redesignations old->new, reprinted-without-instruction, removed ids, touched {id: ref})."""
    new = copy.deepcopy(old_tree)
    redes, removed, touched = {}, set(), {}
    if ops and ops[0][0] in ("republish_section", "add_section"):
        paras = [p for p in fr_paragraphs(block) if p != "* * * * *"]
        tree = parse_section(sec, paras, xml=False)
        for c in set(tree) | set(old_tree):
            touched[c] = ref
        return tree, {}, {}, set(), touched
    if ops and ops[0][0] in ("def_add", "def_revise"):
        frag = parse_definitions(sec, [p for p in fr_paragraphs(block) if p != "* * * * *"], xml=False)
        for kind, terms, _dst, letter in ops:
            for term in terms:
                tid = f"{sec}[{term}]"
                fids = [c for c in frag if c == tid or c.startswith(tid + "(")]
                if not fids:
                    raise ValueError(f"{kind} {tid}: no text in the FR block")
                if kind == "def_revise":
                    if tid not in new:
                        raise ValueError(f"{kind} {tid}: not in the in-force text")
                    for c in [c for c in new if c == tid or c.startswith(tid + "(")]:
                        del new[c]
                elif tid in new:
                    raise ValueError(f"{kind} {tid}: already defined")
                for c in fids:
                    new[c] = {"head": frag[c]["head"], "text": frag[c]["text"]}
                    touched[c] = f"{ref}{letter}"
        return new, {}, {}, set(), touched
    hints = [p for _op, a, b, _l in ops for p in a + b]
    frag = fragment_tree(sec, block, hints, set(old_tree))
    applied = set()
    for op, paths, dst, letter in ops:
        r = f"{ref}{letter}"
        if op == "remove":
            for p in paths:
                ids = _ids_under(new, p)
                if not ids:
                    raise ValueError(f"remove {p}: not in the in-force text")
                for c in ids:
                    del new[c]
                    removed.add(c)
                    touched[c] = r
        elif op == "redesignate":
            moved = {}
            for a, b in zip(paths, dst):
                ids = _ids_under(new, a)
                if not ids:
                    raise ValueError(f"redesignate {a}: not in the in-force text")
                for c in ids:
                    nid = b + c[len(a):]
                    moved[nid] = new.pop(c)
                    redes[c] = nid
                    touched[c] = r
            for c, v in moved.items():
                if c in new:
                    raise ValueError(f"redesignation collides at {c}")
                new[c] = v
        elif op in ("revise", "add"):
            for p in paths:
                fids = _ids_under(frag, p)
                if not fids:
                    raise ValueError(f"{op} {p}: no text in the FR block")
                if op == "revise":
                    if not _ids_under(new, p):
                        raise ValueError(f"revise {p}: not in the in-force text")
                    for c in _ids_under(new, p):
                        if not (frag.get(c) or {}).get("placeholder"):
                            del new[c]
                elif _ids_under(new, p):
                    raise ValueError(f"add {p}: already exists")
                for c in fids:
                    if not frag[c].get("placeholder"):
                        new[c] = {"head": frag[c]["head"], "text": frag[c]["text"]}
                        applied.add(c)
                        touched[c] = r
        elif op == "revise_heading":
            for p in paths:
                if p not in new or p not in frag:
                    raise ValueError(f"heading {p}")
                new[p] = dict(new[p], head=frag[p]["head"])
                applied.add(p)
                touched[p] = r
    reprinted = {c: v for c, v in frag.items() if not v.get("placeholder") and c not in applied}
    return new, redes, reprinted, removed, touched


# ---------------------------------------------------------------------------------------------------
# Both versions and their difference.
# ---------------------------------------------------------------------------------------------------
def build(in_force_xml: str, regtext: str, instructions=SUBPART_INSTRUCTIONS) -> dict:
    old = {s: v["paras"] for s, v in ecfr_sections(in_force_xml).items()}
    new = copy.deepcopy(old)
    redes, reprinted, removed, touched, log = {}, {}, set(), {}, []
    ins = split_instructions(regtext)
    for n in instructions:
        instr, block = ins[n]
        sec = re.search(r"Sec\.\s+(1\d\d\.\d+)", instr).group(1)
        ops = parse_ops(sec, instr)
        tree, r, rp, rm, t = apply_section(sec, new.get(sec, {}), ops, block, str(n))
        new[sec] = tree
        redes.update(r)
        reprinted.update(rp)
        removed |= rm
        touched.update(t)
        log.append((n, sec, [o[0] + o[3] for o in ops], len(old.get(sec, {})), len(tree)))
    OLD = {c: v for t in old.values() for c, v in t.items()}
    NEW = {c: v for t in new.values() for c, v in t.items()}
    return {"old": OLD, "new": NEW, "redes": redes, "reprinted": reprinted, "removed": removed,
            "touched": touched, "log": log}


def classify(b: dict) -> list:
    """One row per in-force paragraph, plus one per amended paragraph no in-force paragraph becomes."""
    OLD, NEW, redes, reprinted, removed, touched = (b[k] for k in ("old", "new", "redes", "reprinted",
                                                                 "removed", "touched"))
    rows, reached = [], set()
    for c in sorted(OLD, key=order_key):
        ref = touched.get(c, "")
        if c in removed:
            rows.append((c, "", "removed", ref, ""))
            continue
        c2 = redes.get(c, c)
        if c2 not in NEW:
            rows.append((c, "", "not_in_amended_text", ref, "absent from the republished section"))
            continue
        reached.add(c2)
        if subtree(OLD, c) != subtree(NEW, c2):
            rows.append((c, c2, "changed", ref or touched.get(c2, ""), ""))
            continue
        moved_anc = [a for a in ancestors(c) if a in OLD and
                     (redes.get(a, a) not in NEW or own(OLD[a]) != own(NEW[redes.get(a, a)]))]
        if moved_anc:
            rows.append((c, c2, "lead_in_changed", touched.get(moved_anc[-1], ""), "lead-in changed: " + ", ".join(moved_anc)))
            continue
        bad = [k for k in _ids_under(OLD, c) if redes.get(k, k) in reprinted and own(reprinted[redes.get(k, k)]) != own(OLD[k])]
        if bad:
            rows.append((c, c2, "reprint_differs", ref, "FR reprint without an instruction differs at " + ", ".join(redes.get(k, k) for k in bad)))
            continue
        rows.append((c, c2, "unchanged" if c2 == c else "unchanged_redesignated", ref, ""))
    for c2 in sorted(set(NEW) - reached, key=order_key):
        rows.append(("", c2, "added", touched.get(c2, ""), ""))
    # Reviewer hint, never a carry: an uncarried provision whose exact wording now stands at another number
    # that no instruction moved it to (164.502(a)(2)(ii) 'When required by the Secretary' is (a)(2)(iii)).
    at = {}
    for c2, v in NEW.items():
        at.setdefault((c2.split("(")[0], own(v)), []).append(c2)
    out = []
    for o, n, s, r, d in rows:
        if o and s in ("changed", "not_in_amended_text", "removed") and len(own(OLD[o])) >= 25:
            hits = [x for x in at.get((o.split("(")[0], own(OLD[o])), []) if x != n]
            if len(hits) == 1:
                d = (d + "; " if d else "") + f"same wording now at {hits[0]} (no instruction moves it; not carried)"
        out.append((o, n, s, r, d))
    return out


def _load_sources():
    from config import source_path  # type: ignore
    xml = source_path(IN_FORCE_SRC).read_text(encoding="utf-8")
    regtext = source_path(AMENDMENT_SRC).read_text(encoding="utf-8")
    return xml, regtext


def db_rows(b=None):
    """(regulation_paragraphs rows, regulation_paragraph_diff rows, stats) for build_db."""
    if b is None:
        b = build(*_load_sources())
    para_rows = []
    for label, tree, src in ((OLD_LABEL, b["old"], IN_FORCE_SRC), (NEW_LABEL, b["new"], AMENDMENT_SRC)):
        for i, c in enumerate(sorted(tree, key=order_key)):
            v = tree[c]
            para_rows.append({"framework": label, "version": VERSIONS[label], "regulation": REGULATION,
                              "paragraph_id": c, "parent_id": parent_of(c), "seq": i,
                              "heading": v.get("head") or "", "text": v["text"],
                              "subtree_sha256": subtree_sha256(tree, c),
                              "implied": int(bool(v.get("implied"))), "source_id": src})
    diff_rows = [{"framework_from": OLD_LABEL, "framework_to": NEW_LABEL, "regulation": REGULATION,
                  "old_id": o, "new_id": n, "status": s, "instruction": r, "detail": d}
                 for o, n, s, r, d in classify(b)]
    stats = {"paragraphs": {OLD_LABEL: len(b["old"]), NEW_LABEL: len(b["new"])},
             "by_status": {s: sum(1 for r in diff_rows if r["status"] == s) for s in STATUSES},
             "redesignations": len(b["redes"])}
    return para_rows, diff_rows, stats


def carry_map(conn) -> dict:
    """{in-force id: amended id} for paragraphs whose mappings carry (status unchanged / redesignated)."""
    try:
        return {o: n for o, n in conn.execute(
            "SELECT old_id, new_id FROM regulation_paragraph_diff WHERE framework_from=? AND framework_to=? "
            "AND status IN ('unchanged', 'unchanged_redesignated')", (OLD_LABEL, NEW_LABEL))}
    except Exception:
        return {}


# ---------------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------------
def report() -> int:
    b = build(*_load_sources())
    paras, diff, stats = db_rows(b)
    for n, sec, ops, a, z in b["log"]:
        print(f"  instruction {n:>2} {sec}: {' '.join(ops)} (paragraphs {a} -> {z})")
    print(f"  paragraphs: {stats['paragraphs']}; redesignations: {stats['redesignations']}")
    print(f"  by status: {stats['by_status']}")
    return 0


def verify_ecfr(date: str) -> int:
    """Compare the amended tree with the eCFR's codified Subpart E on DATE (report-only, network)."""
    import fetchkit  # type: ignore
    b = build(*_load_sources())
    body = fetchkit.fetch(ECFR_URL.format(date=date), timeout=120, retries=2).body.decode("utf-8")
    codified = {c: v for t in ecfr_sections(body).values() for c, v in t["paras"].items()}
    ids = sorted(set(codified) | set(b["new"]), key=order_key)
    diff = [c for c in ids if (c in codified) != (c in b["new"]) or
            (c in codified and own(codified[c]) != own(b["new"][c]))]
    print(f"eCFR {date}: {len(codified)} paragraphs; computed amended text: {len(b['new'])}; differing: {len(diff)}")
    for c in diff[:40]:
        print(f"  {c}: {'only in eCFR' if c not in b['new'] else 'only computed' if c not in codified else 'text differs'}")
    return 0 if not diff else 1


_SELFTEST_XML = """<DIV8 N="164.999" TYPE="SECTION"><HEAD>&#xA7; 164.999 Test section.</HEAD>
<P>(a) <I>Standard: Notice.</I> A covered entity must:</P>
<P>(1) Obtain an acknowledgment;</P>
<P>(2) Post the notice in a clear location;</P>
<P>(i) At each site; and</P>
<P>(ii) On its web site.</P>
<P>(3) Revise the notice as required by paragraph (a)(2) of this section.</P>
<P>(b) <I>Uses.</I> A covered entity may use information as follows:</P>
<P>(1) For treatment.</P>
<P>(c)-(g) [Reserved]</P>
<P>(h) <I>Records.</I> Records must be kept:</P>
<P>(1) For six years.</P>
<P>(i) <I>Letter heading.</I> A paragraph lettered (i).</P>
<P>(j) <I>Letter heading.</I> A paragraph lettered (j).</P>
</DIV8>"""
_SELFTEST_REG = """Header

0
1. Amend Sec.  164.999 by: a. Removing paragraph (a)(1); b. Redesignating paragraphs (a)(2) and (3) as paragraphs (a)(1) and (2), respectively; c. Revising paragraph (b); and d. Revising paragraph (h). The revisions read as follows:

    Sec.  164.999   Test section.

    (a) * * *
    (2) Revise the notice as required by paragraph (a)(1) of this section.
    (b) Uses. A covered entity may use and disclose information as follows:
    (1) For treatment.
* * * * *
    (h) Records. Records must be kept:
    (1) For six years.
* * * * *
"""


def selftest() -> int:
    ok = fail = 0

    def check(cond, msg):
        nonlocal ok, fail
        print(f"  [{'ok' if cond else 'FAIL'}] {msg}")
        ok, fail = ok + bool(cond), fail + (not cond)

    b = build(_SELFTEST_XML, _SELFTEST_REG, instructions=[1])
    st = {r[0] or r[1]: r for r in classify(b)}
    check(st["164.999(a)(1)"][2] == "removed",
          "a removed paragraph is 'removed' although its id is reused by the next paragraph")
    check(st["164.999(a)(2)(i)"][1:3] == ("164.999(a)(1)(i)", "unchanged_redesignated"),
          "a redesignated paragraph with identical text carries at its new id (never by citation string)")
    check(st["164.999(a)(3)"][2] == "reprint_differs",
          "a redesignated paragraph the FR reprints with different text (an updated cross-reference) is not carried")
    check(st["164.999(b)(1)"][2] == "lead_in_changed",
          "identical text under a revised lead-in is 'lead_in_changed', not carried")
    check(st["164.999(h)"][2] == "unchanged" and st["164.999(h)(1)"][2] == "unchanged",
          "a revised paragraph with the same wording is unchanged although the eCFR italicises its heading and the FR does not")
    check("164.999(i)" in b["old"] and "164.999(h)(1)(i)" not in b["old"] and "164.999(a)(2)(ii)" in b["old"],
          "after (h)(1), an (i) followed by (j) is a letter; after (a)(2), an (i) followed by (ii) is roman")
    carried = sorted((r[0] for r in classify(b) if r[2] in CARRY), key=order_key)
    check(carried == ["164.999(a)(2)", "164.999(a)(2)(i)", "164.999(a)(2)(ii)", "164.999(c)", "164.999(d)", "164.999(e)",
                      "164.999(f)", "164.999(g)", "164.999(h)", "164.999(h)(1)", "164.999(i)", "164.999(j)"],
          f"carried exactly the 12 provisions whose text is unchanged (got {len(carried)})")
    try:
        build(_SELFTEST_XML, _SELFTEST_REG.replace("Removing paragraph (a)(1)", "Removing paragraph (a)(9)"), instructions=[1])
        check(False, "an instruction that names a missing paragraph stops the build")
    except ValueError:
        check(True, "an instruction that names a missing paragraph stops the build")
    try:
        xml, regtext = _load_sources()
    except Exception as e:  # pinned sources are committed; their absence is a failure, not a skip
        check(False, f"pinned sources load ({e})")
        print(f"[selftest] cfr-versions: {ok}/{ok + fail} passed")
        return 1
    b = build(xml, regtext)
    rows = {r[0] or r[1]: r for r in classify(b)}
    check(b["redes"] == {"164.502(a)(5)(ii)(B)(2)(vii)": "164.502(a)(5)(ii)(B)(2)(viii)",
                         "164.502(a)(5)(ii)(B)(2)(viii)": "164.502(a)(5)(ii)(B)(2)(ix)",
                         "164.520(c)(2)(iii)": "164.520(c)(2)(ii)", "164.520(c)(2)(iii)(A)": "164.520(c)(2)(ii)(A)",
                         "164.520(c)(2)(iii)(B)": "164.520(c)(2)(ii)(B)", "164.520(c)(2)(iv)": "164.520(c)(2)(iii)"},
          "pinned rule: the six redesignations of instructions 5c and 9h")
    check(rows["164.520(c)(2)(ii)"][2] == "removed" and rows["164.520(c)(2)(iii)(A)"][1:3] == ("164.520(c)(2)(ii)(A)", "unchanged_redesignated"),
          "pinned rule: 164.520(c)(2)(ii) is removed; the old (c)(2)(iii)(A) carries at (c)(2)(ii)(A)")
    check(rows["164.520(c)(2)(iv)"][2] == "reprint_differs",
          "pinned rule: the reprinted (c)(2)(iii) cites (c)(2)(ii) where the redesignated text cites (c)(2)(iii)")
    check(rows["164.501[Health care operations]"][2] == "changed" and rows["164.501[Electronic health record]"][2] == "added",
          "pinned rule: instruction 4 revises 'Health care operations' and adds 'Electronic health record'")
    check(rows["164.525"][2] == "added" and rows["164.524(c)(4)(iii)"][2] == "not_in_amended_text",
          "pinned rule: 164.525 is new; 164.524(c)(4)(iii) is absent from the republished 164.524")
    print(f"[selftest] cfr-versions: {ok}/{ok + fail} passed")
    return 0 if fail == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--report", action="store_true")
    g.add_argument("--selftest", action="store_true")
    g.add_argument("--verify-ecfr", metavar="DATE")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.verify_ecfr:
        return verify_ecfr(a.verify_ecfr)
    return report()


if __name__ == "__main__":
    sys.exit(main())
