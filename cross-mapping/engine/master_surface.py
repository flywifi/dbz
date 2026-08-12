"""
master_surface.py — assemble the all-in-one master mapping surface (Phase 19).

One row per unordered canonical framework pair (fw_a, native_a, fw_b, native_b),
unioned from every mapping surface in grc.db plus the Phase 19 pair loaders:

  framework_projection   native <-> NIST 800-53 control  (owner/NIST/hub/bundled)
  unified_mappings       NIST control -> target framework (catalog side)
  consensus_edges        third-party <-> third-party (strong/moderate only)
  OLIR pair loaders      PCI/ISO/171r3 <-> CSF 2.0, TSC <-> HITRUST
  ER production          aggregate co-occurrence counts (public ids only)

Arbitration (minority-report — dissent never dropped): the strongest tier wins
the primary row; every losing surface's claim is preserved verbatim in the
`corroboration` JSON column.  Tier order:

  owner_direct(1) > nist_stated(2) > owner_stated(3) > hub(4) > bundled(5)
  > consensus(6) > production_aggregate(7)

`owner_stated` (Phase 20) = the framework OWNER mapping their own controls to a
foreign target (CSA's CCM->800-53 OSCAL, SCF's 800-53 column) — authoritative
within the owner's audit scope (CSA STAR / SCF CAP) per the acceptance-authority
model, ranked below NIST-reviewed mappings.

Hygiene (CLAUDE.md non-negotiable): provider-proprietary ids (ER-N / REQ-N)
are refused at assembly time — a surface that ever supplies one raises.
FedRAMP r5 hub natives (baseline-annotated 800-53 ids like 'AC-10[H]') are
excluded: FedRAMP-as-audit is the 800-53 baseline itself and is served by the
baseline-flag scope surface, not by pair rows.  Consensus `single` (1-voter)
pairs are excluded from the master surface (queryable via `dbz_query consensus`).

Deterministic: sorted output; no wall-clock reads.  stdlib + sqlite only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import uncertainty  # type: ignore
from spine_normalize import normalize_tsc_id  # type: ignore

REPO_ROOT = _HERE.parent.parent
VOCAB_PATH = REPO_ROOT / "canonical-sources" / "framework_vocab.json"

_PROPRIETARY_RE = re.compile(r"\b(?:ER|REQ)-\d+\b")

NIST_LABEL = "NIST 800-53"

# The single authoritative tier order — dbz_query imports this (never copy it).
TIER_ORDER = ["owner_direct", "nist_stated", "owner_stated", "hub", "bundled",
              "consensus", "production_aggregate"]

# provenance -> (tier, rank, expected confidence or None)
TIER_MAP: Dict[str, Tuple[str, int, Optional[float]]] = {
    "cmmc171":            ("owner_direct", 1, 0.95),
    "direct_olir":        ("nist_stated", 2, 0.85),
    "direct_800_66":      ("nist_stated", 2, 0.85),
    "direct_csf2":        ("nist_stated", 2, 0.85),
    "direct_cprt_171r3":  ("nist_stated", 2, 0.85),
    "direct_cprt_172r3":  ("nist_stated", 2, 0.85),
    "olir_csf2_pair":     ("nist_stated", 2, 0.85),
    "ccm_oscal":          ("owner_stated", 3, 0.85),
    "scf_direct":         ("owner_stated", 3, 0.80),
    "hitrust_hub":        ("hub", 4, 0.65),
    "transitive_unified": ("hub", 4, 0.65),
    "aicpa_tsp_hub":      ("hub", 4, 0.65),
    "master_crosswalk":   ("bundled", 5, 0.60),
    "consensus":          ("consensus", 6, None),
    "production_aggregate": ("production_aggregate", 7, None),
}

_CONS_EXTENT_REL = {
    "equal": "equal", "a_subset_b": "subset", "b_subset_a": "superset",
    "intersect": "intersect", "atoms_disjoint": "unspecified",
    "no_spine_footprint": "unspecified",
}

# consensus_edges framework labels -> canonical (mirrors consensus_detector._PROJ_LABEL
# plus the non-projection labels; asserted against framework_labels in test_spine)
_CONSENSUS_TO_CANON = {
    "SOC 2 (TSC)": "SOC 2",
    "ISO 27001/2 (2022)": "ISO 27001/2 (2022)",
    "HIPAA Security": "HIPAA Security",
    "GDPR": "GDPR",
    "CIS v8": "CIS CSC v8.0",
    "NIST SP 800-171": "NIST SP 800-171 r2",
    "CMMC 2.0": "CMMC 2.0",
    "PCI DSS": "PCI DSS v4.0",
    "NIST CSF 2.0": "NIST CSF 2.0",
    "NIST 800-53": NIST_LABEL,
}

# ER frameworks whose native ids are PUBLIC and eligible for production aggregates.
# SOC 1 / SOC 2 / HIPAA ER natives are firm-local (proprietary) — never eligible.
_ER_PUBLIC = {"ISO 27001/2 (2022)": "ISO 27001/2 (2022)",
              "PCI DSS v4.0": "PCI DSS v4.0",
              "HITRUST": "HITRUST CSF"}


def load_label_rows() -> List[dict]:
    """framework_labels rows from framework_vocab.json's framework_aliases block
    (explicit aliases only — resolution falls back to identity)."""
    with open(VOCAB_PATH, encoding="utf-8") as f:
        vocab = json.load(f)
    block = vocab.get("framework_aliases", {}).get("canonical", {})
    rows: List[dict] = []
    for canonical in sorted(block):
        rows.append({"alias": canonical, "surface": "canonical", "canonical": canonical})
        for alias in sorted(set(block[canonical].get("aliases", []))):
            rows.append({"alias": alias, "surface": "alias", "canonical": canonical})
    for label in sorted(vocab.get("framework_aliases", {}).get(
            "deliberately_distinct", {}).get("labels", [])):
        rows.append({"alias": label, "surface": "distinct", "canonical": label})
    return rows


class LabelResolver:
    def __init__(self, rows: List[dict]):
        self._map = {r["alias"]: r["canonical"] for r in rows}
        self._lower = {r["alias"].lower(): r["canonical"] for r in rows}

    def canon(self, label: str) -> str:
        s = str(label).strip()
        return self._map.get(s) or self._lower.get(s.lower()) or s


def _pair_key(fw_a: str, id_a: str, fw_b: str, id_b: str):
    if (fw_a, id_a) <= (fw_b, id_b):
        return fw_a, id_a, fw_b, id_b
    return fw_b, id_b, fw_a, id_a


class _Claims:
    """Collects per-pair claims from every surface, then arbitrates."""

    def __init__(self):
        self.claims: Dict[tuple, List[dict]] = {}
        self.votes: Dict[tuple, int] = {}
        self.production: Dict[tuple, int] = {}
        self.anchors: Dict[tuple, Set[str]] = {}

    def add(self, fw_a, id_a, fw_b, id_b, *, provenance, relationship,
            relationship_basis, confidence, hop_count, needs_confirmation,
            source_ref, anchors=None):
        for v in (id_a, id_b):
            if _PROPRIETARY_RE.search(str(v)):
                raise ValueError(f"proprietary identifier refused at master assembly: framework pair {fw_a}<->{fw_b}")
        key = _pair_key(fw_a, str(id_a), fw_b, str(id_b))
        tier, rank, _c = TIER_MAP[provenance]
        self.claims.setdefault(key, []).append({
            "provenance": provenance, "tier": tier, "rank": rank,
            "relationship": relationship or "unspecified",
            "relationship_basis": relationship_basis,
            "confidence": confidence, "hop_count": hop_count,
            "needs_confirmation": int(needs_confirmation),
            "source": source_ref,
        })
        if anchors:
            self.anchors.setdefault(key, set()).update(anchors)

    @staticmethod
    def _evidence_state(tier: str, votes, production, corroborating: int) -> str:
        """Derived evidence-strength ladder (schema 3.13) — orthogonal to the
        provenance tier: the tier says HOW the edge was established, the state
        says HOW STRONGLY it is corroborated. Deterministic, from existing
        fields only (rules: protocol-layer/evidence-standards.md):

          oracle_confirmed   — the production ER oracle co-cites the pair
                               (production_support >= 1) or the edge IS
                               production data (production_aggregate tier)
          cross_validated    — >=1 corroborating non-winning surface, or
                               consensus votes >= 2
          columns_aligned    — a single directly-stated surface
                               (owner_direct / nist_stated / owner_stated / hub)
          asserted_by_source — a single compiled/bundled surface only

        Precedence: highest applicable state wins."""
        if (production or 0) >= 1 or tier == "production_aggregate":
            return "oracle_confirmed"
        if corroborating >= 1 or (votes or 0) >= 2:
            return "cross_validated"
        if tier in ("owner_direct", "nist_stated", "owner_stated", "hub"):
            return "columns_aligned"
        return "asserted_by_source"

    def rows(self) -> List[dict]:
        out: List[dict] = []
        for key in sorted(self.claims):
            fw_a, id_a, fw_b, id_b = key
            claims = sorted(self.claims[key],
                            key=lambda c: (c["rank"], -(c["confidence"] or 0.0),
                                           c["provenance"], c["source"]))
            primary, rest = claims[0], claims[1:]
            anchors = sorted(self.anchors.get(key, set()))
            uid = uncertainty.uncertainty_id(
                "master_pair", fw_a=fw_a, native_a=id_a, fw_b=fw_b, native_b=id_b,
                provenance=primary["provenance"])
            out.append({
                "fw_a": fw_a, "native_a": id_a, "fw_b": fw_b, "native_b": id_b,
                "relationship": primary["relationship"],
                "relationship_basis": primary["relationship_basis"],
                "tier": primary["tier"], "provenance": primary["provenance"],
                "confidence": primary["confidence"],
                "hop_count": primary["hop_count"],
                "needs_confirmation": primary["needs_confirmation"],
                "uncertainty_id": uid,
                "votes": self.votes.get(key),
                "production_support": self.production.get(key, 0),
                "shared_anchors": json.dumps(anchors[:20]) if anchors else None,
                "anchor_count": len(anchors) if anchors else 0,
                "corroboration": json.dumps(
                    [{k: c[k] for k in ("provenance", "tier", "confidence",
                                        "relationship", "source")} for c in rest],
                    sort_keys=True) if rest else None,
                "evidence_state": self._evidence_state(
                    primary["tier"], self.votes.get(key),
                    self.production.get(key, 0), len(rest)),
                "source_ref": primary["source"],
            })
        return out


def assemble(conn, csf2_pairs: Optional[List[dict]] = None,
             tsp_pairs: Optional[List[dict]] = None,
             ccm_cis_pairs: Optional[List[dict]] = None) -> Tuple[List[dict], dict]:
    """Build master_mappings rows from the loaded surfaces.  Pure over its
    inputs — reads grc.db tables + the pair lists, returns sorted rows."""
    labels = LabelResolver(load_label_rows())
    col = _Claims()
    stats = {"skipped_fedramp": 0, "skipped_consensus_single": 0,
             "unified_rows": 0, "projection_pairs": 0, "consensus_pairs": 0,
             "olir_pair_rows": 0, "tsp_pair_rows": 0, "er_aggregate_pairs": 0}

    # 1. framework_projection -> native <-> NIST control (collapse over sub-parts,
    #    keep best provenance per (native, control); sub-parts feed shared_anchors).
    best: Dict[tuple, dict] = {}
    for (fw, nat, ctrl, sub, rel, basis, prov, conf, hop, needs, sfile, srow) in conn.execute(
            """SELECT framework, native_id, r5_control, r5_subpart, relationship,
                      relationship_basis, provenance, confidence, hop_count,
                      needs_confirmation, source_file, source_row
               FROM framework_projection WHERE status <> 'refuted'"""):
        if fw == "FedRAMP r5":
            stats["skipped_fedramp"] += 1
            continue
        canon_fw = labels.canon(fw)
        if canon_fw == "SOC 2":
            # one TSC native dialect: 'AICPA 2017 CC6.1' (hub) -> 'CC6.1'
            # (consensus / master-crosswalk form); firm-local ids never parse.
            tsc = normalize_tsc_id(nat)
            if tsc:
                nat = tsc
        key = (canon_fw, nat, ctrl)
        tier_rank = TIER_MAP.get(prov, ("hub", 3, None))[1]
        cur = best.get(key)
        if cur is None or (tier_rank, -(conf or 0)) < (cur["rank"], -(cur["conf"] or 0)):
            best[key] = {"rank": tier_rank, "conf": conf, "prov": prov, "rel": rel,
                         "basis": basis, "hop": hop, "needs": needs,
                         "src": f"{sfile}:{srow}", "subs": set()}
        if sub:
            best[key]["subs"].add(sub)
    for (canon_fw, nat, ctrl), b in best.items():
        col.add(canon_fw, nat, NIST_LABEL, ctrl,
                provenance=b["prov"], relationship=b["rel"],
                relationship_basis=b["basis"], confidence=b["conf"],
                hop_count=b["hop"], needs_confirmation=b["needs"],
                source_ref=b["src"], anchors=b["subs"])
    stats["projection_pairs"] = len(best)

    # 2. unified_mappings (catalog side) -> NIST control <-> target framework.
    for (ctrl, fw, tid, rel, msrc) in conn.execute(
            """SELECT DISTINCT control_id, framework, target_id,
                      relationship_type, mapping_source
               FROM unified_mappings WHERE framework <> 'DISA CCI'"""):
        canon_fw = labels.canon(fw)
        prov = "transitive_unified"
        rel_norm = {"Equal": "equal", "Subset": "subset", "Superset": "superset",
                    "Intersecting": "intersect"}.get(str(rel), "unspecified")
        basis = ("co_membership" if str(rel) == "transitive_via_hitrust"
                 else "source_stated" if rel_norm != "unspecified" else "derived_cardinality")
        col.add(canon_fw, tid, NIST_LABEL, ctrl,
                provenance=prov, relationship=rel_norm, relationship_basis=basis,
                confidence=0.65, hop_count=2, needs_confirmation=1,
                source_ref=f"unified_mappings:{msrc or ''}")
        stats["unified_rows"] += 1

    # 3. consensus_edges (strong + moderate) -> third-party pairs.
    for (fa, na, fb, nb, votes, tier, extent, atoms, prod) in conn.execute(
            """SELECT fw_a, native_a, fw_b, native_b, votes, tier, extent,
                      shared_atoms, production_support
               FROM consensus_edges WHERE tier IN ('strong', 'moderate')"""):
        ca, cb = _CONSENSUS_TO_CANON.get(fa, fa), _CONSENSUS_TO_CANON.get(fb, fb)
        anchors = json.loads(atoms) if atoms else []
        key = _pair_key(labels.canon(ca), na, labels.canon(cb), nb)
        col.add(labels.canon(ca), na, labels.canon(cb), nb,
                provenance="consensus",
                relationship=_CONS_EXTENT_REL.get(extent or "", "unspecified"),
                relationship_basis="multi_source_consensus",
                confidence=None, hop_count=None, needs_confirmation=1,
                source_ref=f"consensus_edges:{tier}", anchors=anchors)
        col.votes[key] = max(col.votes.get(key, 0), votes or 0)
        if prod:
            col.production[key] = max(col.production.get(key, 0), prod)
        stats["consensus_pairs"] += 1
    stats["skipped_consensus_single"] = conn.execute(
        "SELECT COUNT(*) FROM consensus_edges WHERE tier='single'").fetchone()[0]

    # 3b. Shared 800-53 anchors for CROSS pairs (phase-36 finding F-8).
    #
    # An anchor is the r5 control BOTH sides of a cross-framework pair project onto —
    # the concrete answer to "why do you think these two are related?". It is only a
    # meaningful concept for cross edges: on a spoke edge (X <-> a NIST control) the
    # control is an endpoint, not a shared pivot, so writing it into shared_anchors
    # would be circular. Spoke evidence is carried by source_ref instead.
    #
    # Computed from framework_projection, which is where both sides' spine footprints
    # already live — no new source, no new judgment.
    _proj_anchor_cache: Dict[str, Dict[str, Set[str]]] = {}

    def _anchors_for(fw: str, native: str) -> Set[str]:
        by_native = _proj_anchor_cache.get(fw)
        if by_native is None:
            by_native = {}
            for n, ctrl in conn.execute(
                    "SELECT native_id, r5_control FROM framework_projection WHERE framework=?",
                    (fw,)):
                by_native.setdefault(str(n), set()).add(str(ctrl))
            _proj_anchor_cache[fw] = by_native
        return by_native.get(str(native), set())

    def shared_anchors(fw_a: str, id_a: str, fw_b: str, id_b: str) -> List[str]:
        if fw_a == NIST_LABEL or fw_b == NIST_LABEL:
            return []
        return sorted(_anchors_for(fw_a, id_a) & _anchors_for(fw_b, id_b))

    # 4. OLIR CSF-2.0 pairs (PCI / ISO / 171r3 <-> CSF2) + AICPA TSP <-> HITRUST.
    for p in csf2_pairs or []:
        col.add(labels.canon(p["fw"]), p["native"], "NIST CSF 2.0", p["csf2_id"],
                provenance="olir_csf2_pair", relationship="intersect",
                relationship_basis="source_stated", confidence=0.85, hop_count=1,
                needs_confirmation=0, source_ref=f"cprt_csf2_olir:{p['olir_name']}",
                anchors=shared_anchors(labels.canon(p["fw"]), p["native"],
                                       "NIST CSF 2.0", p["csf2_id"]))
        stats["olir_pair_rows"] += 1
    for p in tsp_pairs or []:
        col.add("SOC 2", p["tsc_id"], "HITRUST CSF", p["hitrust_id"],
                provenance="aicpa_tsp_hub", relationship="intersect",
                relationship_basis="co_membership", confidence=0.65, hop_count=1,
                needs_confirmation=1,
                source_ref="Mapping-of-2017-AICPA-TSP-to-HITRUST-CSFv11.4.0.xlsx",
                anchors=shared_anchors("SOC 2", p["tsc_id"], "HITRUST CSF", p["hitrust_id"]))
        stats["tsp_pair_rows"] += 1
    # CCM <-> CIS 8.1 from CSA's OSCAL mapping-collection (owner-stated, Phase 20)
    for p in ccm_cis_pairs or []:
        col.add("CSA CCM v4", p["ccm_id"], "CIS CSC v8.0", p["cis_id"],
                provenance="ccm_oscal", relationship=p["relationship"],
                relationship_basis="source_stated", confidence=0.85, hop_count=1,
                needs_confirmation=0, source_ref="ccm-oscal-mappings.json",
                anchors=shared_anchors("CSA CCM v4", p["ccm_id"], "CIS CSC v8.0", p["cis_id"]))
        stats["ccm_cis_pair_rows"] = stats.get("ccm_cis_pair_rows", 0) + 1

    # 5. ER production aggregates — public-id frameworks only, counts only.
    er_counts: Dict[tuple, int] = {}
    for (fa, na, fb, nb, n) in conn.execute(
            """SELECT m1.framework, m1.native_id, m2.framework, m2.native_id,
                      COUNT(DISTINCT m1.er_id)
               FROM er_mappings m1 JOIN er_mappings m2 ON m1.er_id = m2.er_id
               WHERE m1.framework < m2.framework
               GROUP BY 1, 2, 3, 4"""):
        if fa not in _ER_PUBLIC or fb not in _ER_PUBLIC:
            continue
        key = _pair_key(labels.canon(_ER_PUBLIC[fa]), na,
                        labels.canon(_ER_PUBLIC[fb]), nb)
        er_counts[key] = er_counts.get(key, 0) + n
    for key, n in sorted(er_counts.items()):
        fw_a, id_a, fw_b, id_b = key
        col.production[key] = max(col.production.get(key, 0), n)
        if key not in col.claims:  # aggregate-only pair: production tier primary
            col.add(fw_a, id_a, fw_b, id_b,
                    provenance="production_aggregate", relationship="unspecified",
                    relationship_basis="production_cooccurrence", confidence=None,
                    hop_count=None, needs_confirmation=1,
                    source_ref="er_mappings:aggregate",
                    anchors=shared_anchors(fw_a, id_a, fw_b, id_b))
        stats["er_aggregate_pairs"] += 1

    rows = col.rows()
    stats["rows"] = len(rows)
    stats["by_tier"] = {}
    for r in rows:
        stats["by_tier"][r["tier"]] = stats["by_tier"].get(r["tier"], 0) + 1
    return rows, stats
