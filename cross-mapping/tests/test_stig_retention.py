#!/usr/bin/env python3
"""Offline tests for tools/stig_harvest.py's phase-50 retention path — synthetic DISA library
zips, no network. Pins: a benchmark DISA drops from its library is KEPT and flagged (never
deleted); a benchmark kept across two refreshes keeps the library it was last seen in; the gz map
is byte-deterministic; per-title zips record the ZIP name as source_zip; --via-trackr parses."""

import io
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import stig_harvest as sh  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok: {label}")


def xccdf(bid: str, version: str, release: str, n_rules: int) -> bytes:
    rules = "".join(
        f'<Group id="V-{i}"><Rule id="SV-{i}r1_rule" severity="medium"><version>X-{i}</version>'
        f'<title>rule {i}</title><ident system="http://cyber.mil/cci">CCI-{i:06d}</ident></Rule></Group>'
        for i in range(1, n_rules + 1))
    return (f'<?xml version="1.0"?><Benchmark xmlns="http://checklists.nist.gov/xccdf/1.1" id="{bid}">'
            f'<title>{bid} title</title><version>{version}</version>'
            f'<plain-text id="release-info">Release: {release} Benchmark Date: 01 Apr 2026</plain-text>'
            f'{rules}</Benchmark>').encode()


def member_zip(name: str, bid: str, version: str, release: str, n: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{name[:-4]}_Manual-xccdf.xml", xccdf(bid, version, release, n))
    return buf.getvalue()


def library(path: Path, members: list) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, bid, v, r, n in members:
            z.writestr(name, member_zip(name, bid, v, r, n))
    return path


def test_retention_across_two_refreshes():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        lib1 = library(d / "U_SRG-STIG_Library_April_2026.zip",
                       [("U_A_V1R1_STIG.zip", "A_STIG", "1", "1", 3), ("U_B_V2R1_STIG.zip", "B_STIG", "2", "1", 2)])
        lib2 = library(d / "U_SRG-STIG_Library_October_2026.zip", [("U_A_V1R2_STIG.zip", "A_STIG", "1", "2", 4)])
        lib3 = library(d / "U_SRG-STIG_Library_January_2027.zip", [("U_A_V1R3_STIG.zip", "A_STIG", "1", "3", 4)])
        april, _ = sh.distill_library(lib1, {})
        october, _ = sh.distill_library(lib2, {})
        ok(set(october) == {"A_STIG"}, "the October library no longer carries B_STIG (DISA dropped it)")
        m2, kept = sh.retain_absent(october, april, lib1.stem, lib2.stem)
        ok(kept == ["B_STIG"] and set(m2) == {"A_STIG", "B_STIG"}, "B_STIG is kept, not deleted")
        ok(m2["B_STIG"]["lifecycle"] == "not_in_current_library"
           and m2["B_STIG"]["last_library"] == "U_SRG-STIG_Library_April_2026",
           "kept benchmark is flagged with the library it was last seen in")
        ok(m2["A_STIG"]["lifecycle"] == "current" and m2["A_STIG"]["release"] == "2",
           "carried benchmark is current at the new release")
        january, _ = sh.distill_library(lib3, {})
        m3, kept3 = sh.retain_absent(january, m2, lib2.stem, lib3.stem)
        ok(m3["B_STIG"]["last_library"] == "U_SRG-STIG_Library_April_2026",
           "a benchmark kept across two refreshes keeps its true last library (not the previous one)")
        meta = {"library": lib3.stem}
        ok(sh._map_bytes(m3, meta) == sh._map_bytes(m3, meta), "the gz map is byte-deterministic")
        cat = sh._catalog_from(m3, {}, meta)
        ok(cat["harvested"]["B_STIG"]["lifecycle"] == "not_in_current_library",
           "stig_catalog.json carries the lifecycle flag")


def test_title_zip_records_zip_name():
    blob = member_zip("U_A_V1R5_STIG.zip", "A_STIG", "1", "5", 2)
    stats = {"malformed_cci_citations": 0, "xml_parse_errors": 0, "benchmarks_without_rules": 0}
    b = sh._parse_title_zip(blob, "A_STIG", "U_A_V1R5_STIG.zip", stats)
    ok(b and b["source_zip"] == "U_A_V1R5_STIG.zip" and b["release"] == "5",
       "per-title refresh records the ZIP name as source_zip (the next V/R rewrite needs it)")
    ok(sh._parse_title_zip(blob, "OTHER_STIG", "x.zip", stats) is None,
       "a zip without the expected benchmark id is refused (probe-or-keep)")


def test_parser_accepts_documented_flags():
    a = sh.build_parser().parse_args(["--via-trackr", "--titles-file", "t.txt", "--flush-every", "5"])
    ok(a.titles_file == "t.txt" and a.flush_every == 5,
       "--titles-file / --flush-every parse (pre-phase-50: AttributeError on --via-trackr)")
    a = sh.build_parser().parse_args(["--full", "--from-zip", "x.zip", "--retain-absent", "--refresh-final"])
    ok(a.retain_absent and a.refresh_final, "--retain-absent / --refresh-final parse")


if __name__ == "__main__":
    for fn in (test_retention_across_two_refreshes, test_title_zip_records_zip_name,
               test_parser_accepts_documented_flags):
        fn()
    print(f"\nstig retention tests: {PASS} assertions PASS")
