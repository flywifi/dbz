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
    normalize_hipaa_citation,
    normalize_iso_id,
    normalize_pci_id,
    normalize_tsc_id,
    oscal_control_id,
    parse_cci_index,
    parse_hitrust_ref,
    parse_objective,
    parse_oscal_parts,
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
            iso_raw = str(rowd.get(iso_c, "")).strip()
            if not focal_raw or focal_raw.lower() == "nan" or not iso_raw or iso_raw.lower() == "nan":
                continue
            focal = normalize_control_id(focal_raw)
            if not focal:
                continue
            if focal not in catalog_ids:
                unresolved.add(focal_raw)
                continue
            # Canonicalize the ISO citation (A-prefixed Annex A / bare ISMS clause);
            # keep the raw id when the normalizer can't classify it (never guess).
            iso_canon, _iso_space = normalize_iso_id(iso_raw)
            iso_id = iso_canon if iso_canon else iso_raw
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


def derive_relationships(edges: List[dict]) -> None:
    """
    Fill `relationship` on each native<->NIST edge from fan-out cardinality (for
    sources that state no relationship).  From the native id's perspective:
      1:1                                            -> equal
      native -> 1 control that maps to many natives  -> subset  (native ⊆ control)
      native -> many controls                        -> superset (native spans controls)
      many:many                                      -> intersect
    Always stamped relationship_basis='derived_cardinality'.
    """
    nat_to_ctrls: Dict[str, Set[str]] = {}
    ctrl_to_nats: Dict[str, Set[str]] = {}
    for e in edges:
        nat_to_ctrls.setdefault(e["native_id"], set()).add(e["r5_control"])
        ctrl_to_nats.setdefault(e["r5_control"], set()).add(e["native_id"])
    for e in edges:
        n_ctrls = len(nat_to_ctrls[e["native_id"]])
        n_nats = len(ctrl_to_nats[e["r5_control"]])
        if n_ctrls == 1 and n_nats == 1:
            rel = "equal"
        elif n_ctrls == 1 and n_nats > 1:
            rel = "subset"
        elif n_ctrls > 1 and n_nats == 1:
            rel = "superset"
        else:
            rel = "intersect"
        e["relationship"] = rel
        e["relationship_basis"] = "derived_cardinality"


def derive_iso_relationships(edges: List[dict]) -> None:
    """Kept name for the OLIR ISO loader; the logic is framework-generic."""
    derive_relationships(edges)


# ── framework_projection: CPRT direct projections (Phase 19) ────────────────────

def _load_cprt_export(src: str) -> dict:
    """Read a CPRT JSON export registered in the manifest; returns the
    response.elements block {documents, relationship_types, elements, relationships}."""
    with open(source_path(src), encoding="utf-8") as f:
        return json.load(f)["response"]["elements"]


