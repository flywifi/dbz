"""
Canonical normal-form parsers for the overlap spine (stdlib only, deterministic).

The spine pivots on a NIST 800-53 r5 coordinate:
    r5_control  (AC-2)                     coarsest
      r5_subpart (AC-2 d.1)                statement/AP granularity  [PRIMARY]
        cci      (CCI-000015)              finest, where it exists

The same logical sub-part is written differently by every source:
    DISA CCI list   'AC-2(3) d 1'   (spaced)         -> parse_cci_index
    HITRUST hub     'AC-2(3)d1'     (compressed)     -> parse_hitrust_ref   (Phase 3)
    CUI overlay     'AC-02-00-01'   (sort id)        -> parse_cui_sort_id
    171A/53A cross  'AC-02d.01'     (objective)      -> parse_objective     (Phase 2/4)

Every parser returns the canonical control id (via `normalize_control_id`) plus an
optional dotted lowercase sub-part path.  `canon_subpart(ctrl, path)` joins them into
the one canonical string used everywhere: "AC-2 d.1".

Design rule: only claim a sub-part when the source gives a clean statement part
(letter, optionally followed by numbers).  The r4 assessment-objective decomposition
(`.2 (i)`, `(i and ii)`) does NOT map cleanly onto an r5 statement part, so those
resolve to control-level (path=None) and keep their raw form for provenance.  Never
fabricate a sub-part.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Base control id, optional enhancement in parens (a space before the paren is allowed,
# as the DISA list writes 'AC-11 (1)').  The numeric groups may carry leading zeros
# ('AC-01', 'AC-02(01)') which we strip.
_CTRL_RE = re.compile(r"^([A-Z]{2,3})-(\d{1,3})(?:\s*\((\d{1,3})\))?")


def normalize_control_id(raw: str) -> Optional[str]:
    """
    Normalize a NIST 800-53 control/enhancement id to canonical unpadded form.

    'AC-01' -> 'AC-2' is wrong; zero-strip only: 'AC-01' -> 'AC-1',
    'AC-02(01)' -> 'AC-2(1)', 'AC-11 (1)' -> 'AC-11(1)', 'ac-2.1' handled by callers.
    Returns None if the string does not start with a control id.
    """
    if not isinstance(raw, str):
        return None
    m = _CTRL_RE.match(raw.strip().upper())
    if not m:
        return None
    fam, num, enh = m.group(1), int(m.group(2)), m.group(3)
    cid = f"{fam}-{num}"
    if enh is not None:
        cid += f"({int(enh)})"
    return cid


def canon_subpart(control_id: str, path: Optional[str]) -> Optional[str]:
    """Join a canonical control id and a dotted path into 'AC-2 d.1' (or None)."""
    if not control_id or not path:
        return None
    return f"{control_id} {path}"


# A statement-part remainder: a single letter, then optional whitespace-separated
# numbers/letters, e.g. 'a', 'b 1', 'a 2'.  (Not '.2 (i)' — that is objective form.)
_STMT_RE = re.compile(r"^([a-z])((?:\s+\d+)*)\s*$")


def parse_cci_index(raw: str) -> List[Tuple[str, Optional[str]]]:
    """
    Parse a DISA CCI 'index' cell into [(control_id, subpart_path_or_None), ...].

    'AC-1 a'          -> [('AC-1', 'a')]
    'AC-1 b 1'        -> [('AC-1', 'b.1')]
    'AC-2(1) b'       -> [('AC-2(1)', 'b')]
    'AC-1'            -> [('AC-1', None)]            whole control
    'AC-1.2 (i)'      -> [('AC-1', None)]            r4 objective form -> control-level
    'AC-16 (2).1 (i)' -> [('AC-16(2)', None)]        enhancement, objective form
    Unparseable       -> []
    """
    if not isinstance(raw, str):
        return []
    s = raw.strip()
    cid = normalize_control_id(s)
    if not cid:
        return []
    m = _CTRL_RE.match(s.upper())
    remainder = s[m.end():].strip()
    if not remainder:
        return [(cid, None)]
    # Statement part?  Must be evaluated on the lowercased remainder.
    sm = _STMT_RE.match(remainder.lower())
    if sm:
        letter = sm.group(1)
        nums = sm.group(2).split()
        path = ".".join([letter] + nums) if nums else letter
        return [(cid, path)]
    # Objective form ('.2 (i)', '.1 (i and ii)', '(1).1 (ii)') -> control-level only.
    return [(cid, None)]


_HITRUST_SUFFIX_TOK = re.compile(r"[a-z]|\d+")


def parse_hitrust_ref(raw: str) -> List[Tuple[str, Optional[str]]]:
    """
    Parse a HITRUST cross-reference NIST cell token (compressed sub-part form) into
    [(control_id, subpart_path_or_None)].

    'AC-17a'   -> [('AC-17', 'a')]
    'CA-1a1b'  -> [('CA-1', 'a.1.b')]
    'CA-1a2'   -> [('CA-1', 'a.2')]
    'AC-2(3)a' -> [('AC-2(3)', 'a')]
    'AC-2c'    -> [('AC-2', 'c')]
    'AC-2(1)'  -> [('AC-2(1)', None)]        whole enhancement
    Unparseable / unexpected suffix -> control-level, never fabricated.
    """
    if not isinstance(raw, str):
        return []
    s = raw.strip()
    cid = normalize_control_id(s)
    if not cid:
        return []
    m = _CTRL_RE.match(s.upper())
    remainder = s[m.end():].strip()
    if not remainder:
        return [(cid, None)]
    if not re.fullmatch(r"[A-Za-z0-9]+", remainder):
        return [(cid, None)]  # unexpected shape -> control-level
    toks = _HITRUST_SUFFIX_TOK.findall(remainder.lower())
    path = ".".join(toks) if toks else None
    return [(cid, path)]


# 171A/53A objective id: 'AC-02d.01', 'AC-06(01)(a)[01]', 'IA-03_ODP[01]', 'AC-05_ODP'
_OBJ_ODP_RE = re.compile(
    r"^([A-Z]{2,3})-(\d{1,3})(?:\((\d{1,3})\))?_ODP(?:\[(\d+)\])?\s*$")
_OBJ_CTRL_RE = re.compile(
    r"^([A-Z]{2,3})-(\d{1,3})(?:\((\d{1,3})\))?")
_OBJ_SUFFIX_TOK = re.compile(r"[a-z]|\d+")


def _odp_to_oscal(fam: str, num: int, enh: Optional[int], idx: Optional[int]) -> str:
    """Convert crosswalk ODP ref to canonical OSCAL param id."""
    base = f"{fam.lower()}-{num:02d}"
    if enh is not None:
        base += f".{enh:02d}"
    if idx is not None:
        return f"{base}_odp.{idx:02d}"
    return f"{base}_odp"


def parse_objective(raw: str) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """
    Parse a 171A/53A objective column value into [(control_id, subpart_path, odp_ref)].

    Three formats:
      Sub-part:  'AC-02d.01'           -> [('AC-2', 'd.1', None)]
                 'AC-06(01)(a)[01]'    -> [('AC-6(1)', 'a.1', None)]
                 'AC-07a.'             -> [('AC-7', 'a', None)]
                 'CM-06b'              -> [('CM-6', 'b', None)]
      ODP ref:   'IA-03_ODP[01]'       -> [('IA-3', None, 'ia-03_odp.01')]
                 'AC-05_ODP'           -> [('AC-5', None, 'ac-05_odp')]
      Special:   'Withdrawn' / bare    -> [] / [(ctrl, None, None)]
    """
    if not isinstance(raw, str):
        return []
    s = raw.strip()
    if not s or s.lower() == "nan" or s.lower() == "withdrawn":
        return []

    # ODP reference?
    m = _OBJ_ODP_RE.match(s)
    if m:
        fam, num_s, enh_s, idx_s = m.group(1), m.group(2), m.group(3), m.group(4)
        num = int(num_s)
        enh = int(enh_s) if enh_s else None
        idx = int(idx_s) if idx_s else None
        cid = f"{fam}-{num}"
        if enh is not None:
            cid += f"({enh})"
        odp_ref = _odp_to_oscal(fam, num, enh, idx)
        return [(cid, None, odp_ref)]

    # Sub-part or bare control/enhancement
    cm = _OBJ_CTRL_RE.match(s)
    if not cm:
        return []
    fam, num_s, enh_s = cm.group(1), cm.group(2), cm.group(3)
    cid = f"{fam}-{int(num_s)}"
    if enh_s is not None:
        cid += f"({int(enh_s)})"

    remainder = s[cm.end():].strip().rstrip(".")
    if not remainder:
        return [(cid, None, None)]

    # Remainder has sub-part info mixing letters, digits, dots, parens, brackets.
    # Strategy: split on structural delimiters (dot, paren-groups, bracket-groups)
    # to get an ordered sequence of tokens, then join with dots.
    toks: List[str] = []
    buf = remainder
    while buf:
        buf = buf.lstrip(". ")
        if not buf:
            break
        if buf[0] == "(":
            end = buf.find(")")
            inner = buf[1:end] if end > 0 else buf[1:]
            for t in _OBJ_SUFFIX_TOK.findall(inner.lower()):
                toks.append(str(int(t)) if t.isdigit() else t)
            buf = buf[end + 1:] if end > 0 else ""
        elif buf[0] == "[":
            end = buf.find("]")
            inner = buf[1:end] if end > 0 else buf[1:]
            for t in _OBJ_SUFFIX_TOK.findall(inner.lower()):
                toks.append(str(int(t)) if t.isdigit() else t)
            buf = buf[end + 1:] if end > 0 else ""
        else:
            m2 = re.match(r"([a-zA-Z]+|\d+)", buf)
            if m2:
                t = m2.group(1).lower()
                toks.append(str(int(t)) if t.isdigit() else t)
                buf = buf[m2.end():]
            else:
                buf = buf[1:]

    if not toks:
        return [(cid, None, None)]
    path = ".".join(toks)
    return [(cid, path, None)]


# ── OSCAL structured parts (raw catalog: catalog.groups[].controls[]) ──────────

_OSCAL_ID_RE = re.compile(r"^([a-z]{2,3})-(\d{1,3})(?:\.(\d{1,3}))?$")
_OSCAL_INSERT_RE = re.compile(r"insert:\s*param,\s*([a-z0-9_.\-]+)")
# objective ids append '-N' below the statement-part level: 'ac-2_obj.d.3-1'
_OBJ_LEAF_SUFFIX = re.compile(r"-\d+$")


def oscal_control_id(oscal_id: str) -> Optional[str]:
    """'ac-2' -> 'AC-2'; 'ac-2.1' -> 'AC-2(1)'.  None if not an OSCAL control id."""
    if not isinstance(oscal_id, str):
        return None
    m = _OSCAL_ID_RE.match(oscal_id.strip().lower())
    if not m:
        return None
    fam, num, enh = m.group(1).upper(), int(m.group(2)), m.group(3)
    cid = f"{fam}-{num}"
    if enh is not None:
        cid += f"({int(enh)})"
    return cid


def parse_oscal_parts(control: dict) -> List[dict]:
    """
    Walk a raw OSCAL control's statement and assessment-objective part trees.

    Returns a flat list of dicts:
      {kind: 'statement'|'objective', part_id, subpath, prose, odp_refs}

    subpath is the dotted lowercase path below the root part ('' for the root):
      'ac-2_smt.d.3'   -> 'd.3'
      'ac-2_obj.d.3-1' -> 'd.3'   (objective leaf indices '-N' collapse onto the
                                   statement sub-part they test; the full part_id
                                   keeps the finer granularity)
    odp_refs are the param ids referenced by '{{ insert: param, … }}' in prose.
    Never fabricates: parts without ids inherit the parent subpath.
    """
    out: List[dict] = []
    if not isinstance(control, dict):
        return out

    def walk(part: dict, root_id: str, kind: str, parent_subpath: str) -> None:
        pid = str(part.get("id") or "")
        if pid.startswith(root_id):
            sub = pid[len(root_id):].lstrip(".")
            subpath = _OBJ_LEAF_SUFFIX.sub("", sub) if kind == "objective" else sub
        else:
            subpath = parent_subpath
        prose = part.get("prose") or ""
        out.append({
            "kind": kind,
            "part_id": pid,
            "subpath": subpath,
            "prose": prose,
            "odp_refs": _OSCAL_INSERT_RE.findall(prose),
        })
        for child in part.get("parts", []) or []:
            walk(child, root_id, kind, subpath)

    for part in control.get("parts", []) or []:
        name = part.get("name")
        if name == "statement":
            walk(part, str(part.get("id") or ""), "statement", "")
        elif name == "assessment-objective":
            walk(part, str(part.get("id") or ""), "objective", "")
    return out


def parse_cui_sort_id(raw: str) -> Optional[Tuple[str, int]]:
    """
    Parse a CUI-overlay sort id 'FAMILY-CTRL-ENH-PART' into (control_id, part_ordinal).

    'AC-01-00-00' -> ('AC-1', 0)      base control, statement 0
    'AC-01-00-03' -> ('AC-1', 3)
    'AC-02-01-00' -> ('AC-2(1)', 0)   enhancement 1
    Returns None if the shape is unexpected.
    """
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split("-")
    if len(parts) != 4:
        return None
    fam, num, enh, part = parts
    try:
        cid = f"{fam.upper()}-{int(num)}"
        if int(enh) != 0:
            cid += f"({int(enh)})"
        return cid, int(part)
    except ValueError:
        return None
