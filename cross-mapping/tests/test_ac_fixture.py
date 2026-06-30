#!/usr/bin/env python3
"""
Quick smoke-test against the AC-family fixture.

Tests schema shape without requiring the full source spreadsheets.
Run:
    python cross-mapping/tests/test_ac_fixture.py
"""
import json
import sys
from pathlib import Path

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "AC_fixture.json"


def test_fixture_schema():
    with open(_FIXTURE, encoding="utf-8") as f:
        data = json.load(f)

    assert "AC-1" in data, "AC-1 missing"
    assert "AC-2" in data, "AC-2 missing"

    ac2 = data["AC-2"]

    # Identity
    assert ac2["schema_version"] == "1.1.0", f"schema_version: {ac2['schema_version']}"
    assert ac2["id"] == "AC-2"
    assert ac2["family"] == "AC"
    assert ac2["title"] == "Account Management"

    # Parameters
    assert isinstance(ac2["parameters"], list), "parameters must be list"
    assert len(ac2["parameters"]) > 0, "AC-2 must have assignment parameters"
    for p in ac2["parameters"]:
        assert "id" in p and "type" in p and "label" in p, f"param missing fields: {p}"

    # Baselines
    bl = ac2["baselines"]
    assert isinstance(bl, dict)
    assert bl.get("low") is True
    assert bl.get("moderate") is True
    assert bl.get("high") is True

    # Compliance scope
    scope = ac2["compliance_scope"]
    assert isinstance(scope["fedramp_levels"], list)
    assert "low" in scope["fedramp_levels"]
    assert isinstance(scope["mapped_frameworks"], list)
    assert scope["framework_count"] >= 1

    # CCIs
    assert isinstance(ac2["mapped_ccis"], list)
    assert len(ac2["mapped_ccis"]) > 0, "AC-2 must have CCI mappings"
    import re
    for cci in ac2["mapped_ccis"]:
        assert re.match(r"^CCI-\d+$", cci), f"bad CCI format: {cci}"

    # Unified mappings
    unified = ac2["unified_mappings"]
    assert isinstance(unified, list)
    assert len(unified) > 0, "AC-2 must have unified_mappings"
    frameworks_present = {m["framework"] for m in unified}
    assert "DISA CCI" in frameworks_present, "DISA CCI not in unified_mappings"
    assert "ISO/IEC 27001:2022" in frameworks_present, "ISO 27001 not in unified_mappings"
    assert "CMMC 2.0 / NIST 800-171" in frameworks_present, "CMMC not in unified_mappings"
    assert "HITRUST CSF" in frameworks_present, "HITRUST not in unified_mappings"

    for m in unified:
        for field in ("framework", "control_id", "relationship_type", "direction", "mapping_source"):
            assert field in m, f"unified mapping missing '{field}': {m}"

    # Enhancements
    enhs = ac2["enhancements"]
    assert isinstance(enhs, list)
    assert len(enhs) > 0, "AC-2 should have enhancements"
    enh = enhs[0]
    assert "schema_version" in enh
    assert "unified_mappings" in enh
    assert "compliance_scope" in enh

    print("[✓] test_fixture_schema PASSED")


def test_crosswalk_atom():
    """Verify the crosswalk atom script produces valid output."""
    ingestion_dir = Path(__file__).resolve().parent.parent / "nist-catalog" / "output"
    scripts_dir = Path(__file__).resolve().parent.parent.parent / "skills" / "atoms" / "compliance-crosswalk" / "scripts"

    if not (ingestion_dir / "NIST_800_53_AC.json").exists():
        print("[skip] test_crosswalk_atom — AC catalog not built yet")
        return

    sys.path.insert(0, str(scripts_dir))
    from crosswalk import crosswalk_control

    result = crosswalk_control(
        source_control_id="AC-2",
        catalog_path=ingestion_dir / "NIST_800_53_AC.json",
        target_frameworks=["ISO/IEC 27001:2022", "HITRUST CSF"],
    )

    assert result["tool"] == "compliance-crosswalk"
    assert result["source_control"]["id"] == "AC-2"
    assert len(result["mappings"]) > 0
    assert result["human_review_required"] is True

    print(f"[✓] test_crosswalk_atom PASSED ({len(result['mappings'])} mappings returned)")


if __name__ == "__main__":
    failures = 0
    for test in [test_fixture_schema, test_crosswalk_atom]:
        try:
            test()
        except Exception as e:
            print(f"[✗] {test.__name__} FAILED: {e}")
            failures += 1

    sys.exit(failures)
