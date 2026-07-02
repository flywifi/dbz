#!/usr/bin/env python3
"""
consensus_detector.py — cross-source agreement on third-party framework pairs.

Multiple independent mapping authorities each publish crosswalks from their own
framework to many others.  When several of them independently imply the SAME
third-party pair (e.g. a TSC criterion and an ISO control connected through an
SCF control, through a CCM control, AND through shared 800-53 sub-parts), that
agreement is strong derived evidence the two requirements overlap — worth
confirming against the authoritative texts and characterizing.

Acceptance-authority model (docs/standards-refresh-runbook.md): each owner's
crosswalk is the acceptance rule for THEIR framework only.  Consensus here is
OUR derived signal with citations to every voter — it never overrides any
owner's data and never makes one voter's mapping binding outside its scope.

Voter independence: CSA's two artifacts (CCM mapping sheet + OSCAL) count as
ONE voter; NIST-derived instruments (OLIR, CMMC crosswalk) are flagged with
shared ancestry.  Production audit evidence contributes AGGREGATE corroboration
counts only — provider-proprietary identifiers are never read into results
(CLAUDE.md publication hygiene).

SOC 2 comparability: consensus keys on AICPA TSC criteria ONLY (CC/A/C/PI/P
series).  Firm-local control ids (each audit firm/platform defines its own
SOC 2 control set) never key a consensus edge.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
_INGEST = _HERE.parent / "nist-catalog" / "ingestion"
for _p in (str(_INGEST), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # type: ignore
from spine_normalize import (  # type: ignore
    normalize_control_id,
    normalize_iso_id,
    normalize_pci_id,
    normalize_tsc_id,
)

REPO_ROOT = _HERE.parent.parent
SCF_XLSX = REPO_ROOT / "canonical-sources" / "source_data" / "Secure Controls Framework (SCF) - 2026.1.1.xlsx"
CCM_XLSX = REPO_ROOT / "canonical-sources" / "source_data" / "csa-star" / "CCMv4.0.13_Generated-at_2024-10-31.xlsx"
MASTER_JSON = REPO_ROOT / "canonical-sources" / "crosswalk_80053_master.json"
PCI_ISO_XLSX = REPO_ROOT / "canonical-sources" / "source_data" / "PCI 4.0 to ISO 27001_2022.xlsx"

# Canonical framework labels used for consensus keys.
FW_TSC = "SOC 2 (TSC)"
FW_ISO = "ISO 27001/2 (2022)"
FW_PCI = "PCI DSS"
FW_HIPAA = "HIPAA Security"
FW_CIS = "CIS v8"
FW_CSF = "NIST CSF 2.0"
FW_53 = "NIST 800-53"
FW_171 = "NIST SP 800-171"
FW_GDPR = "GDPR"
FW_CMMC = "CMMC 2.0"

_SPLIT = re.compile(r"[\n;,]+")
_HIPAA_RE = re.compile(r"\b164\.(\d{3})\b")
_CIS_RE = re.compile(r"^(\d{1,2})(?:\.(\d{1,2}))?$")
_CSF_RE = re.compile(r"^([A-Z]{2})\.([A-Z]{2})-(\d{1,2})$", re.IGNORECASE)
_171_RE = re.compile(r"^0?3\.(\d{1,2})\.(\d{1,2})")
_GDPR_RE = re.compile(r"^Art(?:icle)?\.?\s*(\d{1,3})(?:\s*[.(]\s*(\d{1,2})\)?)?", re.IGNORECASE)
_CMMC_RE = re.compile(r"^([A-Z]{2})\.L(\d)-(?:3\.)?[\d.]+|^([A-Z]{2})\.(\d)\.(\d{3})")


def _canon(fw: str, raw: str) -> Optional[str]:
    """Per-framework canonical id, or None when unrecognized — never guess.
    Firm-local SOC 2 ids fail normalize_tsc_id by design and are dropped."""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    if fw == FW_TSC:
        return normalize_tsc_id(s)
    if fw == FW_ISO:
        canon, _space = normalize_iso_id(s)
        return canon
    if fw == FW_PCI:
        return normalize_pci_id(s)
    if fw == FW_53:
        return normalize_control_id(s)
    if fw == FW_HIPAA:
        m = _HIPAA_RE.search(s)
        return f"164.{m.group(1)}" if m else None
    if fw == FW_CIS:
        m = _CIS_RE.match(s)
        if not m:
            return None
        return f"{int(m.group(1))}.{int(m.group(2))}" if m.group(2) else str(int(m.group(1)))
    if fw == FW_CSF:
        m = _CSF_RE.match(s)
        return f"{m.group(1).upper()}.{m.group(2).upper()}-{int(m.group(3))}" if m else None
    if fw == FW_171:
        m = _171_RE.match(s)
        return f"3.{int(m.group(1))}.{int(m.group(2))}" if m else None
    if fw == FW_GDPR:
        m = _GDPR_RE.match(s)
        if not m:
            return None
        base = f"Art {int(m.group(1))}"
        return f"{base}({int(m.group(2))})" if m.group(2) else base
    if fw == FW_CMMC:
        return s.upper() if _CMMC_RE.match(s.upper()) else None
    return None


def _pair_key(fw_a: str, id_a: str, fw_b: str, id_b: str) -> Tuple[str, str, str, str]:
    """Unordered canonical pair key (sorted by framework label, then id)."""
    if (fw_a, id_a) <= (fw_b, id_b):
        return fw_a, id_a, fw_b, id_b
    return fw_b, id_b, fw_a, id_a


class _Collector:
    def __init__(self):
        # key -> voter -> list of {derivation, strength, source}
        self.pairs: Dict[Tuple[str, str, str, str], Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))

    def add(self, fw_a: str, id_a: str, fw_b: str, id_b: str,
            voter: str, derivation: str, strength: Optional[str], source: str) -> None:
        if fw_a == fw_b:
            return
        key = _pair_key(fw_a, id_a, fw_b, id_b)
        self.pairs[key][voter].append(
            {"derivation": derivation, "strength": strength, "source": source})


def _row_pairs(collector: _Collector, per_fw: Dict[str, Set[str]],
               voter: str, derivation: str, strength: Optional[str], source: str) -> None:
    fws = sorted(per_fw)
    for i, fa in enumerate(fws):
        for fb in fws[i + 1:]:
            for a in sorted(per_fw[fa]):
                for b in sorted(per_fw[fb]):
                    collector.add(fa, a, fb, b, voter, derivation, strength, source)


# ── Voter: SCF (pivot = SCF control) ─────────────────────────────────────────

_SCF_COLS = [
    (FW_TSC, "TSC 2017"),                    # AICPA TSC 2017:2022 (used for SOC 2)
    (FW_ISO, "ISO\n27001\n2022"),
    (FW_ISO, "ISO\n27002\n2022"),
    (FW_PCI, "PCI DSS\n4.0.1"),
    (FW_CIS, "CIS\nCSC\n8.1"),
    (FW_CSF, "NIST\nCSF\n2.0"),
    (FW_53, "NIST\n800-53\nR5"),
    (FW_171, "NIST\n800-171\nR2"),
    (FW_HIPAA, "HIPAA Administrative Simplification"),
    (FW_GDPR, "GDPR"),
]


def _find_scf_col(cols: List[str], needle: str) -> Optional[str]:
    for c in cols:
        cn = str(c)
        if needle in cn:
            return c
    # tolerant: match ignoring whitespace variety
    flat = needle.replace("\n", " ")
    for c in cols:
        if flat in str(c).replace("\n", " "):
            return c
    return None


def collect_scf(collector: _Collector) -> int:
    if not SCF_XLSX.exists():
        return 0
    df = pd.read_excel(SCF_XLSX, sheet_name="SCF 2026.1")
    cols = list(df.columns)
    resolved: List[Tuple[str, str]] = []
    for fw, needle in _SCF_COLS:
        c = _find_scf_col(cols, needle)
        if c is not None and (fw, c) not in resolved:
            # avoid the TSC "used for SOC 2" col matching multiple AICPA cols:
            if fw == FW_TSC and "TSC" not in str(c):
                continue
            resolved.append((fw, c))
    fname = SCF_XLSX.name
    n = 0
    for i, row in df.iterrows():
        per_fw: Dict[str, Set[str]] = defaultdict(set)
        for fw, c in resolved:
            for tok in _SPLIT.split(str(row.get(c) or "")):
                cid = _canon(fw, tok)
                if cid:
                    per_fw[fw].add(cid)
        if len(per_fw) >= 2:
            _row_pairs(collector, per_fw, "scf", "pivot:scf", None, f"{fname}:row {i}")
            n += 1
    return n


# ── Voter: CSA (pivot = CCM control; mapping sheet with Gap Level) ───────────

# (framework label, column offset of the 'Control Mapping' column) — modern groups only.
_CCM_GROUPS = [
    (FW_TSC, 4),
    (FW_CIS, 10),
    (FW_ISO, 22),   # ISO/IEC 27001:2022, 27002:2022
    (FW_53, 25),
    (FW_CSF, 31),   # NIST CSF v2.0
    (FW_PCI, 37),   # PCI DSS v4.0
]


def collect_csa(collector: _Collector) -> int:
    if not CCM_XLSX.exists():
        return 0
    df = pd.read_excel(CCM_XLSX, sheet_name="Scope Applicability (Mappings)", header=None)
    fname = CCM_XLSX.name
    n = 0
    for i in range(3, len(df)):
        row = df.iloc[i]
        per_fw: Dict[str, Set[str]] = defaultdict(set)
        gap: Dict[str, str] = {}
        for fw, off in _CCM_GROUPS:
            cell = row.iloc[off] if off < len(row) else None
            for tok in _SPLIT.split(str(cell or "")):
                if fw == FW_ISO:
                    # CSA writes ISO refs as '27001: 5.1' / '27001: A.5.35'
                    tok = re.sub(r"^\s*2700[12]\s*:\s*", "", tok)
                cid = _canon(fw, tok)
                if cid:
                    per_fw[fw].add(cid)
            g = row.iloc[off + 1] if off + 1 < len(row) else None
            if g is not None and str(g).strip().lower() not in ("nan", ""):
                gap[fw] = str(g).strip()
        if len(per_fw) >= 2:
            strength = json.dumps(gap, sort_keys=True) if gap else None
            _row_pairs(collector, per_fw, "csa", "pivot:ccm", strength, f"{fname}:row {i}")
            n += 1
    return n


# ── Voter: HITRUST (pivot = HITRUST control; from grc.db hub table) ──────────

_HUB_LABELS = {
    "SOC 2": FW_TSC,
    "ISO 27001/2 (2022)": FW_ISO,
    "HIPAA Security": FW_HIPAA,
    "GDPR": FW_GDPR,
    "CIS CSC v8.0": FW_CIS,
    "NIST SP 800-171 r2": FW_171,
    "CMMC 2.0": FW_CMMC,
}


def collect_hitrust(collector: _Collector, conn) -> int:
    rows = conn.execute(
        "SELECT hitrust_id, framework, target_id FROM hitrust_hub ORDER BY hitrust_id, framework, target_id"
    ).fetchall()
    by_pivot: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    for hid, fw_label, tid in rows:
        fw = _HUB_LABELS.get(fw_label)
        if not fw:
            continue
        cid = _canon(fw, tid)
        if cid:
            by_pivot[hid][fw].add(cid)
    n = 0
    for hid in sorted(by_pivot):
        per_fw = by_pivot[hid]
        if len(per_fw) >= 2:
            _row_pairs(collector, per_fw, "hitrust", "pivot:hitrust", None,
                       f"hitrust_hub:{hid}")
            n += 1
    return n


# ── Voters: NIST-anchored directs (from grc.db projections) ──────────────────

def collect_nist_direct(collector: _Collector, conn) -> int:
    """OLIR (ISO<->800-53) and cmmc171 (CMMC/171<->800-53) — direct, source-stated
    or NIST-derived.  Flagged as shared-ancestry ('nist') voters downstream."""
    n = 0
    for nid, ctrl in conn.execute(
            "SELECT DISTINCT native_id, r5_control FROM framework_projection "
            "WHERE provenance='direct_olir' ORDER BY native_id, r5_control"):
        iso = _canon(FW_ISO, nid)
        c53 = _canon(FW_53, ctrl)
        if iso and c53:
            collector.add(FW_ISO, iso, FW_53, c53, "olir", "direct", None, "framework_projection:direct_olir")
            n += 1
    for fw_label, target_fw in (("CMMC 2.0", FW_CMMC), ("NIST SP 800-171 r2", FW_171)):
        for nid, ctrl, rel in conn.execute(
                "SELECT DISTINCT native_id, r5_control, relationship FROM framework_projection "
                "WHERE provenance='cmmc171' AND framework=? ORDER BY native_id, r5_control", (fw_label,)):
            cid = _canon(target_fw, nid)
            c53 = _canon(FW_53, ctrl)
            if cid and c53:
                collector.add(target_fw, cid, FW_53, c53, "cmmc171", "direct", rel,
                              "framework_projection:cmmc171")
                n += 1
    return n


# ── Voter: master crosswalk (pivot = 800-53) ─────────────────────────────────

_MASTER_FW = {
    "SOC 2 TSC": FW_TSC,
    "ISO 27001:2022": FW_ISO,
    "NIST CSF v2.0": FW_CSF,
    "PCI DSS v4.0": FW_PCI,
    "HIPAA (45 CFR)": FW_HIPAA,
    "NIST 800-171r3": FW_171,
}


def collect_master(collector: _Collector) -> int:
    if not MASTER_JSON.exists():
        return 0
    data = json.loads(MASTER_JSON.read_text(encoding="utf-8"))
    n = 0
    for nist_id in sorted(data.get("map", {})):
        fws = data["map"][nist_id]
        c53 = _canon(FW_53, nist_id)
        if not c53:
            continue
        per_fw: Dict[str, Set[str]] = defaultdict(set)
        per_fw[FW_53].add(c53)
        for label, ids in fws.items():
            fw = _MASTER_FW.get(label)
            if not fw:
                continue
            for tok in (ids if isinstance(ids, list) else [ids]):
                cid = _canon(fw, str(tok))
                if cid:
                    per_fw[fw].add(cid)
        if len(per_fw) >= 2:
            _row_pairs(collector, per_fw, "master", "pivot:800-53", None,
                       f"crosswalk_80053_master.json:{nist_id}")
            n += 1
    return n


# ── Voter: PCI<->ISO direct file ─────────────────────────────────────────────

_PCI_LEAD = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){0,3})\b")
_ISO_LEAD = re.compile(r"^(A?\.?\s*\d{1,2}(?:\.\d{1,2}){0,2})\b")


def collect_pci_iso(collector: _Collector) -> int:
    """Rows: col0 = 'PCI id + title', col2 = newline list of 'ISO id + title'."""
    if not PCI_ISO_XLSX.exists():
        return 0
    df = pd.read_excel(PCI_ISO_XLSX, sheet_name=0, header=None)
    fname = PCI_ISO_XLSX.name
    n = 0
    for i in range(len(df)):
        row = [str(x).strip() for x in df.iloc[i].tolist()]
        if not row:
            continue
        m = _PCI_LEAD.match(row[0])
        pci = _canon(FW_PCI, m.group(1)) if m else None
        if not pci:
            continue
        for cell in row[1:]:
            for line in cell.split("\n"):
                lm = _ISO_LEAD.match(line.strip())
                iso = _canon(FW_ISO, lm.group(1)) if lm else None
                if iso:
                    collector.add(FW_PCI, pci, FW_ISO, iso, "pci_iso", "direct", None,
                                  f"{fname}:row {i}")
                    n += 1
    return n


# ── Aggregate production corroboration (NO proprietary ids read into results) ─

def production_support(conn) -> Dict[Tuple[str, str, str, str], int]:
    """Pair co-occurrence counts from production audit evidence.  Only pairs
    where BOTH sides carry public canonical ids contribute; provider-proprietary
    identifiers never leave this function."""
    fw_map = {"ISO 27001/2 (2022)": FW_ISO, "PCI DSS v4.0": FW_PCI}
    by_pivot: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    for er_id, fw_label, nid in conn.execute(
            "SELECT er_id, framework, native_id FROM er_mappings ORDER BY er_id"):
        fw = fw_map.get(fw_label)
        if not fw:
            continue
        cid = _canon(fw, nid)
        if cid:
            by_pivot[er_id][fw].add(cid)
    counts: Dict[Tuple[str, str, str, str], int] = defaultdict(int)
    for _pivot, per_fw in by_pivot.items():
        fws = sorted(per_fw)
        for i, fa in enumerate(fws):
            for fb in fws[i + 1:]:
                for a in sorted(per_fw[fa]):
                    for b in sorted(per_fw[fb]):
                        counts[_pair_key(fa, a, fb, b)] += 1
    return dict(counts)


# ── Characterization (strong pairs only) ──────────────────────────────────────

_PROJ_LABEL = {FW_TSC: "SOC 2", FW_ISO: "ISO 27001/2 (2022)", FW_HIPAA: "HIPAA Security",
               FW_GDPR: "GDPR", FW_CIS: "CIS CSC v8.0", FW_171: "NIST SP 800-171 r2",
               FW_CMMC: "CMMC 2.0"}


def _atoms(conn, fw: str, native: str) -> Set[str]:
    """Spine sub-part footprint of one native id (projection-known frameworks only)."""
    if fw == FW_53:
        ctrl = native
        out = {r[0] for r in conn.execute(
            "SELECT subpart_id FROM nist_subparts WHERE r5_control=? AND path<>''", (ctrl,))}
        return out or {ctrl}
    label = _PROJ_LABEL.get(fw)
    if not label:
        return set()
    # Projection natives are often FULLER than the canonical consensus key:
    # 171 -> '3.1.10[a]', HIPAA -> '§ 164.308(a)(1)(i)', TSC -> 'AICPA 2017 CC6.1'.
    if fw == FW_171:
        where, params = ("(native_id=? OR native_id LIKE ?)", (native, native + "[%"))
    elif fw == FW_HIPAA:
        where, params = ("native_id LIKE ?", (f"%{native}%",))
    elif fw == FW_TSC:
        where, params = ("(native_id=? OR native_id=?)", (native, f"AICPA 2017 {native}"))
    else:
        where, params = ("native_id=?", (native,))
    out: Set[str] = set()
    if True:
        for r5c, sp in conn.execute(
                f"SELECT r5_control, r5_subpart FROM framework_projection "
                f"WHERE framework=? AND {where}", (label, *params)):
            if sp:
                out.add(sp)
            else:
                out.add(r5c)
                for (s,) in conn.execute(
                        "SELECT subpart_id FROM nist_subparts WHERE r5_control=? AND path<>''", (r5c,)):
                    out.add(s)
    return out


def characterize(conn, fw_a: str, id_a: str, fw_b: str, id_b: str) -> dict:
    a = _atoms(conn, fw_a, id_a)
    b = _atoms(conn, fw_b, id_b)
    shared = sorted(a & b)
    if not a or not b:
        extent = "no_spine_footprint"
    elif not shared:
        extent = "atoms_disjoint"
    elif a == b:
        extent = "equal"
    elif a <= b:
        extent = "a_subset_b"
    elif b <= a:
        extent = "b_subset_a"
    else:
        extent = "intersect"
    return {"extent": extent, "shared_atoms_count": len(shared),
            "shared_atoms": shared[:25]}


# ── Entry point ───────────────────────────────────────────────────────────────

def detect(conn) -> Tuple[List[dict], dict]:
    """Run all voters; return (consensus_rows, stats)."""
    import uncertainty as UNC  # type: ignore

    col = _Collector()
    stats = {
        "scf_rows": collect_scf(col),
        "csa_rows": collect_csa(col),
        "hitrust_pivots": collect_hitrust(col, conn),
        "nist_direct_edges": collect_nist_direct(col, conn),
        "master_rows": collect_master(col),
        "pci_iso_edges": collect_pci_iso(col),
    }
    support = production_support(conn)

    rows: List[dict] = []
    tier_counts = {"strong": 0, "moderate": 0, "single": 0}
    for key in sorted(col.pairs):
        fw_a, id_a, fw_b, id_b = key
        voters = col.pairs[key]
        names = sorted(voters)
        votes = len(names)
        nist_ancestry = int("olir" in names and "cmmc171" in names)
        tier = "strong" if votes >= 3 else ("moderate" if votes == 2 else "single")
        tier_counts[tier] += 1
        row = {
            "fw_a": fw_a, "native_a": id_a, "fw_b": fw_b, "native_b": id_b,
            "votes": votes, "tier": tier,
            "voters": json.dumps(names),
            "evidence": json.dumps({v: voters[v][:5] for v in names}, sort_keys=True),
            "production_support": support.get(key, 0),
            "nist_ancestry_overlap": nist_ancestry,
            "extent": None, "shared_atoms_count": None, "shared_atoms": None,
            "text_confirmation": None, "uncertainty_id": None,
            "needs_confirmation": 1,
        }
        if tier == "strong":
            ch = characterize(conn, fw_a, id_a, fw_b, id_b)
            row.update({"extent": ch["extent"],
                        "shared_atoms_count": ch["shared_atoms_count"],
                        "shared_atoms": json.dumps(ch["shared_atoms"])})
            row["text_confirmation"] = (
                "pending_licensed_artifact" if FW_ISO in (fw_a, fw_b)
                else "texts_on_file")
            row["uncertainty_id"] = UNC.uncertainty_id(
                "consensus", fw_a=fw_a, native_a=id_a, fw_b=fw_b, native_b=id_b)
        rows.append(row)

    stats["pairs"] = len(rows)
    stats["tiers"] = tier_counts
    stats["with_production_support"] = sum(1 for r in rows if r["production_support"])
    return rows, stats


if __name__ == "__main__":
    import sqlite3
    db = REPO_ROOT / "cross-mapping" / "output" / "grc.db"
    conn = sqlite3.connect(str(db))
    rows, stats = detect(conn)
    print(json.dumps(stats, indent=2))
    strong = [r for r in rows if r["tier"] == "strong"]
    print(f"strong pairs: {len(strong)}; sample:")
    for r in strong[:10]:
        print(f"  {r['fw_a']} {r['native_a']} <-> {r['fw_b']} {r['native_b']} "
              f"votes={r['votes']} voters={r['voters']} extent={r['extent']}")
    conn.close()
