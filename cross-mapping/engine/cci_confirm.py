#!/usr/bin/env python3
"""
cci_confirm.py — the framework -> CCI confirmation layer (Phase 38).

The objective of this repository is that every framework converges onto **confirmed CCI
mappings**: HITRUST, CSA, the NIST OLIRs and the STIGs cross-referencing one another until
a CCI mapping is witnessed rather than merely reachable.

Before this module the convergence existed only one layer down. `cci_mapping_corroboration`
already votes on each CCI's 800-53 anchor (witnesses: disa_bridge / acasehs_r4 / acasehs_r5 /
trackr_rmf / stig_exercised -> 4,285 confirmed). Above it, frameworks reached CCIs only by
transitive reachability — framework -> r5 sub-part -> cci_bridge -> CCI. That is a JOIN, not a
confirmation: it says a path exists, never that anyone checked it.

This module builds `framework_cci_confirmation`: one row per (framework, native_id, cci_id)
carrying independent witness counts and a derived verdict.

WITNESS INDEPENDENCE is the whole point, so each witness comes from a different kind of
evidence and none is derivable from another:

  w_framework_sources      how many distinct mapping PUBLISHERS put this framework control on
                           this 800-53 anchor (framework_projection.provenance)
  w_cci_anchor_confirmed   the CCI's own 800-53 anchor is multi-witness confirmed
                           (cci_mapping_corroboration.verdict = 'confirmed')
  w_stig_exercised         a real STIG rule tests this CCI in the field (stig_cci_usage)
  w_consensus              a DIFFERENT framework independently agrees on this control
                           (consensus_edges, strong/moderate only)
  w_subpart_precision      the anchor is a sub-part, not a whole control — a PRECISION
                           witness, deliberately not counted as agreement

Ten of the fourteen frameworks have exactly one mapping source (phase-36 finding F-4), so
publisher-vs-publisher agreement is unavailable for most of them. That is exactly why the
verdict counts the other witness types, which do not depend on how many framework sources exist.

`reachable` must never be presented as a confirmed mapping — separating those two is the
reason this table exists.

Deterministic, stdlib + sqlite only.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Set, Tuple

# Only strong/moderate consensus counts as a witness; `single` (1 voter) is not agreement.
_CONSENSUS_TIERS = ("strong", "moderate")

VERDICTS = ("confirmed", "corroborated", "reachable", "weak")


def consensus_key(native_id: str) -> str:
    """Coarse control identity for matching the consensus surface to the projection.

    The two surfaces write different granularities for the same control:
      HIPAA  consensus '164.308'  vs projection '164.308(a)(1)(ii)(A)'
      CIS    consensus '1.0'      vs projection '1.01'
    Coarsening to the leading control token lets them meet. This is a WITNESS join —
    "does another framework agree in this control area" — and is deliberately coarse; it
    is never stored and never used as an identifier. (Same discipline as
    spine_normalize.corroboration_key, added in phase 37 for finding F-6.)
    """
    s = str(native_id or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{3}\.\d{3})", s)          # 45 CFR section: 164.308(a)(1) -> 164.308
    if m:
        return m.group(1)
    m = re.match(r"^(\d+)\.(\d+)", s)            # dotted: 1.01 -> 1.1 ; 5.15 -> 5.15
    if m:
        return f"{int(m.group(1))}.{int(m.group(2))}"
    m = re.match(r"^(\d+)", s)                   # bare leading number
    if m:
        return m.group(1)
    return s.upper()


def _consensus_controls(conn, canon: Dict[str, str]) -> Dict[Tuple[str, str], int]:
    """(canonical framework, consensus_key) -> number of DIFFERENT frameworks agreeing.

    consensus_edges is framework<->framework, so each side of an edge witnesses the other.
    Its labels are the consensus vocabulary ('CIS v8', 'SOC 2 (TSC)'), which are mapped to
    the projection's canonical labels before use — without that the witness silently never
    fires, which is the label-dialect defect phase 36 recorded as F-6."""
    out: Dict[Tuple[str, str], Set[str]] = {}
    qs = ",".join("?" * len(_CONSENSUS_TIERS))
    for fa, na, fb, nb in conn.execute(
            f"SELECT fw_a, native_a, fw_b, native_b FROM consensus_edges "
            f"WHERE tier IN ({qs})", _CONSENSUS_TIERS):
        ca, cb = canon.get(str(fa), str(fa)), canon.get(str(fb), str(fb))
        out.setdefault((ca, consensus_key(na)), set()).add(cb)
        out.setdefault((cb, consensus_key(nb)), set()).add(ca)
    # a framework never witnesses itself
    return {k: len(v - {k[0]}) for k, v in out.items()}


def _verdict(w_sources: int, anchor_confirmed: int, stig: int, consensus: int,
             baseline: int = 0, olir: int = 0, scf: int = 0) -> str:
    """Derived mechanically — no per-row judgment.

    Agreement witnesses are: a second independent PUBLISHER, a STIG that actually exercises
    the CCI, and another framework agreeing via consensus. Sub-part precision is not an
    agreement witness and never promotes a verdict on its own.
    """
    # CCI-LEVEL witnesses speak to this exact CCI: a second publisher placing the control on
    # this anchor, or a STIG rule actually exercising the CCI. The consensus witness is
    # weaker — it matches at control granularity (see consensus_key), so it attests that the
    # control area is agreed, not that this specific CCI is right. It may therefore SUPPORT a
    # confirmation but never carry one alone. (Measured 2026-08-13: no confirmed row rests on
    # consensus alone; this rule makes that a guarantee rather than a property of the data.)
    cci_level = (1 if w_sources >= 2 else 0) + (1 if stig else 0)
    # baseline (owner scope statement) and olir_composed (two-hop NIST-published path)
    # are CONTROL-granularity like consensus: they support, never carry alone.
    agreement = (cci_level + (1 if consensus else 0)
                 + (1 if baseline else 0) + (1 if olir else 0) + (1 if scf else 0))
    if not anchor_confirmed:
        # the CCI's own anchor is disa_only / candidate — nothing above it can be confirmed
        return "weak"
    if agreement >= 2 and cci_level >= 1:
        return "confirmed"
    if agreement >= 1:
        return "corroborated"
    return "reachable"


def build_rows(conn) -> Tuple[List[dict], dict]:
    """Assemble framework_cci_confirmation. Returns (rows, stats)."""
    anchor_confirmed: Set[str] = {
        r[0] for r in conn.execute(
            "SELECT cci_id FROM cci_mapping_corroboration WHERE verdict='confirmed'")}
    anchor_known: Set[str] = {
        r[0] for r in conn.execute("SELECT DISTINCT cci_id FROM cci_mapping_corroboration")}
    stig_ccis: Set[str] = {
        r[0] for r in conn.execute("SELECT DISTINCT cci_id FROM stig_cci_usage")}
    # consensus labels -> projection canonical labels (the master surface's own map)
    try:
        from master_surface import _CONSENSUS_TO_CANON as _C2C  # type: ignore
    except Exception:
        _C2C = {}
    consensus = _consensus_controls(conn, dict(_C2C))

    # framework control -> distinct publishers, counted at COARSE control granularity
    # (phase-39 WS-2). Exact native_id keying was defeated by the F-6 id-dialect class:
    # cmmc171 writes 'AC.L1-3.1.1(a.)' while the hub writes 'AC.L1.3.1.1', so the same
    # control's two publishers never met (measured: CMMC 0 multi-publisher natives exact,
    # 17 via the coarse key; ISO 4 vs 23). The coarse key is a WITNESS join only —
    # stored ids are untouched (the phase-37 discipline).
    from spine_normalize import corroboration_key  # type: ignore
    # Keyed PER ANCHOR CONTROL: a second publisher counts only if it placed the same
    # (coarse) framework control on the SAME 800-53 control the CCI hangs under —
    # "both mapped this control somewhere" is not agreement. (This also tightens a
    # latent phase-38 imprecision that exact-id keying happened to mask.)
    pubs: Dict[Tuple[str, str, str], Set[str]] = {}
    for fw, nat, r5c, prov in conn.execute(
            "SELECT framework, native_id, r5_control, provenance FROM framework_projection "
            "WHERE status <> 'refuted'"):
        k = corroboration_key(str(fw), str(nat)) or str(nat)
        pubs.setdefault((str(fw), k, str(r5c)), set()).add(str(prov))
    cci_anchor_ctls: Dict[str, Set[str]] = {}
    for cci, r5c in conn.execute("SELECT cci_id, r5_control FROM cci_bridge"):
        cci_anchor_ctls.setdefault(str(cci), set()).add(str(r5c))

    # OLIR-composed witness (phase-39 WS-3): X <-> CSF-2.0 pairs NIST published (OLIR),
    # composed with NIST's own CSF-2.0 -> 800-53 mapping. Two hops, both NIST-published,
    # matched per anchor: the witness fires only when the composed path lands on the SAME
    # 800-53 control this CCI hangs under. Control-granularity -> supports, never carries.
    olir_x: Dict[Tuple[str, str], Set[str]] = {}
    for fa, na, fb, nb in conn.execute(
            "SELECT fw_a, native_a, fw_b, native_b FROM master_mappings "
            "WHERE provenance='olir_csf2_pair'"):
        if fa == "NIST CSF 2.0":
            fw_x, nat_x, csf = str(fb), str(nb), str(na)
        elif fb == "NIST CSF 2.0":
            fw_x, nat_x, csf = str(fa), str(na), str(nb)
        else:
            continue
        k = corroboration_key(fw_x, nat_x) or nat_x
        olir_x.setdefault((fw_x, k), set()).add(csf)
    csf2_ctls: Dict[str, Set[str]] = {}
    for nat, r5c in conn.execute(
            "SELECT native_id, r5_control FROM framework_projection "
            "WHERE framework='NIST CSF 2.0' AND provenance='direct_csf2'"):
        csf2_ctls.setdefault(str(nat), set()).add(str(r5c))

    # SCF fan-out witness (phase-40): SCF->X composed with SCF->800-53, per anchor.
    # Same honesty rule as olir_composed: the composition is ours -> supports-only.
    scf_x: Dict[Tuple[str, str], Set[str]] = {}
    try:
        for fw_x, nat_x, r5c in conn.execute(
                "SELECT framework, native_id, r5_control FROM scf_composed_edges"):
            k = corroboration_key(str(fw_x), str(nat_x)) or str(nat_x)
            scf_x.setdefault((str(fw_x), k), set()).add(str(r5c))
    except Exception:
        pass

    def scf_witness(fw: str, ck_nat: str, cci: str) -> int:
        anchors = cci_anchor_ctls.get(cci, set())
        return 1 if scf_x.get((fw, ck_nat), set()) & anchors else 0

    def olir_witness(fw: str, ck_nat: str, cci: str) -> int:
        anchors = cci_anchor_ctls.get(cci, set())
        for csf in olir_x.get((fw, ck_nat), ()):
            if csf2_ctls.get(csf, set()) & anchors:
                return 1
        return 0

    # (framework, native, cci) -> subpart_anchored?
    pairs: Dict[Tuple[str, str, str], bool] = {}
    for fw, nat, cci in conn.execute("""
            SELECT DISTINCT fp.framework, fp.native_id, cb.cci_id
            FROM framework_projection fp
            JOIN cci_bridge cb ON cb.r5_subpart = fp.r5_subpart
            WHERE fp.r5_subpart IS NOT NULL AND fp.status <> 'refuted'
              AND fp.framework <> 'FedRAMP r5'"""):
        pairs[(str(fw), str(nat), str(cci))] = True
    for fw, nat, cci in conn.execute("""
            SELECT DISTINCT fp.framework, fp.native_id, cb.cci_id
            FROM framework_projection fp
            JOIN cci_bridge cb ON cb.r5_control = fp.r5_control
            WHERE fp.r5_subpart IS NULL AND fp.status <> 'refuted'
              AND fp.framework <> 'FedRAMP r5'"""):
        pairs.setdefault((str(fw), str(nat), str(cci)), False)

    rows: List[dict] = []
    stats = {v: 0 for v in VERDICTS}
    stats["pairs"] = 0
    stats["anchor_unknown"] = 0
    for (fw, nat, cci), subpart in sorted(pairs.items()):
        ck_nat = corroboration_key(fw, nat) or nat
        w_sources = max((len(pubs.get((fw, ck_nat, a), ()))
                         for a in cci_anchor_ctls.get(cci, ())), default=0)
        a_conf = 1 if cci in anchor_confirmed else 0
        if cci not in anchor_known:
            stats["anchor_unknown"] += 1
        stig = 1 if cci in stig_ccis else 0
        cons = consensus.get((fw, consensus_key(nat)), 0)
        olir = olir_witness(fw, ck_nat, cci)
        scf = scf_witness(fw, ck_nat, cci)
        verdict = _verdict(w_sources, a_conf, stig, cons, baseline=0, olir=olir, scf=scf)
        witnesses = []
        if w_sources >= 2:
            witnesses.append(f"framework_sources:{w_sources}")
        if a_conf:
            witnesses.append("cci_anchor_confirmed")
        if stig:
            witnesses.append("stig_exercised")
        if cons:
            witnesses.append(f"consensus:{cons}")
        if olir:
            witnesses.append("olir_composed")
        if scf:
            witnesses.append("scf_composed")
        if subpart:
            witnesses.append("subpart_precision")
        rows.append({
            "framework": fw, "native_id": nat, "cci_id": cci,
            "w_framework_sources": w_sources,
            "w_cci_anchor_confirmed": a_conf,
            "w_stig_exercised": stig,
            "w_consensus": cons,
            "w_subpart_precision": 1 if subpart else 0,
            "w_baseline_authoritative": 0,
            "w_olir_composed": olir,
            "w_scf_composed": scf,
            "verdict": verdict,
            "witnesses": json.dumps(sorted(witnesses)),
        })
        stats[verdict] += 1
        stats["pairs"] += 1
    # ── FedRAMP r5: derived from the OWNER's baseline flags, not graded as a foreign
    # framework (phase-39 WS-1). FedRAMP-as-audit IS the 800-53 baseline
    # (master_surface docstring); the authoritative scope statement is the
    # baseline_low/moderate/high flags on controls+enhancements. The 91,690 hub rows
    # with baseline-annotated natives are redundant re-statements and are excluded above.
    fed_pairs: Dict[Tuple[str, str], Set[str]] = {}   # (control_id, cci) -> baseline levels
    for table in ("controls", "enhancements"):
        idcol = "nist_id" if table == "controls" else "id"
        for level in ("low", "moderate", "high"):
            for (ctl, cci) in conn.execute(
                    f"SELECT t.{idcol}, cb.cci_id FROM {table} t "
                    f"JOIN cci_bridge cb ON cb.r5_control = t.{idcol} "
                    f"WHERE t.baseline_{level} = 1"):
                fed_pairs.setdefault((str(ctl), str(cci)), set()).add(level)
    for (ctl, cci), levels in sorted(fed_pairs.items()):
        a_conf = 1 if cci in anchor_confirmed else 0
        stig = 1 if cci in stig_ccis else 0
        verdict = _verdict(1, a_conf, stig, 0, baseline=1)
        witnesses = [f"baseline:{lv}" for lv in sorted(levels)]
        if a_conf:
            witnesses.append("cci_anchor_confirmed")
        if stig:
            witnesses.append("stig_exercised")
        rows.append({
            "framework": "FedRAMP r5", "native_id": ctl, "cci_id": cci,
            "w_framework_sources": 1,
            "w_cci_anchor_confirmed": a_conf,
            "w_stig_exercised": stig,
            "w_consensus": 0,
            "w_subpart_precision": 0,
            "w_baseline_authoritative": 1,
            "w_olir_composed": 0,
            "w_scf_composed": 0,
            "verdict": verdict,
            "witnesses": json.dumps(sorted(witnesses)),
        })
        stats[verdict] += 1
        stats["pairs"] += 1
    return rows, stats


if __name__ == "__main__":  # manual inspection
    import sqlite3
    import sys
    from pathlib import Path
    db = Path(__file__).resolve().parents[2] / "cross-mapping" / "output" / "grc.db"
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    _rows, _stats = build_rows(c)
    print(json.dumps(_stats, indent=1))
    sys.exit(0)
