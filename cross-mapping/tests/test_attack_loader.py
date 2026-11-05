#!/usr/bin/env python3
"""Offline tests for the phase-51 ATT&CK loader (MITRE TAXII + CTID NIST 800-53 rev5 mapping).
Pins: CTID control ids normalise to the catalog form; only direct 'mitigates' mappings are written;
an unmapped technique stays blank (no parent inheritance, no keyword guess); a technique CTID mapped
under another name carries a review note; deprecated/revoked objects are dropped; the newest
collection version is stamped; no local path leaks into provenance; build_db keeps parent links."""

import ast
import json
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "engine"
sys.path.insert(0, str(ENGINE))
import attack_stix_loader as al  # noqa: E402


def _shipped_load_attack_data():
    """build_db.load_attack_data, taken from the shipped source. Importing build_db pulls in pandas,
    which the health workflow does not install (the first 0.16.0 CI run went red on exactly that
    import); the function itself needs only json and Path."""
    src = (ENGINE / "build_db.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "load_attack_data")
    ns = {"json": json, "Path": Path}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "build_db.py", "exec"), ns)
    return ns["load_attack_data"]

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok: {label}")


def ap(tid, name, sub=False, deprecated=False, revoked=False, tactic="initial-access"):
    return {"type": "attack-pattern", "id": f"attack-pattern--{tid}", "name": name, "x_mitre_is_subtechnique": sub,
            "x_mitre_deprecated": deprecated, "revoked": revoked, "description": name,
            "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": tactic}],
            "external_references": [{"source_name": "mitre-attack", "external_id": tid}]}


CTID = {"metadata": {"attack_version": "16.1", "mapping_framework": "nist_800_53", "mapping_framework_version": "rev5",
                     "last_update": "04/16/2025"},
        "mapping_objects": [
            {"mapping_type": "mitigates", "capability_id": "AC-02", "attack_object_id": "T1078", "attack_object_name": "Valid Accounts"},
            {"mapping_type": "mitigates", "capability_id": "IA-02", "attack_object_id": "T1078", "attack_object_name": "Valid Accounts"},
            {"mapping_type": "mitigates", "capability_id": "AC-02", "attack_object_id": "T1078", "attack_object_name": "Valid Accounts"},
            {"mapping_type": "mitigates", "capability_id": "CM-07", "attack_object_id": "T1176", "attack_object_name": "Browser Extensions"},
            {"mapping_type": "non_mappable", "capability_id": None, "attack_object_id": "T1496.002", "attack_object_name": "Bandwidth Hijacking"},
            {"mapping_type": "mitigates", "capability_id": "SI-04", "attack_object_id": "T1999", "attack_object_name": "Gone"}]}
OBJECTS = [ap("T1078", "Valid Accounts"), ap("T1078.001", "Default Accounts", sub=True), ap("T1176", "Software Extensions"),
           ap("T1999", "Gone", deprecated=True), ap("T1998", "Revoked", revoked=True),
           {"type": "x-mitre-collection", "x_mitre_version": "19.1", "modified": "2026-05-12T00:00:00Z"},
           {"type": "x-mitre-collection", "x_mitre_version": "20.0", "modified": "2026-10-12T00:00:00Z"}]


class F:
    def __init__(self, body):
        self.body = body
        self.status = 200
        self.headers = {}


def test_normalisation():
    ok(al._norm_ctrl("AC-02") == "AC-2" and al._norm_ctrl("SI-04(04)") == "SI-4(4)" and al._norm_ctrl("x") is None,
       "CTID ids normalise to the catalog form (AC-02 -> AC-2, SI-04(04) -> SI-4(4))")


def test_pipeline():
    al.fetchkit.fetch = lambda url, **k: F(json.dumps(CTID).encode())
    al.taxii_objects = lambda t, page=100: [o for o in OBJECTS if o["type"] == t]
    res = al.ATTACKLoader().run(dry_run=True)
    by = {t["technique_id"]: t for t in res["techniques"]}
    ok(res["_attack_version"] == "20.0", "the newest collection version is stamped (20.0, not 19.1)")
    ok(set(by) == {"T1078", "T1078.001", "T1176"}, "deprecated and revoked techniques are dropped")
    ok(by["T1078"]["nist_controls"] == ["AC-2", "IA-2"], "direct CTID 'mitigates' mappings, deduplicated and normalised")
    ok(by["T1078.001"]["nist_controls"] == [], "an unmapped sub-technique stays blank (no parent inheritance)")
    ok("nist_mapping_note" in by["T1176"] and "Browser Extensions" in by["T1176"]["nist_mapping_note"]
       and "nist_mapping_note" not in by["T1078"], "a technique mapped under its 16.1 name carries a review note; an unchanged one does not")
    md = res["metadata"]
    ok(md["total_unmapped_left_blank"] == 1 and md["total_mapping_notes"] == 1 and md["used_fallback"] is False,
       "metadata counts blanks and notes; no fallback")
    ok(md["source_stix_url"].startswith("https://attack-taxii.mitre.org/") and "file:" not in json.dumps(md),
       "provenance names the issuer endpoint, never a local path")
    ok(md["nist_mapping_source"]["mapping_attack_version"] == "16.1", "the mapping's ATT&CK version (skew) is recorded")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "a.json"
        p.write_text(json.dumps(res), encoding="utf-8")
        rows = {r["technique_id"]: r for r in _shipped_load_attack_data()(p)}
    ok(rows["T1078.001"]["parent_id"] == "T1078", "build_db keeps the parent link the loader writes (sub_technique_of)")


if __name__ == "__main__":
    test_normalisation()
    test_pipeline()
    print(f"\nattack loader tests: {PASS} assertions PASS")