def _cprt_53_projection(src: str, framework: str, provenance: str,
                        native_canon, dest_doc_prefix: str,
                        catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """Generic CPRT external_reference -> 800-53 projection (171r3, 172r3).

    NIST's own CPRT datasets state requirement -> 800-53 control mappings as
    external_reference relationships; edges are NIST-stated, control-level,
    confidence 0.85 (nist_stated tier), needs_confirmation=0.  Relationships are
    filled by fan-out cardinality (the dataset states none)."""
    data = _load_cprt_export(src)
    fname = source_path(src).name
    edges: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    rels_seen = dropped_dest = dropped_native = 0
    for r in data.get("relationships", []):
        if r.get("relationship_identifier") != "external_reference":
            continue
        if not str(r.get("dest_doc_identifier", "")).startswith(dest_doc_prefix):
            continue
        rels_seen += 1
        native = native_canon(str(r.get("source_element_identifier", "")).strip())
        if not native:
            dropped_native += 1
            continue
        ctrl = normalize_control_id(str(r.get("dest_element_identifier", "")).strip())
        if not ctrl or ctrl not in catalog_ids:
            dropped_dest += 1
            continue
        key = (native, ctrl)
        if key in seen:
            continue
        seen.add(key)
        edges.append(_projection_row(
            framework=framework, native_id=native, r5_control=ctrl,
            granularity="control", provenance=provenance, confidence=0.85,
            needs_confirmation=0, source_file=fname, source_row=-1,
        ))
    derive_relationships(edges)
    edges.sort(key=lambda r: (r["native_id"], r["r5_control"]))
    return edges, {"relationships_seen": rels_seen, "edges": len(edges),
                   "dropped_dest": dropped_dest, "dropped_native": dropped_native}


def _canon_171r3_native(raw: str) -> Optional[str]:
    """'03.15.01' -> '3.15.1' (the unpadded canonical 171 form used by the
    consensus keys and the master crosswalk's 171r3 column)."""
    m = re.match(r"^0?3\.(\d{1,2})\.(\d{1,2})$", raw)
    return f"3.{int(m.group(1))}.{int(m.group(2))}" if m else None


def load_171r3_projection(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """NIST SP 800-171 r3 requirements -> 800-53 r5 controls, from the official
    CPRT dataset's external_reference relationships (dest doc SP_800_53_5_1_1;
    ids stable into the r5.2.0 catalog)."""
    return _cprt_53_projection(
        "cprt-sp800-171r3", "NIST SP 800-171 r3", "direct_cprt_171r3",
        _canon_171r3_native, "SP_800_53", catalog_ids)


def load_172r3_projection(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """NIST SP 800-172 r3 enhanced security requirements -> 800-53 r5.2.0 controls
    (official CPRT dataset; dest doc SP_800_53_5_2_0)."""
    def canon(raw: str) -> Optional[str]:
        return raw if re.match(r"^\d{1,2}\.\d{1,2}[Ee]?$|^0?3\.\d{1,2}\.\d{1,2}[Ee]?$", raw) else None
    return _cprt_53_projection(
        "cprt-sp800-172r3", "NIST SP 800-172 r3", "direct_cprt_172r3",
        canon, "SP_800_53", catalog_ids)


def _iter_graph_external_rels(graphs: dict):
    """Yield (host_element_identifier, external_relationship_dict) from a CPRT
    graph-harvest artifact's `graphs` block."""
    def walk(o, host):
        if isinstance(o, dict):
            here = o.get("elementIdentifier") or host
            for ext in o.get("externalRelationships") or []:
                yield here, ext
            for v in o.values():
                yield from walk(v, here)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v, host)
    yield from walk(graphs, None)


def _load_graph_artifact(src: str) -> dict:
    with open(source_path(src), encoding="utf-8") as f:
        return json.load(f)["graphs"]


_OLIR_800_66_53 = "SP-800-66-Rev-2-to-SP-800-53-Rev-5.1.1"
_OLIR_CSF2_53 = "Cybersecurity-Framework-v2.0-to-SP-800-53-Rev-5-2-0"
_OLIR_PCI_CSF2 = ("Payment-Card-Industry-Data-Security-Standards-(PCI-DSS)"
                  "-4.0.1-to-Cybersecurity-Framework-v2.0")
_OLIR_ISO_CSF2 = "ISO/IEC-27001:2022-to-Cybersecurity-Framework-v2.0"
_OLIR_CSF2_171R3 = "CSF 2.0 to SP 800-171 Rev 3"
_OLIR_CCM_CSF2 = "Cloud-Controls-Matrix-(CCM)-Version-4.0-to-Cybersecurity-Framework-v2.0"
_OLIR_SCF_CSF2 = "NIST CSF 2.0 To Secure Controls Framework (SCF)"
_CSF2_SUBCAT_RE = re.compile(r"^[A-Z]{2}\.[A-Z]{2}-\d{2}$")

# SCF control ids: 'GOV-01', 'GOV-01.1', 'MON-01.12' (2-4 letter domain).
_SCF_ID_RE = re.compile(r"^[A-Z]{2,4}-\d{2}(?:\.\d{1,2})?$")
# CCM control ids: 'A&A-01', 'AIS-01', 'LOG-03' (OSCAL id-refs write A_A for A&A).
_CCM_ID_RE = re.compile(r"^[A-Z][A-Za-z&]{1,3}-\d{2}$")


def _canon_ccm_id(raw: str) -> Optional[str]:
    """OSCAL id-ref / OLIR form -> the CCM xlsx display form ('A_A-01' -> 'A&A-01').
    Only the A&A domain carries the underscore encoding; everything else is as-is."""
    s = str(raw).strip().replace("A_A-", "A&A-")
    return s if _CCM_ID_RE.match(s) else None


def _canon_scf_id(raw: str) -> Optional[str]:
    s = str(raw).strip().upper()
    return s if _SCF_ID_RE.match(s) else None


def load_800_66_projection(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """HIPAA Security Rule citations -> 800-53 r5 controls, from the NIST OLIR
    informative reference carried in the SP 800-66r2 CPRT element graphs.
    NIST-stated, control-level, confidence 0.85 (direct_800_66), one canonical
    citation namespace with the hub (normalize_hipaa_citation).  The graphs'
    CSF v1.1 references are deliberately NOT loaded (version-stale)."""
    src = "cprt-sp800-66r2-olir-graphs"
    if not source_path(src).exists():
        return [], {"skipped": "artifact not on disk"}
    fname = source_path(src).name
    edges: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    dropped_native = dropped_dest = 0
    for host, ext in _iter_graph_external_rels(_load_graph_artifact(src)):
        if ext.get("olirName") != _OLIR_800_66_53:
            continue
        native = normalize_hipaa_citation(str(host or ""))
        if not native:
            dropped_native += 1
            continue
        ctrl = normalize_control_id(str(ext.get("elementIdentifier", "")).strip())
        if not ctrl or ctrl not in catalog_ids:
            dropped_dest += 1
            continue
        key = (native, ctrl)
        if key in seen:
            continue
        seen.add(key)
        edges.append(_projection_row(
            framework="HIPAA Security", native_id=native, r5_control=ctrl,
            granularity="control", provenance="direct_800_66", confidence=0.85,
            needs_confirmation=0, source_file=fname, source_row=-1,
        ))
    derive_relationships(edges)
    edges.sort(key=lambda r: (r["native_id"], r["r5_control"]))
    return edges, {"edges": len(edges), "dropped_native": dropped_native,
                   "dropped_dest": dropped_dest,
                   "distinct_citations": len({e["native_id"] for e in edges})}


def load_csf2_projection(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """NIST CSF 2.0 subcategories -> 800-53 r5.2.0 controls, from the official
    OLIR informative reference in the CSF 2.0 CPRT element graphs (NIST-owned,
    pinned to the exact catalog release on disk)."""
    src = "cprt-csf2-olir-graphs"
    if not source_path(src).exists():
        return [], {"skipped": "artifact not on disk"}
    fname = source_path(src).name
    edges: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    dropped_native = dropped_dest = 0
    for host, ext in _iter_graph_external_rels(_load_graph_artifact(src)):
        if ext.get("olirName") != _OLIR_CSF2_53:
            continue
        native = str(host or "").strip()
        if not _CSF2_SUBCAT_RE.match(native):
            dropped_native += 1
            continue
        # canonical CSF form drops the zero-pad: GV.OC-01 -> GV.OC-1? No — the
        # repo's CSF canonical (consensus_detector._canon) is XX.XX-N unpadded.
        fam, num = native.rsplit("-", 1)
        native = f"{fam}-{int(num)}"
        ctrl = normalize_control_id(str(ext.get("elementIdentifier", "")).strip())
        if not ctrl or ctrl not in catalog_ids:
            dropped_dest += 1
            continue
        key = (native, ctrl)
        if key in seen:
            continue
        seen.add(key)
        edges.append(_projection_row(
            framework="NIST CSF 2.0", native_id=native, r5_control=ctrl,
            granularity="control", provenance="direct_csf2", confidence=0.85,
            needs_confirmation=0, source_file=fname, source_row=-1,
        ))
    derive_relationships(edges)
    edges.sort(key=lambda r: (r["native_id"], r["r5_control"]))
    return edges, {"edges": len(edges), "dropped_native": dropped_native,
                   "dropped_dest": dropped_dest,
                   "distinct_subcats": len({e["native_id"] for e in edges})}


_ISO_ANNEX_DEST_RE = re.compile(r"Annex A Controls?:\s*([\d., ]+)", re.IGNORECASE)


def collect_csf2_olir_pairs() -> Tuple[List[dict], dict]:
    """Third-party <-> CSF 2.0 pairs from the OLIR sets in the CSF graphs, for the
    master surface (NOT spine projections): PCI DSS 4.0.1 <-> CSF2 (owner-submitted),
    ISO 27001:2022 <-> CSF2 (category-level; compound dest strings parsed
    conservatively, function-level rows dropped), CSF2 <-> 171r3 (NIST), and — since
    Phase 20 — CCM v4 <-> CSF2 and SCF <-> CSF2 (category-level like the ISO set).
    Returns rows {fw, native, csf2_id, olir_name}."""
    src = "cprt-csf2-olir-graphs"
    if not source_path(src).exists():
        return [], {"skipped": "artifact not on disk"}
    rows: List[dict] = []
    seen: Set[Tuple[str, str, str]] = set()
    dropped = {"pci": 0, "iso": 0, "171r3": 0, "ccm": 0, "scf": 0, "csf_host": 0}
    _category_level = (_OLIR_ISO_CSF2, _OLIR_SCF_CSF2)
    for host, ext in _iter_graph_external_rels(_load_graph_artifact(src)):
        name = ext.get("olirName")
        if name not in (_OLIR_PCI_CSF2, _OLIR_ISO_CSF2, _OLIR_CSF2_171R3,
                        _OLIR_CCM_CSF2, _OLIR_SCF_CSF2):
            continue
        host_s = str(host or "").strip()
        # host must be a subcategory (or, for category-level sets, a category)
        if _CSF2_SUBCAT_RE.match(host_s):
            fam, num = host_s.rsplit("-", 1)
            csf_id = f"{fam}-{int(num)}"
        elif name in _category_level and re.match(r"^[A-Z]{2}\.[A-Z]{2}$", host_s):
            csf_id = host_s  # category-level rows keep the category id
        else:
            dropped["csf_host"] += 1
            continue
        dest = str(ext.get("elementIdentifier", "")).strip()
        if name == _OLIR_PCI_CSF2:
            pci = normalize_pci_id(dest)
            if not pci:
                dropped["pci"] += 1
                continue
            targets = [("PCI DSS v4.0", pci)]
        elif name == _OLIR_CSF2_171R3:
            nat = _canon_171r3_native(dest)
            if not nat:
                dropped["171r3"] += 1
                continue
            targets = [("NIST SP 800-171 r3", nat)]
        elif name == _OLIR_CCM_CSF2:
            ccm = _canon_ccm_id(dest)
            if not ccm:
                dropped["ccm"] += 1
                continue
            targets = [("CSA CCM v4", ccm)]
        elif name == _OLIR_SCF_CSF2:
            scf = _canon_scf_id(dest)
            if not scf:
                dropped["scf"] += 1
                continue
            targets = [("SCF 2026.1", scf)]
        else:  # ISO: compound dest like 'Annex A Controls: 5.26' / 'Mandatory Clause: None'
            m = _ISO_ANNEX_DEST_RE.search(dest)
            if not m:
                dropped["iso"] += 1
                continue
            targets = []
            for tok in re.split(r"[,\s]+", m.group(1).strip()):
                if not tok or tok == ".":
                    continue
                canon, _space = normalize_iso_id(f"A.{tok}" if re.match(r"^\d+\.\d+$", tok) else tok)
                if canon:
                    targets.append(("ISO 27001/2 (2022)", canon))
                else:
                    dropped["iso"] += 1
        for fw, nat in targets:
            key = (name, csf_id, f"{fw}:{nat}")
            if key in seen:
                continue
            seen.add(key)
            rows.append({"fw": fw, "native": nat, "csf2_id": csf_id, "olir_name": name})
    rows.sort(key=lambda r: (r["olir_name"], r["fw"], r["native"], r["csf2_id"]))
    return rows, {"pairs": len(rows), "dropped": dropped,
                  "by_set": {n: sum(1 for r in rows if r["olir_name"] == n)
                             for n in sorted({r["olir_name"] for r in rows})}}


def load_pci_master_projection(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """PCI DSS v4.0 requirements -> 800-53 r5 controls from the user-provided
    master crosswalk's PCI column.  Bundled tier: co-citation by a single
    compiler, confidence 0.60, needs_confirmation=1 — the Phase 18 consensus
    tier lifts eligible pairs to 0.85 at query time.  Unparseable tokens are
    counted and dropped, never guessed."""
    path = REPO_ROOT / "canonical-sources" / "crosswalk_80053_master.json"
    if not path.exists():
        return [], {"skipped": "master crosswalk not on disk"}
    with open(path, encoding="utf-8") as f:
        master = json.load(f)
    edges: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    unparseable = dropped_ctrl = 0
    for nist_raw in sorted(master.get("map", {})):
        ctrl = normalize_control_id(nist_raw)
        if not ctrl or ctrl not in catalog_ids:
            dropped_ctrl += 1
            continue
        for tok in master["map"][nist_raw].get("PCI DSS v4.0", []) or []:
            pci = normalize_pci_id(str(tok).strip())
            if not pci:
                unparseable += 1
                continue
            key = (pci, ctrl)
            if key in seen:
                continue
            seen.add(key)
            edges.append(_projection_row(
                framework="PCI DSS v4.0", native_id=pci, r5_control=ctrl,
                relationship="intersect", relationship_basis="co_citation",
                granularity="control", provenance="master_crosswalk",
                confidence=0.60, needs_confirmation=1,
                source_file=path.name, source_sheet=nist_raw, source_row=-1,
            ))
    edges.sort(key=lambda r: (r["native_id"], r["r5_control"]))
    return edges, {"edges": len(edges), "unparseable_pci_tokens": unparseable,
                   "controls_not_in_catalog": dropped_ctrl,
                   "distinct_pci": len({e["native_id"] for e in edges})}


def load_aicpa_tsp_hub() -> Tuple[List[dict], dict]:
    """TSC <-> HITRUST direct pairs from the licensed 'Mapping of 2017 AICPA TSP
    to HITRUST CSF v11.4.0' workbook (487 merged ranges resolved via openpyxl).

    Layout (sheet 'CSF to AICPA Mapping'): row 1 = TSC criteria headers across
    merged column ranges ('CC1.1 The entity demonstrates ...'); row 2 =
    point-of-focus sub-headers; column A from row 5 = HITRUST control ids
    ('01.b User Registration'); body cells carry an 'X' where a HITRUST control
    covers that point of focus.  Pairs are deduped to the criterion level.
    Emits master-surface pairs (hub tier, 0.65) — NOT a spine projection.
    Returns rows {tsc_id, hitrust_id}."""
    src = "aicpa-tsp-to-hitrust"
    try:
        path = source_path(src)
    except Exception:
        return [], {"skipped": "not registered"}
    if not path.exists():
        return [], {"skipped": "artifact not on disk"}
    from openpyxl import load_workbook  # available via requirements.txt
    wb = load_workbook(path, read_only=False, data_only=True)
    ws = wb[wb.sheetnames[0]]
    # Resolve merged header ranges: every cell in a range sees the anchor value.
    grid: Dict[Tuple[int, int], object] = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is not None:
                grid[(c.row, c.column)] = c.value
    for rng in ws.merged_cells.ranges:
        anchor = grid.get((rng.min_row, rng.min_col))
        if anchor is None:
            continue
        for rr in range(rng.min_row, rng.max_row + 1):
            for cc in range(rng.min_col, rng.max_col + 1):
                grid.setdefault((rr, cc), anchor)
    # Column -> TSC criterion from the row-1 merged headers.
    col_tsc: Dict[int, str] = {}
    tsc_token = re.compile(r"\b(CC|PI|A|C|P)\s?(\d{1,2})\.(\d{1,2})\b")
    for cc in range(2, ws.max_column + 1):
        v = grid.get((1, cc))
        if v is None:
            continue
        m = tsc_token.search(str(v))
        if m:
            tsc = normalize_tsc_id(f"{m.group(1)}{m.group(2)}.{m.group(3)}")
            if tsc:
                col_tsc[cc] = tsc
    # Row -> HITRUST control id from column A ('01.b User Registration',
    # '09.aa Audit Logging' — one- or two-letter suffixes).
    hitrust_re = re.compile(r"^(\d{2}\.[a-z]{1,2})\b")
    row_hitrust: Dict[int, str] = {}
    for rr in range(2, ws.max_row + 1):
        v = grid.get((rr, 1))
        if v is None:
            continue
        m = hitrust_re.match(str(v).strip())
        if m:
            row_hitrust[rr] = str(v).strip()
    pairs: Set[Tuple[str, str]] = set()
    markers = 0
    for (rr, cc), v in grid.items():
        if rr not in row_hitrust or cc not in col_tsc:
            continue
        if str(v).strip().upper() == "X":
            markers += 1
            pairs.add((col_tsc[cc], row_hitrust[rr]))
    rows = [{"tsc_id": t, "hitrust_id": h} for t, h in sorted(pairs)]
    return rows, {"pairs": len(rows), "tsc_columns": len(col_tsc),
                  "hitrust_rows": len(row_hitrust), "x_markers": markers,
                  "distinct_tsc": len({r["tsc_id"] for r in rows}),
                  "distinct_hitrust": len({r["hitrust_id"] for r in rows})}


# ── framework_projection: SCF + CCM meta-frameworks (Phase 20) ──────────────────
# Acceptance-authority scope: SCF edges are SCF/CAP-scope acceptance rules; CCM
# edges are CSA-STAR-scope. Owner-of-source mappings to a foreign target sit in
# the master surface's `owner_stated` tier — below NIST-reviewed, above the hub.

_CCM_OSCAL_JSON = (Path(__file__).resolve().parent.parent.parent / "canonical-sources" /
                   "source_data" / "csa-star" /
                   "CCMv4.0.12-OSCAL-Dataset_Generated-at_2024-06-03" /
                   "ccm-oscal-mappings.json")
_CCM_REL_MAP = {"equivalent-to": "equal", "superset-of": "superset"}


def load_scf_projection(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """SCF controls -> 800-53 r5, from SCF's own 'NIST 800-53 R5' column in the
    2026.1.1 workbook.  Owner co-citation (the xlsx carries no per-mapping STRM
    strength — those live in per-framework PDFs not on disk): provenance
    'scf_direct', confidence 0.80, needs_confirmation=1, relationships filled by
    fan-out cardinality."""
    src = "scf-controls"
    try:
        path = source_path(src)
    except Exception:
        return [], {"skipped": "not registered"}
    if not path.exists():
        return [], {"skipped": "artifact not on disk"}
    df = pd.read_excel(path, sheet_name="SCF 2026.1")
    cols = list(df.columns)
    id_col = next((c for c in cols if str(c).strip() == "SCF #"), None)
    nist_col = None
    for c in cols:
        flat = str(c).replace("\n", " ")
        if "800-53" in flat and "R5" in flat and "53B" not in flat:
            nist_col = c
            break
    if id_col is None or nist_col is None:
        return [], {"skipped": f"columns not found (id={id_col!r}, nist={nist_col!r})"}
    edges: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    bad_scf = unresolved = 0
    fname = path.name
    for i, row in df.iterrows():
        scf = _canon_scf_id(str(row.get(id_col) or ""))
        if not scf:
            bad_scf += 1
            continue
        for tok in re.split(r"[\n;,]+", str(row.get(nist_col) or "")):
            tok = tok.strip()
            if not tok or tok.lower() == "nan":
                continue
            ctrl = normalize_control_id(tok)
            if not ctrl or ctrl not in catalog_ids:
                unresolved += 1
                continue
            key = (scf, ctrl)
            if key in seen:
                continue
            seen.add(key)
            edges.append(_projection_row(
                framework="SCF 2026.1", native_id=scf, r5_control=ctrl,
                granularity="control", provenance="scf_direct", confidence=0.80,
                needs_confirmation=1, source_file=fname,
                source_sheet="SCF 2026.1", source_row=int(i),
            ))
    derive_relationships(edges)
    edges.sort(key=lambda r: (r["native_id"], r["r5_control"]))
    return edges, {"edges": len(edges), "rows_without_scf_id": bad_scf,
                   "unresolved_53_tokens": unresolved,
                   "distinct_scf": len({e["native_id"] for e in edges})}


def _ccm_oscal_maps(target_marker: str) -> Optional[list]:
    """The maps[] block of the OSCAL mapping whose target href contains marker."""
    if not _CCM_OSCAL_JSON.exists():
        return None
    with open(_CCM_OSCAL_JSON, encoding="utf-8") as f:
        mc = json.load(f)["mapping-collection"]["mappings"]
    for m in mc:
        if target_marker in str(m.get("target-resource", {}).get("href", "")):
            return m["maps"]
    return None


def load_ccm_projection(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """CCM v4 controls -> 800-53 r5, from CSA's own OSCAL mapping-collection
    (source-STATED relationships: equivalent-to -> equal, superset-of -> superset).
    provenance 'ccm_oscal', confidence 0.85, needs_confirmation=0."""
    maps = _ccm_oscal_maps("usnistgov")
    if maps is None:
        return [], {"skipped": "OSCAL mapping artifact not on disk"}
    edges: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    bad_ccm = bad_rel = unresolved = expanded = 0
    fname = _CCM_OSCAL_JSON.name
    for i, m in enumerate(maps):
        rel_raw = m.get("relationship")
        rel_type = rel_raw.get("type") if isinstance(rel_raw, dict) else rel_raw
        rel = _CCM_REL_MAP.get(str(rel_type))
        if rel is None:
            bad_rel += 1
            continue
        for s in m.get("sources", []):
            ccm = _canon_ccm_id(s.get("id-ref", ""))
            if not ccm:
                bad_ccm += 1
                continue
            for t in m.get("targets", []):
                expanded += 1
                ctrl = oscal_control_id(str(t.get("id-ref", "")).strip())
                if not ctrl or ctrl not in catalog_ids:
                    unresolved += 1
                    continue
                key = (ccm, ctrl)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(_projection_row(
                    framework="CSA CCM v4", native_id=ccm, r5_control=ctrl,
                    relationship=rel, relationship_basis="source_stated",
                    granularity="control", provenance="ccm_oscal", confidence=0.85,
                    needs_confirmation=0, source_file=fname, source_row=i,
                ))
    edges.sort(key=lambda r: (r["native_id"], r["r5_control"]))
    return edges, {"edges": len(edges), "expanded_pairs": expanded,
                   "unresolved_53": unresolved, "bad_ccm_ids": bad_ccm,
                   "unmapped_relationships": bad_rel,
                   "distinct_ccm": len({e["native_id"] for e in edges})}


_CIS_OSCAL_RE = re.compile(r"^cisc-(\d{1,2})\.(\d{1,2})$")


def collect_ccm_cis_pairs() -> Tuple[List[dict], dict]:
    """CCM <-> CIS Controls 8.1 pairs from the same OSCAL mapping-collection
    (CSA-stated relationships), for the master surface. Returns rows
    {ccm_id, cis_id, relationship}."""
    maps = _ccm_oscal_maps("CISecurity")
    if maps is None:
        return [], {"skipped": "OSCAL mapping artifact not on disk"}
    pairs: Set[Tuple[str, str, str]] = set()
    bad = 0
    for m in maps:
        rel_raw = m.get("relationship")
        rel_type = rel_raw.get("type") if isinstance(rel_raw, dict) else rel_raw
        rel = _CCM_REL_MAP.get(str(rel_type), "intersect")
        for s in m.get("sources", []):
            ccm = _canon_ccm_id(s.get("id-ref", ""))
            if not ccm:
                bad += 1
                continue
            for t in m.get("targets", []):
                mm = _CIS_OSCAL_RE.match(str(t.get("id-ref", "")).strip())
                if not mm:
                    bad += 1
                    continue
                pairs.add((ccm, f"{int(mm.group(1))}.{int(mm.group(2))}", rel))
    rows = [{"ccm_id": c, "cis_id": k, "relationship": r} for c, k, r in sorted(pairs)]
    return rows, {"pairs": len(rows), "dropped": bad}


# ── framework_projection: HITRUST hub for commercial frameworks (Phase 3) ───────

# role in the manifest -> canonical framework label projected into the spine.
# 'nist_53r5_id' is the spine anchor (not a projected framework); 'hitrust_id' is
# the pivot key.  Everything else becomes a framework whose native ids co-occur with
# the row's NIST r5 sub-parts (hub co-membership, confidence 0.65, hop 2).
_HUB_FRAMEWORKS = {
    # "SOC 2" is the report label; the native ids are the AICPA Trust Services
    # Criteria (2017) themselves — the specific testable criteria a SOC 2 audit
    # evaluates against (CC/A/C/PI/P series), e.g. "AICPA 2017 CC6.1". The label is
    # kept as "SOC 2" so it joins with the ER-crosswalk naming; TSC-criterion
    # provenance stays on every edge's native_id.
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
    iso_ambiguous = 0
    iso_label = _HUB_FRAMEWORKS.get("iso_27001_2022_id")
    hipaa_label = _HUB_FRAMEWORKS.get("hipaa_security_id")

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
                if label == iso_label:
                    # Canonicalize ISO citations so hub / OLIR / ER ids join.
                    _canon, _space = normalize_iso_id(target_id)
                    if _canon:
                        target_id = _canon
                    if _space == "ambiguous":
                        iso_ambiguous += 1
                elif label == hipaa_label:
                    # One HIPAA citation namespace with the 800-66 direct
                    # projection ('§ 164.308(a)(1)' -> '164.308(a)(1)').
                    _hcanon = normalize_hipaa_citation(target_id)
                    if _hcanon:
                        target_id = _hcanon
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
        "iso_ambiguous": iso_ambiguous,
    }
    return hub_rows, edges, stats


def _read_sheet_name(src: str) -> str:
    try:
        return sheet_name(src)
    except Exception:
        return ""


# ── odp_values: concrete ODP values pinned in DAAPM prose (Phase 4) ─────────────

_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "sixty": 60, "ninety": 90,
}
_UNIT_SINGULAR = {
    "minutes": "minute", "hours": "hour", "days": "day", "weeks": "week",
    "months": "month", "years": "year", "attempts": "attempt", "characters": "character",
}
# numeric value + unit ("72 hours", "90 days", "3 consecutive"/"3 attempts")
_RE_NUM_UNIT = re.compile(
    r"\b(\d+)\s+(minutes?|hours?|days?|weeks?|months?|years?|attempts?|characters?)\b", re.I)
# parenthetical numeral ("(15) minute")
_RE_PAREN = re.compile(r"\((\d+)\)\s*(minutes?|hours?|days?|weeks?|months?|years?)\b", re.I)
# word-number + unit/consecutive ("three consecutive", "one year")
_RE_WORD = re.compile(
    r"\b(" + "|".join(_WORD_NUM) + r")\s+(consecutive|minutes?|hours?|days?|weeks?|months?|years?|attempts?|characters?)\b",
    re.I)
# frequency adverbs
_RE_FREQ = re.compile(
    r"\b(annually|quarterly|monthly|weekly|daily|semi-?annually|biannually|continuously)\b", re.I)


def _norm_value(num: int, unit: str) -> str:
    unit = unit.lower()
    unit = _UNIT_SINGULAR.get(unit, unit)
    if unit == "consecutive":
        unit = "attempt"
    return f"{num} {unit}"


def load_odp_values(catalog_ids: Set[str]) -> Tuple[List[dict], dict]:
    """
    Extract concrete ODP values from the DAAPM (DoD) baseline prose.  Values are
    linked at the control level (odp_id=NULL) because the prose does not carry ODP
    ids; every row is flagged needs_confirmation.  Best-effort regex extraction.
    """
    src = "federal-baseline-daapm"
    fname = source_path(src).name
    df = _read_source_df(src)
    cols = list(df.columns)
    num_c = _find_col(cols, col(src, "nist_id"))
    txt_c = _find_col(cols, col(src, "control_text"))
    if num_c is None or txt_c is None:
        return [], {"rows": 0, "note": "DAAPM control_text column not found"}

    rows: List[dict] = []
    seen: Set[Tuple[str, str]] = set()
    for i, rec in enumerate(df.itertuples(index=False), start=0):
        rowd = dict(zip(df.columns, rec))
        cid = normalize_control_id(str(rowd.get(num_c, "")).strip())
        if not cid or cid not in catalog_ids:
            continue
        text = str(rowd.get(txt_c, "") or "")
        if not text or text.lower() == "nan":
            continue

        matches: List[Tuple[str, str, str, float]] = []  # (raw, norm, kind, conf)
        for m in _RE_NUM_UNIT.finditer(text):
            matches.append((m.group(0), _norm_value(int(m.group(1)), m.group(2)),
                            "count" if "attempt" in m.group(2).lower() else "duration", 0.7))
        for m in _RE_PAREN.finditer(text):
            matches.append((m.group(0), _norm_value(int(m.group(1)), m.group(2)), "duration", 0.7))
        for m in _RE_WORD.finditer(text):
            matches.append((m.group(0), _norm_value(_WORD_NUM[m.group(1).lower()], m.group(2)),
                            "count" if "consecutive" in m.group(2).lower() or "attempt" in m.group(2).lower() else "duration", 0.55))
        for m in _RE_FREQ.finditer(text):
            matches.append((m.group(0), m.group(1).lower().replace("semi annually", "semi-annually"),
                            "frequency", 0.55))

        for raw, norm, kind, conf in matches:
            key = (cid, norm)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "control_id": cid, "odp_id": None, "baseline": "DAAPM (DoD)",
                "value_raw": raw.strip(), "value_norm": norm, "value_kind": kind,
                "extraction_confidence": conf, "needs_confirmation": 1,
                "source_file": fname, "source_row": i,
            })

    rows.sort(key=lambda r: (r["control_id"], r["value_norm"]))
    stats = {
        "rows": len(rows),
        "controls_with_values": len({r["control_id"] for r in rows}),
        "kinds": sorted({r["value_kind"] for r in rows}),
    }
    return rows, stats


def detect_odp_clashes(odp_rows: List[dict]) -> List[dict]:
    """
    Given odp_values rows from one or more baselines, find controls/ODPs where two
    baselines pin *different* values (an odp_value_divergence clash).  Pure function
    (unit-testable).  When only one baseline has values, nothing clashes — the ODP is
    'undetermined' for the other side, which the overlap engine surfaces as partial.
    """
    groups: Dict[Tuple[str, Optional[str]], Dict[str, Set[str]]] = {}
    for r in odp_rows:
        key = (r["control_id"], r.get("odp_id"))
        groups.setdefault(key, {}).setdefault(r["baseline"], set()).add(r["value_norm"])

    clashes: List[dict] = []
    for (control_id, odp_id), by_base in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        if len(by_base) < 2:
            continue
        value_sets = list(by_base.values())
        if all(v == value_sets[0] for v in value_sets):
            continue  # all baselines agree
        clashes.append({
            "control_id": control_id,
            "odp_id": odp_id,
            "kind": "odp_value_divergence",
            "positions": [
                {"baseline": b, "values": sorted(v)} for b, v in sorted(by_base.items())
            ],
        })
    return clashes


# ── framework_projection: CMMC/800-171 <-> 800-53 crosswalk (Phase 2b) ───────

_STRM_MAP = {
    "equal": "equal",
    "intersects with": "intersect",
    "subset of": "subset",
    "superset of": "superset",
    "no relationship": "disjoint",
}

_FEDRAMP_ODP_RE = re.compile(
    r"([A-Z]{2,3}-\d{1,3}(?:\(\d{1,3}\))?_ODP(?:\[\d+\])?)\s*[-–—]?\s*(.+)",
    re.I,
)


def load_cmmc171_projection(
    catalog_ids: Set[str],
) -> Tuple[List[dict], List[dict], dict]:
    """
    Project CMMC 2.0 and NIST SP 800-171 r2 onto the r5 spine using the
    CMMC/800-171↔800-53 crosswalk.  Returns (projection_edges, fedramp_odp_rows, stats).

    Each row produces up to two projection edges (one per framework) anchored to
    the r5 sub-part parsed from the 53A objective column.  Relationships come from
    the 'Mapping -171 to -53' column (STRM semantics: Equal/Subset/Superset/Intersects).

    provenance='cmmc171', confidence=0.95, hop_count=1, relationship_basis='source_stated'.
    ODP references in the objective column are collected for backfill in link_odps_to_subparts.
    FedRAMP pinned ODP values are extracted from the FedRAMP column.
    """
    src = "cmmc-800-171-53-crosswalk"
    fname = source_path(src).name
    sname = _read_sheet_name(src)
    df = _read_source_df(src)
    cols = list(df.columns)

    cmmc_c = _find_col(cols, col(src, "cmmc_practice"))
    obj171_c = _find_col(cols, col(src, "nist_171a_objective"))
    r5ctrl_c = _find_col(cols, col(src, "nist_53r5_id"))
    obj53_c = _find_col(cols, col(src, "nist_53a_objective"))
    strm_c = _find_col(cols, col(src, "mapping_171_to_53"))
    qual_c = _find_col(cols, col(src, "relationship_strength"))
    fedramp_c = _find_col(cols, col(src, "fedramp_moderate_notes"))

    edges: List[dict] = []
    fedramp_rows: List[dict] = []
    odp_links: List[Tuple[str, str, Optional[str]]] = []  # (odp_id, control_id, subpart)
    seen_edge: Set[Tuple[str, str, str, str]] = set()
    seen_fedramp: Set[Tuple[str, str]] = set()
    skipped_disjoint = 0
    skipped_withdrawn = 0
    rows_read = 0

    for i, rec in enumerate(df.itertuples(index=False), start=0):
        rowd = dict(zip(df.columns, rec))
        rows_read += 1

        cmmc_id = str(rowd.get(cmmc_c, "")).strip() if cmmc_c else ""
        obj171_raw = str(rowd.get(obj171_c, "")).strip() if obj171_c else ""
        r5ctrl_raw = str(rowd.get(r5ctrl_c, "")).strip() if r5ctrl_c else ""
        obj53_raw = str(rowd.get(obj53_c, "")).strip() if obj53_c else ""

        if cmmc_id.lower() == "nan":
            cmmc_id = ""
        if obj171_raw.lower() == "nan":
            obj171_raw = ""
        if r5ctrl_raw.lower() == "nan":
            r5ctrl_raw = ""

        # Relationship from column 8 (Mapping -171 to -53)
        strm_raw = str(rowd.get(strm_c, "")).strip().lower() if strm_c else ""
        if strm_raw == "nan":
            strm_raw = ""
        relationship = _STRM_MAP.get(strm_raw, "unspecified")
        if relationship == "disjoint":
            skipped_disjoint += 1
            continue

        # Relationship quality from column 9
        qual_raw = str(rowd.get(qual_c, "")).strip() if qual_c else ""
        if qual_raw.lower() == "nan":
            qual_raw = ""

        # Spine anchor: r5 control from the explicit column
        r5_control = normalize_control_id(r5ctrl_raw)
        if not r5_control or r5_control not in catalog_ids:
            continue

        # Parse the 53A objective for sub-part / ODP linkage
        r5_subpart: Optional[str] = None
        odp_id: Optional[str] = None
        if obj53_raw and obj53_raw.lower() not in ("nan", "withdrawn"):
            parsed = parse_objective(obj53_raw)
            if not parsed:
                skipped_withdrawn += 1
            else:
                _, subpath, odp_ref = parsed[0]
                if subpath:
                    r5_subpart = canon_subpart(r5_control, subpath)
                if odp_ref:
                    odp_id = odp_ref
                    odp_links.append((odp_ref, r5_control, r5_subpart))
        elif obj53_raw.lower() == "withdrawn":
            skipped_withdrawn += 1
            continue

        granularity = "subpart" if r5_subpart else "control"

        # Emit CMMC 2.0 edge
        if cmmc_id:
            key = ("CMMC 2.0", cmmc_id, r5_control, r5_subpart or "")
            if key not in seen_edge:
                seen_edge.add(key)
                edges.append(_projection_row(
                    framework="CMMC 2.0", native_id=cmmc_id,
                    r5_control=r5_control, r5_subpart=r5_subpart,
                    odp_id=odp_id,
                    relationship=relationship,
                    relationship_basis="source_stated",
                    granularity=granularity, provenance="cmmc171",
                    confidence=0.95, hop_count=1, needs_confirmation=0,
                    source_file=fname, source_sheet=sname, source_row=i,
                ))

        # Emit NIST SP 800-171 r2 edge
        if obj171_raw:
            key = ("NIST SP 800-171 r2", obj171_raw, r5_control, r5_subpart or "")
            if key not in seen_edge:
                seen_edge.add(key)
                edges.append(_projection_row(
                    framework="NIST SP 800-171 r2", native_id=obj171_raw,
                    r5_control=r5_control, r5_subpart=r5_subpart,
                    odp_id=odp_id,
                    relationship=relationship,
                    relationship_basis="source_stated",
                    granularity=granularity, provenance="cmmc171",
                    confidence=0.95, hop_count=1, needs_confirmation=0,
                    source_file=fname, source_sheet=sname, source_row=i,
                ))

        # Extract FedRAMP ODP pinned values (Step 4b)
        fedramp_raw = str(rowd.get(fedramp_c, "")).strip() if fedramp_c else ""
        if fedramp_raw and fedramp_raw.lower() != "nan":
            fm = _FEDRAMP_ODP_RE.match(fedramp_raw)
            if fm:
                fodp_raw = fm.group(1)
                fval = fm.group(2).strip()
                fodp_parsed = parse_objective(fodp_raw)
                if fodp_parsed:
                    _, _, fodp_ref = fodp_parsed[0]
                    if fodp_ref and fval:
                        fkey = (r5_control, fodp_ref)
                        if fkey not in seen_fedramp:
                            seen_fedramp.add(fkey)
                            fedramp_rows.append({
                                "control_id": r5_control,
                                "odp_id": fodp_ref,
                                "baseline": "FedRAMP Moderate",
                                "value_raw": fedramp_raw,
                                "value_norm": fval,
                                "value_kind": "pinned",
                                "extraction_confidence": 0.7,
                                "needs_confirmation": 1,
                                "source_file": fname,
                                "source_row": i,
                            })

    edges.sort(key=lambda r: (r["framework"], r["native_id"], r["r5_control"], r["r5_subpart"] or ""))
    fedramp_rows.sort(key=lambda r: (r["control_id"], r["odp_id"]))
    stats = {
        "rows_read": rows_read,
        "edges": len(edges),
        "cmmc_edges": len([e for e in edges if e["framework"] == "CMMC 2.0"]),
        "nist171_edges": len([e for e in edges if e["framework"] == "NIST SP 800-171 r2"]),
        "odp_links": odp_links,
        "fedramp_values": len(fedramp_rows),
        "skipped_disjoint": skipped_disjoint,
        "skipped_withdrawn": skipped_withdrawn,
        "relationships": sorted({e["relationship"] for e in edges}),
    }
    return edges, fedramp_rows, stats


# ── OSCAL structural: ODP -> sub-part links + assessment objectives (Phase 11) ──

OSCAL_CACHE_PATH = REPO_ROOT / "cross-mapping" / "output" / "oscal_v5.2.0_cache.json"


def _iter_oscal_controls(doc: dict):
    """Yield every control dict in the raw OSCAL catalog (incl. nested enhancements)."""
    catalog = doc.get("catalog", doc)
    stack = []
    for grp in catalog.get("groups", []) or []:
        stack.extend(grp.get("controls", []) or [])
    while stack:
        ctrl = stack.pop()
        yield ctrl
        stack.extend(ctrl.get("controls", []) or [])


def load_oscal_structural(catalog_ids: Set[str]) -> Tuple[List[dict], List[dict], dict]:
    """
    Walk the raw OSCAL catalog's structured parts trees and derive:

      odp_links       [{odp_id, control_id, r5_subpart, link_basis}] — each ODP linked
                      to the statement sub-part whose prose references it via
                      '{{ insert: param, … }}'.  Deepest reference wins; an ODP only
                      referenced by the root statement gets link_basis='control_scope'
                      and r5_subpart=None.  Nothing fabricated.
      objective_rows  [{objective_id, control_id, r5_subpart, label, prose, …}] — one
                      row per 800-53A assessment-objective part (sub-part anchors that
                      extend CCI-like coverage into PT/SR/PM).
    """
    if not OSCAL_CACHE_PATH.exists():
        return [], [], {"note": "oscal cache not found", "odp_links": 0, "objectives": 0}
    doc = json.loads(OSCAL_CACHE_PATH.read_text(encoding="utf-8"))
    fname = OSCAL_CACHE_PATH.name

    odp_links: List[dict] = []
    objective_rows: List[dict] = []
    basis_counts: Dict[str, int] = {}
    controls_seen = 0

    for ctrl in _iter_oscal_controls(doc):
        cid = oscal_control_id(str(ctrl.get("id", "")))
        if not cid or cid not in catalog_ids:
            continue
        controls_seen += 1
        recs = parse_oscal_parts(ctrl)

        # ODP -> deepest statement sub-part that references it
        best: Dict[str, Tuple[int, str]] = {}  # odp_id -> (depth, subpath)
        ref_count: Dict[str, int] = {}
        for rec in recs:
            if rec["kind"] != "statement":
                continue
            depth = rec["subpath"].count(".") + 1 if rec["subpath"] else 0
            for odp in rec["odp_refs"]:
                ref_count[odp] = ref_count.get(odp, 0) + 1
                cur = best.get(odp)
                if cur is None or depth > cur[0]:
                    best[odp] = (depth, rec["subpath"])
        for odp, (depth, subpath) in best.items():
            if subpath:
                basis = "oscal_part_insert" if ref_count[odp] == 1 else "deepest_reference"
                r5_subpart = canon_subpart(cid, subpath)
            else:
                basis = "control_scope"
                r5_subpart = None
            basis_counts[basis] = basis_counts.get(basis, 0) + 1
            odp_links.append({
                "odp_id": odp, "control_id": cid,
                "r5_subpart": r5_subpart, "link_basis": basis,
            })

        # Assessment objectives — the label prop carries the 53A objective id
        # (e.g. 'AC-02d.03[01]'), matching the CMMC crosswalk's objective column.
        for rec in recs:
            if rec["kind"] != "objective" or not rec["part_id"]:
                continue
            label = ""
            objective_rows.append({
                "objective_id": rec["part_id"],
                "control_id": cid,
                "r5_subpart": canon_subpart(cid, rec["subpath"]) if rec["subpath"] else None,
                "label": label,
                "prose": rec["prose"],
                "source_file": fname,
                "source_row": -1,
            })

    # labels come from the raw part props; re-walk to fill them (cheap second pass)
    labels: Dict[str, str] = {}
    for ctrl in _iter_oscal_controls(doc):
        def collect(part):
            pid = part.get("id")
            if pid:
                for pr in part.get("props", []) or []:
                    if pr.get("name") == "label":
                        labels[pid] = pr.get("value", "")
            for ch in part.get("parts", []) or []:
                collect(ch)
        for part in ctrl.get("parts", []) or []:
            if part.get("name") == "assessment-objective":
                collect(part)
    for row in objective_rows:
        row["label"] = labels.get(row["objective_id"], "")

    odp_links.sort(key=lambda r: (r["control_id"], r["odp_id"]))
    objective_rows.sort(key=lambda r: (r["control_id"], r["objective_id"]))
    stats = {
        "controls_seen": controls_seen,
        "odp_links": len(odp_links),
        "objectives": len(objective_rows),
        "link_basis_counts": dict(sorted(basis_counts.items())),
    }
    return odp_links, objective_rows, stats


def link_odps_to_subparts_from_oscal(odp_links: List[dict], conn) -> int:
    """
    Definitive backfill of control_odps.r5_subpart + link_basis from the OSCAL
    structured parts walk.  Overwrites NULLs only; never downgrades an existing link.
    """
    updated = 0
    for lnk in odp_links:
        cur = conn.execute(
            "UPDATE control_odps SET r5_subpart = ?, link_basis = ? "
            "WHERE odp_id = ? AND control_id = ? AND r5_subpart IS NULL",
            (lnk["r5_subpart"], lnk["link_basis"], lnk["odp_id"], lnk["control_id"]),
        )
        updated += cur.rowcount
    return updated


def complete_subpart_inventory(conn) -> int:
    """
    Union every sub-part referenced by framework_projection or assessment_objectives
    into nist_subparts.  The inventory is otherwise built only from the catalog and
    the CCI bridge, which leaves control-level footprint expansion unable to
    enumerate sub-parts that only objectives or projections name — asymmetrically
    deflating subpart-basis overlap.  Every inserted row derives from real rows in
    the referencing table (source_file names it); nothing is fabricated.
    Deterministic: ordered SELECT, INSERT OR IGNORE.
    """
    inserted = 0
    for table, ctrl_col in (("framework_projection", "r5_control"),
                            ("assessment_objectives", "control_id")):
        rows = conn.execute(f"""
            SELECT DISTINCT r5_subpart, {ctrl_col} FROM {table}
            WHERE r5_subpart IS NOT NULL
              AND r5_subpart NOT IN (SELECT subpart_id FROM nist_subparts)
            ORDER BY r5_subpart""").fetchall()
        for subpart, ctrl in rows:
            if not subpart.startswith(ctrl + " "):
                continue  # malformed — never guess a path
            path = subpart[len(ctrl) + 1:]
            cur = conn.execute("""
                INSERT OR IGNORE INTO nist_subparts
                    (subpart_id, r5_control, path, ordinal, source_file, source_sheet, source_row)
                VALUES (?, ?, ?, 0, ?, '', -1)""",
                (subpart, ctrl, path, table))
            inserted += cur.rowcount
    return inserted


# ── CCI bridge from the current DISA CCI XML (native r5 refs, Phase 11) ────────

CCI_XML_PATH = REPO_ROOT / "canonical-sources" / "source_data" / "U_CCI_List.xml"

_APPJ_RE = re.compile(r"\b(AP|AR|DI|DM|IP|SE|TR|UL)-(\d{1,2})\b")


def load_appj_absorption_map(catalog_ids: Set[str]) -> Dict[str, List[str]]:
    """
    r4 Appendix J privacy control -> r5 controls that absorbed it, extracted from
    NIST's own change-detail prose in the r4->r5 comparison workbook (e.g. AC-1:
    'Addresses access processes and procedures elements of withdrawn App J control
    IP-2').  Only r5 targets present in the catalog are kept.
    """
    src = "nist-r4-to-r5-bridge"
    try:
        path = source_path(src)
    except Exception:
        return {}
    if not path.exists():
        return {}
    df = pd.read_excel(path, sheet_name=sheet_name(src), header=header_row(src))
    cols = list(df.columns)
    # Resolve both columns from the manifest roles first; the merged first header
    # row can hide 'Change Details' behind an unnamed column, so fall back to
    # content detection (the column whose cells mention 'App J') only if needed.
    detail_col = None
    id_col = None
    try:
        detail_col = _find_col(cols, col(src, "change_details"))
        id_col = _find_col(cols, col(src, "r5_id"))
    except Exception:
        pass
    if detail_col is None:
        for c in cols:
            if c == id_col:
                continue
            s = df[c].astype(str)
            if s.str.contains("App J", na=False).any():
                detail_col = c
                break
    if detail_col is None:
        return {}
    if id_col is None:
        id_col = cols[0]

    absorb: Dict[str, Set[str]] = {}
    for _, row in df.iterrows():
        r5 = normalize_control_id(str(row.get(id_col, "")).strip())
        if not r5 or r5 not in catalog_ids:
            continue
        detail = str(row.get(detail_col) or "")
        if detail == "nan":
            continue
        for m in _APPJ_RE.finditer(detail):
            r4 = f"{m.group(1)}-{int(m.group(2))}"
            absorb.setdefault(r4, set()).add(r5)
    return {k: sorted(v) for k, v in sorted(absorb.items())}


def load_cci_bridge_xml(catalog_ids: Set[str]) -> Tuple[List[dict], List[dict], dict]:
    """
    Parse the current DISA CCI List XML into cci_bridge + disa_ccis rows.

    Precedence per CCI (never fabricated, basis stamped on every row):
      1. native 800-53 rev 5 references            basis='r5_native'
      2. rev-4 refs whose id survives into r5       basis='r4_identity'
      3. rev-4 App J privacy refs -> absorbing r5   basis='appj_absorption'
         controls from the NIST comparison workbook (control-level only)
    CCIs resolving to nothing in the r5 catalog are dropped (counted in stats).
    """
    import xml.etree.ElementTree as ET

    if not CCI_XML_PATH.exists():
        return [], [], {"note": "CCI XML not found"}
    fname = CCI_XML_PATH.name
    tree = ET.parse(str(CCI_XML_PATH))
    root = tree.getroot()
    ns = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""

    def t(tag_name: str) -> str:
        return f"{{{ns}}}{tag_name}" if ns else tag_name

    appj_map = load_appj_absorption_map(catalog_ids)

    bridge_rows: List[dict] = []
    disa_rows: List[dict] = []
    seen_bridge: Set[Tuple[str, str, str]] = set()
    stats = {
        "cci_items": 0, "r5_native": 0, "r4_identity": 0, "appj_absorption": 0,
        "dropped_unresolvable": 0, "subpart_rows": 0,
    }

    for i, item in enumerate(root.iter(t("cci_item"))):
        cci = item.get("id", "").strip()
        if not cci:
            continue
        stats["cci_items"] += 1
        status = item.findtext(t("status"), default="") or ""
        definition = item.findtext(t("definition"), default="") or ""
        ctype = item.findtext(t("type"), default="") or ""

        r5_refs: List[str] = []
        r4_refs: List[str] = []
        refs_el = item.find(t("references"))
        if refs_el is not None:
            for ref in refs_el:
                title = ref.get("title", "")
                idx = (ref.get("index") or "").strip()
                if not idx:
                    continue
                if title == "NIST SP 800-53 Revision 5":
                    r5_refs.append(idx)
                elif title == "NIST SP 800-53 Revision 4":
                    r4_refs.append(idx)

        resolved: List[Tuple[str, Optional[str], str, str]] = []  # (ctrl, subpart, basis, raw)
        for idx in r5_refs:
            for ctrl, subpath in parse_cci_index(idx):
                if ctrl in catalog_ids:
                    resolved.append((ctrl, canon_subpart(ctrl, subpath), "r5_native", idx))
        if not resolved:
            for idx in r4_refs:
                for ctrl, subpath in parse_cci_index(idx):
                    if ctrl in catalog_ids:
                        resolved.append((ctrl, canon_subpart(ctrl, subpath), "r4_identity", idx))
                    else:
                        for r5c in appj_map.get(ctrl, []):
                            # control-level only; the absorption statement does not
                            # identify a sub-part — leave it blank, never guess.
                            resolved.append((r5c, None, "appj_absorption", idx))
        if not resolved:
            stats["dropped_unresolvable"] += 1
            continue

        r5_controls: Set[str] = set()
        for ctrl, subpart, basis, raw in resolved:
            r5_controls.add(ctrl)
            key = (cci, ctrl, subpart or "")
            if key in seen_bridge:
                continue
            seen_bridge.add(key)
            stats[basis] += 1
            if subpart:
                stats["subpart_rows"] += 1
            bridge_rows.append({
                "cci_id": cci,
                "r5_control": ctrl,
                "r5_subpart": subpart,
                "r4_ref_raw": raw,
                "basis": basis,
                "source_file": fname,
                "source_row": i,
            })

        disa_rows.append({
            "cci_id": cci,
            "definition": definition,
            "type": ctype,
            "status": status,
            "nist_rev4_refs": json.dumps(sorted(set(r4_refs))),
            "nist_rev5_refs": json.dumps(sorted(r5_controls)),
            "fetched_at": "",
        })

    bridge_rows.sort(key=lambda r: (r["cci_id"], r["r5_control"], r["r5_subpart"] or ""))
    disa_rows.sort(key=lambda r: r["cci_id"])
    stats["bridge_rows"] = len(bridge_rows)
    stats["distinct_controls"] = len({r["r5_control"] for r in bridge_rows})
    stats["distinct_cci"] = len({r["cci_id"] for r in bridge_rows})
    return bridge_rows, disa_rows, stats


def link_odps_to_subparts(
    odp_links: List[Tuple[str, str, Optional[str]]], conn
) -> int:
    """
    Backfill control_odps.r5_subpart from crosswalk ODP links.

    Each triple is (odp_id, control_id, r5_subpart).  When a matching
    control_odps row has r5_subpart IS NULL, we UPDATE it.  Returns the count
    of rows updated.
    """
    updated = 0
    for odp_id, control_id, r5_subpart in odp_links:
        if not r5_subpart:
            continue
        cur = conn.execute(
            "UPDATE control_odps SET r5_subpart = ?, link_basis = 'crosswalk_reference' "
            "WHERE odp_id = ? AND control_id = ? AND r5_subpart IS NULL",
            (r5_subpart, odp_id, control_id),
        )
        updated += cur.rowcount
    return updated


# ── STIG application layer (Phase 21) ────────────────────────────────────────
import gzip as _gzip  # noqa: E402  (local to the STIG loader; stdlib)

STIG_MAP_PATH = REPO_ROOT / "canonical-sources" / "source_data" / "stig" / "stig_cci_map.json.gz"
_CCI_TOKEN_RE = re.compile(r"^CCI-\d{6}$")


def load_stig_rules(catalog_ids: Set[str]) -> Tuple[List[dict], List[dict], List[dict], dict]:
    """
    Load the distilled STIG artifact (tools/stig_harvest.py output) into
    (catalog_rows, rule_rows, usage_rows, stats).

    catalog_rows -> stig_catalog, rule_rows -> stig_rules, usage_rows ->
    stig_cci_usage.  `in_bridge` is computed against the set of CCIs the caller
    already loaded into cci_bridge (passed as `catalog_ids` is the r5 control set;
    the bridge CCI set is loaded here directly from the artifact-independent
    disa list is NOT available, so in_bridge is resolved by the caller after
    cci_bridge exists — see build_db).  Guarded on artifact existence: absent
    artifact returns empty lists + {'skipped': ...} so offline rebuilds pass.

    STIG-cited CCIs that are malformed are counted and refused (never guessed).
    Deterministic: all rows sorted; ccis stored as sorted JSON.
    """
    if not STIG_MAP_PATH.exists():
        return [], [], [], {"skipped": "no stig_cci_map artifact"}
    with _gzip.open(STIG_MAP_PATH, "rt", encoding="utf-8") as f:
        data = json.load(f)
    benchmarks = data.get("benchmarks", {})
    catalog_rows: List[dict] = []
    rule_rows: List[dict] = []
    usage_stig: Dict[str, set] = {}
    usage_rules: Dict[str, int] = {}
    stats = {"benchmarks": 0, "rules": 0, "cci_citations": 0,
             "malformed_cci_citations": 0, "distinct_ccis": 0}
    for stig_id in sorted(benchmarks):
        b = benchmarks[stig_id]
        rules = b.get("rules", [])
        distinct: set = set()
        n_citations = 0
        for r in sorted(rules, key=lambda x: (x.get("group", ""), x.get("rule", ""))):
            ccis = []
            for c in r.get("ccis", []):
                if _CCI_TOKEN_RE.match(c):
                    ccis.append(c)
                else:
                    stats["malformed_cci_citations"] += 1
            ccis = sorted(set(ccis))
            n_citations += len(ccis)
            distinct.update(ccis)
            for c in ccis:
                usage_stig.setdefault(c, set()).add(stig_id)
                usage_rules[c] = usage_rules.get(c, 0) + 1
            rule_rows.append({
                "stig_id": stig_id,
                "group_id": r.get("group", ""),
                "rule_id": r.get("rule", ""),
                "version_id": r.get("version_id", ""),
                "severity": r.get("severity", ""),
                "title": r.get("title", ""),
                "ccis": json.dumps(ccis, ensure_ascii=False),
            })
        catalog_rows.append({
            "stig_id": stig_id,
            "title": b.get("title", ""),
            "version": str(b.get("version", "")),
            "release": str(b.get("release", "")),
            "benchmark_date": b.get("benchmark_date", ""),
            "type": b.get("type", "stig"),
            "rule_count": len(rules),
            "cci_citations": n_citations,
            "distinct_ccis": len(distinct),
            "trackr_title": b.get("trackr_title"),
            "source": b.get("source", ""),
            "source_zip": b.get("source_zip"),
        })
        stats["benchmarks"] += 1
        stats["rules"] += len(rules)
        stats["cci_citations"] += n_citations
    usage_rows = [{"cci_id": c, "n_stigs": len(usage_stig[c]),
                   "n_rules": usage_rules[c], "in_bridge": 0}
                  for c in sorted(usage_stig)]
    stats["distinct_ccis"] = len(usage_rows)
    stats["library"] = data.get("_meta", {}).get("library")
    return catalog_rows, rule_rows, usage_rows, stats
