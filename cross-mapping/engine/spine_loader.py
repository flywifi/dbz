"""
spine_loader.py — load the overlap spine tables into grc.db.

Phase 1 tables:
  nist_subparts   authoritative sub-part inventory (denominators)
  cci_bridge      CCI <-> r5 sub-part (from the DISA CCI list)
  control_odps    control parameters rekeyed to canonical OSCAL ODP ids
  disa_ccis       populated from the CCI xlsx (the enrichment table dbz_query reads)

Later phases add framework_projection, hitrust_hub, odp_values, overlap_matrix.

All column names are read from source_manifest.json via config.py (never hardcoded).
Deterministic: every returned row list is sorted before the caller inserts it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
_INGEST = _HERE.parent / "nist-catalog" / "ingestion"
for _p in (str(_INGEST), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # provided via requirements.txt
from config import source_path, sheet_name, header_row, col  # type: ignore
from spine_normalize import (  # type: ignore
    normalize_control_id,
    parse_cci_index,
    parse_hitrust_ref,
    canon_subpart,
)

REPO_ROOT = _HERE.parent.parent
OSCAL_PATH = REPO_ROOT / "canonical-sources" / "oscal_v5.2.0_full_extract.json"

_INSERT_RE = re.compile(r"insert:\s*param,\s*([a-z0-9_.\-]+)")


def _read_source_df(src: str) -> "pd.DataFrame":
    hr = header_row(src)
    df = pd.read_excel(
        source_path(src),
        sheet_name=sheet_name(src),
        skiprows=list(range(hr)) if hr else None,
    )
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ── cci_bridge + disa_ccis ─────────────────────────────────────────────────────

def load_cci_bridge(catalog_ids: Set[str]) -> Tuple[List[dict], List[dict], dict]:
    """
    Parse the DISA CCI list into cci_bridge rows and disa_ccis rows.

    Returns (cci_bridge_rows, disa_cci_rows, stats).  cci_bridge maps a CCI to an
    r5 control and (where the source gives a clean statement part) an r5 sub-part.
    Rows whose control is not present in the r5 catalog are dropped (withdrawn).
    """
    src = "disa-cci-list"
    fname = source_path(src).name
    df = _read_source_df(src)

    cci_col = col(src, "cci_id")
    ref_col = col(src, "nist_r4_ref")
    def_col = col(src, "definition")
    status_col = col(src, "status")

    seen_bridge: Set[Tuple[str, str, str]] = set()
    bridge_rows: List[dict] = []
    # per-cci aggregation for the disa_ccis enrichment table
    agg: Dict[str, dict] = {}
    dropped_withdrawn = 0

    for i, row in enumerate(df.itertuples(index=False), start=0):
        rowd = dict(zip(df.columns, row))
        cci = str(rowd.get(cci_col, "")).strip()
        if not cci or cci.lower() == "nan":
            continue
        ref = str(rowd.get(ref_col, "")).strip()
        definition = str(rowd.get(def_col, "")).strip()
        status = str(rowd.get(status_col, "")).strip()

        entry = agg.setdefault(cci, {
            "cci_id": cci, "definition": definition, "status": status,
            "r4_refs": set(), "r5_controls": set(),
        })
        if definition and definition.lower() != "nan" and not entry["definition"]:
            entry["definition"] = definition
        if ref and ref.lower() != "nan":
            entry["r4_refs"].add(ref)

        for ctrl, subpath in parse_cci_index(ref):
            if ctrl not in catalog_ids:
                dropped_withdrawn += 1
                continue
            entry["r5_controls"].add(ctrl)
            subpart = canon_subpart(ctrl, subpath)  # None for whole-control
            key = (cci, ctrl, subpart or "")
            if key in seen_bridge:
                continue
            seen_bridge.add(key)
            bridge_rows.append({
                "cci_id": cci,
                "r5_control": ctrl,
                "r5_subpart": subpart,
                "r4_ref_raw": ref,
                "source_file": fname,
                "source_row": i,
            })

    disa_rows: List[dict] = []
    for cci, e in agg.items():
        if not e["r5_controls"]:
            continue  # only maps to withdrawn controls
        disa_rows.append({
            "cci_id": cci,
            "definition": e["definition"],
            "type": "",
            "status": e["status"],
            "nist_rev4_refs": json.dumps(sorted(e["r4_refs"])),
            "nist_rev5_refs": json.dumps(sorted(e["r5_controls"])),
            "fetched_at": "",
        })

    bridge_rows.sort(key=lambda r: (r["cci_id"], r["r5_control"], r["r5_subpart"] or ""))
    disa_rows.sort(key=lambda r: r["cci_id"])
    stats = {
        "cci_rows": len(df),
        "distinct_cci": len(agg),
        "bridge_rows": len(bridge_rows),
        "dropped_withdrawn": dropped_withdrawn,
        "distinct_controls": len({r["r5_control"] for r in bridge_rows}),
    }
    return bridge_rows, disa_rows, stats


# ── nist_subparts ──────────────────────────────────────────────────────────────

def load_nist_subparts(catalog_ids: Set[str], cci_bridge_rows: List[dict]) -> List[dict]:
    """
    Build the sub-part inventory: one whole-control row per catalog control/enhancement,
    plus one row per distinct statement-part sub-part discovered in the CCI bridge.
    Each row traces to a source; nothing is fabricated.
    """
    rows: Dict[str, dict] = {}
    for cid in sorted(catalog_ids):
        r5c = normalize_control_id(cid) or cid
        rows[cid] = {
            "subpart_id": cid,
            "r5_control": r5c,
            "path": "",
            "ordinal": 0,
            "source_file": "catalog",
            "source_sheet": "",
            "source_row": -1,
        }
    for b in cci_bridge_rows:
        sp = b["r5_subpart"]
        if not sp or sp in rows:
            continue
        # path is everything after the control id + a space
        path = sp[len(b["r5_control"]):].strip()
        rows[sp] = {
            "subpart_id": sp,
            "r5_control": b["r5_control"],
            "path": path,
            "ordinal": 0,
            "source_file": b["source_file"],
            "source_sheet": "U_CCI_List",
            "source_row": b["source_row"],
        }
    out = list(rows.values())
    out.sort(key=lambda r: (r["r5_control"], r["path"], r["subpart_id"]))
    return out


# ── control_odps (rekey positional params to canonical OSCAL ODP ids) ───────────

def _oscal_key(control_id: str) -> str:
    """AC-2 -> ac-2 ; AC-2(1) -> ac-2.1 (OSCAL flat-key convention)."""
    return control_id.lower().replace("(", ".").replace(")", "")


def _load_oscal_inserts() -> Dict[str, List[str]]:
    """control_id -> ordered list of param/ODP ids referenced in its statement."""
    if not OSCAL_PATH.exists():
        return {}
    data = json.loads(OSCAL_PATH.read_text(encoding="utf-8"))
    out: Dict[str, List[str]] = {}
    for key, rec in data.items():
        if not isinstance(rec, dict):
            continue
        stmt = rec.get("statement", "") or ""
        ids: List[str] = []
        for pid in _INSERT_RE.findall(stmt):
            if pid not in ids:
                ids.append(pid)
        if ids:
            out[key] = ids
    return out


def load_control_odps(param_rows: List[dict]) -> Tuple[List[dict], dict]:
    """
    Rekey the catalog's positional parameters (param-1, param-2, …) to the canonical
    OSCAL ODP id (ac-02_odp.01, …) by zipping in document order when the counts match.
    When they don't match, fall back to a stable per-control id and flag the basis.
    """
    oscal = _load_oscal_inserts()
    by_ctrl: Dict[str, List[dict]] = {}
    for p in param_rows:
        by_ctrl.setdefault(p["control_id"], []).append(p)

    rows: List[dict] = []
    matched = fallback = 0
    for cid, params in by_ctrl.items():
        params = sorted(params, key=lambda p: (p.get("position") if p.get("position") is not None else 0))
        inserts = oscal.get(_oscal_key(cid), [])
        use_oscal = len(inserts) == len(params) and len(params) > 0
        if use_oscal:
            matched += 1
        else:
            fallback += 1
        for i, p in enumerate(params):
            if use_oscal:
                odp_id = inserts[i]
                basis = "oscal_positional_zip"
            else:
                odp_id = f"{_oscal_key(cid)}_param.{i + 1:02d}"
                basis = "positional_fallback"
            rows.append({
                "odp_id": odp_id,
                "control_id": cid,
                "r5_subpart": None,
                "type": p.get("type", ""),
                "label": p.get("label", ""),
                "ordinal": i + 1,
                "rekey_basis": basis,
            })
    rows.sort(key=lambda r: (r["control_id"], r["ordinal"]))
    stats = {
        "controls_with_params": len(by_ctrl),
        "odp_rows": len(rows),
        "rekeyed_from_oscal": matched,
        "positional_fallback": fallback,
    }
    return rows, stats


# ── framework_projection: NIST 800-53 <-> ISO 27001 (OLIR, Phase 2) ─────────────

ISO_FRAMEWORK = "ISO 27001/2 (2022)"


def _norm_header(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _find_col(columns: List[str], canonical: str) -> Optional[str]:
    """Match a manifest-declared column name to a real df column, tolerating
    internal newlines / whitespace variance."""
    target = _norm_header(canonical)
    for c in columns:
        if _norm_header(c) == target:
            return c
    for c in columns:  # prefix fallback
        if _norm_header(c).startswith(target[:20]):
            return c
    return None


def _projection_row(**kw) -> dict:
    """A framework_projection row with defaults filled in."""
    row = {
        "framework": kw["framework"],
        "native_id": kw["native_id"],
        "r5_control": kw["r5_control"],
        "r5_subpart": kw.get("r5_subpart"),
        "cci_id": kw.get("cci_id"),
        "odp_id": kw.get("odp_id"),
        "relationship": kw.get("relationship", "unspecified"),
        "relationship_basis": kw.get("relationship_basis", "derived_cardinality"),
        "granularity": kw["granularity"],
        "provenance": kw["provenance"],
        "confidence": kw["confidence"],
        "hop_count": kw.get("hop_count", 1),
        "needs_confirmation": int(kw.get("needs_confirmation", 0)),
        "source_file": kw.get("source_file", ""),
        "source_sheet": kw.get("source_sheet", ""),
        "source_row": kw.get("source_row", -1),
    }
    return row


def load_olir_projection(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """
    Project ISO 27001:2022 clauses onto r5 controls using the official NIST OLIR
    crosswalk.  The OLIR `Relationship` column is empty in this source, so edges are
    emitted as control-level with relationship='unspecified' (derive_iso_relationships
    fills it structurally).  provenance='direct_olir', confidence 0.85.
    """
    src = "nist-800-53r5-to-iso-27001-olir"
    path = source_path(src)
    fname = path.name
    nid_role = col(src, "nist_id")
    iso_role = col(src, "iso_id")

    xl = pd.ExcelFile(path)
    sheets = [s for s in xl.sheet_names if s.strip().lower() != "definitions"]

    edges: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    unresolved: Set[str] = set()
    rows_read = 0
    for sh in sheets:
        df = pd.read_excel(path, sheet_name=sh)
        cols = list(df.columns)
        nid_c = _find_col(cols, nid_role)
        iso_c = _find_col(cols, iso_role)
        if nid_c is None or iso_c is None:
            continue
        for i, rec in enumerate(df.itertuples(index=False), start=0):
            rowd = dict(zip(df.columns, rec))
            rows_read += 1
            focal_raw = str(rowd.get(nid_c, "")).strip()
            iso_id = str(rowd.get(iso_c, "")).strip()
            if not focal_raw or focal_raw.lower() == "nan" or not iso_id or iso_id.lower() == "nan":
                continue
            focal = normalize_control_id(focal_raw)
            if not focal:
                continue
            if focal not in catalog_ids:
                unresolved.add(focal_raw)
                continue
            key = (iso_id, focal)
            if key in seen:
                continue
            seen.add(key)
            edges.append(_projection_row(
                framework=ISO_FRAMEWORK, native_id=iso_id, r5_control=focal,
                relationship="unspecified", relationship_basis="derived_cardinality",
                granularity="control", provenance="direct_olir", confidence=0.85,
                source_file=fname, source_sheet=sh, source_row=i,
            ))

    derive_iso_relationships(edges)
    edges.sort(key=lambda r: (r["native_id"], r["r5_control"]))
    stats = {
        "rows_read": rows_read,
        "edges": len(edges),
        "unresolved_focal": len(unresolved),
        "unresolved_sample": sorted(unresolved)[:10],
    }
    return edges, stats


def derive_iso_relationships(edges: List[dict]) -> None:
    """
    Fill `relationship` on each ISO<->NIST edge from fan-out cardinality (the OLIR
    source states none).  From the ISO clause's perspective:
      1:1                       -> equal
      clause -> 1 control that maps to many clauses  -> subset  (clause ⊆ control)
      clause -> many controls                        -> superset (clause spans controls)
      many:many                                      -> intersect
    Always stamped relationship_basis='derived_cardinality'.
    """
    iso_to_ctrls: Dict[str, Set[str]] = {}
    ctrl_to_isos: Dict[str, Set[str]] = {}
    for e in edges:
        iso_to_ctrls.setdefault(e["native_id"], set()).add(e["r5_control"])
        ctrl_to_isos.setdefault(e["r5_control"], set()).add(e["native_id"])
    for e in edges:
        n_ctrls = len(iso_to_ctrls[e["native_id"]])
        n_isos = len(ctrl_to_isos[e["r5_control"]])
        if n_ctrls == 1 and n_isos == 1:
            rel = "equal"
        elif n_ctrls == 1 and n_isos > 1:
            rel = "subset"
        elif n_ctrls > 1 and n_isos == 1:
            rel = "superset"
        else:
            rel = "intersect"
        e["relationship"] = rel
        e["relationship_basis"] = "derived_cardinality"


# ── framework_projection: HITRUST hub for commercial frameworks (Phase 3) ───────

# role in the manifest -> canonical framework label projected into the spine.
# 'nist_53r5_id' is the spine anchor (not a projected framework); 'hitrust_id' is
# the pivot key.  Everything else becomes a framework whose native ids co-occur with
# the row's NIST r5 sub-parts (hub co-membership, confidence 0.65, hop 2).
_HUB_FRAMEWORKS = {
    "tsc_id": "SOC 2",
    "iso_27001_2022_id": "ISO 27001/2 (2022)",
    "hipaa_security_id": "HIPAA Security",
    "gdpr_id": "GDPR",
    "cmmc_v2_id": "CMMC 2.0",
    "fedramp_r5_id": "FedRAMP r5",
    "cis_v8_id": "CIS CSC v8.0",
    "nist_171r2_id": "NIST SP 800-171 r2",
}

_SPLIT_RE = re.compile(r"[\n;]+")


def _split_cell(cell) -> List[str]:
    if cell is None:
        return []
    s = str(cell).strip()
    if not s or s.lower() == "nan":
        return []
    return [tok.strip() for tok in _SPLIT_RE.split(s) if tok.strip()]


def load_hitrust_hub(catalog_ids: Set[str]) -> Tuple[List[dict], List[dict], dict]:
    """
    Load the HITRUST cross-reference into (hub_rows, projection_edges, stats).

    For each HITRUST control row we parse the NIST r5 cell into r5 sub-parts, then
    connect every other framework's native ids in the same row to those sub-parts
    (co-membership).  Edges are provenance='hitrust_hub', confidence 0.65, hop 2,
    needs_confirmation=1.  Every hub target id is also written to hitrust_hub for the
    audit trail.
    """
    src = "hitrust-csf-cross-reference"
    fname = source_path(src).name
    df = _read_source_df(src)
    cols = list(df.columns)

    hit_c = _find_col(cols, col(src, "hitrust_id"))
    nist_c = _find_col(cols, col(src, "nist_53r5_id"))
    fw_cols = {}
    for role, label in _HUB_FRAMEWORKS.items():
        try:
            actual = _find_col(cols, col(src, role))
        except Exception:
            actual = None
        if actual:
            fw_cols[actual] = label

    hub_rows: List[dict] = []
    edges: List[dict] = []
    seen_edge: Set[Tuple[str, str, str]] = set()
    nist_parse_incomplete = 0
    nist_tokens = 0

    for i, rec in enumerate(df.itertuples(index=False), start=0):
        rowd = dict(zip(df.columns, rec))
        hitrust_id = str(rowd.get(hit_c, "")).strip()
        if not hitrust_id or hitrust_id.lower() == "nan":
            continue

        # r5 sub-parts for this HITRUST control
        subparts: List[Tuple[str, Optional[str]]] = []  # (r5_control, r5_subpart)
        for tok in _split_cell(rowd.get(nist_c)):
            nist_tokens += 1
            parsed = parse_hitrust_ref(tok)
            if not parsed:
                nist_parse_incomplete += 1
                continue
            for ctrl, subpath in parsed:
                if ctrl not in catalog_ids:
                    continue
                subparts.append((ctrl, canon_subpart(ctrl, subpath)))

        for actual_col, label in fw_cols.items():
            for target_id in _split_cell(rowd.get(actual_col)):
                hub_rows.append({
                    "hitrust_id": hitrust_id, "framework": label,
                    "target_id": target_id, "source_row": i,
                })
                for r5_control, r5_subpart in subparts:
                    key = (label, target_id, r5_subpart or r5_control)
                    if key in seen_edge:
                        continue
                    seen_edge.add(key)
                    edges.append(_projection_row(
                        framework=label, native_id=target_id, r5_control=r5_control,
                        r5_subpart=r5_subpart,
                        relationship="intersect", relationship_basis="co_membership",
                        granularity="subpart" if r5_subpart else "control",
                        provenance="hitrust_hub", confidence=0.65, hop_count=2,
                        needs_confirmation=1,
                        source_file=fname, source_sheet=_read_sheet_name(src), source_row=i,
                    ))

    hub_rows.sort(key=lambda r: (r["framework"], r["target_id"], r["hitrust_id"]))
    edges.sort(key=lambda r: (r["framework"], r["native_id"], r["r5_control"], r["r5_subpart"] or ""))
    stats = {
        "hub_rows": len(hub_rows),
        "edges": len(edges),
        "frameworks": sorted({e["framework"] for e in edges}),
        "nist_tokens": nist_tokens,
        "nist_parse_incomplete": nist_parse_incomplete,
    }
    return hub_rows, edges, stats


def _read_sheet_name(src: str) -> str:
    try:
        return sheet_name(src)
    except Exception:
        return ""
