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
