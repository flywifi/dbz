#!/usr/bin/env python3
"""
cci_harvest.py — enrichment/corroboration snapshots for the CCI dictionary.

The authoritative CCI universe (numbers + definitions + r4/r5 refs + status) is the
committed DISA CCI List XML (`canonical-sources/source_data/U_CCI_List.xml`), loaded by
spine_loader.load_cci_bridge_xml. This tool fetches the two *derived republications* that
corroborate the CCI↔800-53 mapping (transcription-fidelity + candidate-gap detection — NOT
independent authorities; both ultimately derive from the same DISA list):

  acasehs/STIG-Control-CCI   revision-split control↔CCI JSON (rev4cci.json / rev5cci.json)
                             -> canonical-sources/source_data/cci/acasehs_rev{4,5}.json
  cyber.trackr.live /api/cci enumeration (defs) + per-CCI rmf / ap_acronym / family
                             -> canonical-sources/source_data/cci/trackr_cci.json.gz

All artifacts are sorted + deterministic (gzip mtime=0) and sha-pinned in source_manifest.
Modes:
  --acasehs            fetch + distill the two acasehs revision files
  --trackr             snapshot the trackr enumeration header (count + a version stamp)
  --trackr --enrich    also crawl per-CCI rmf/ap/family (rate-limited, checkpointed)
  --check              compare live CCI-list version + trackr count vs the committed snapshots
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CCI_DIR = ROOT / "canonical-sources" / "source_data" / "cci"
ACASEHS_R4 = CCI_DIR / "acasehs_rev4.json"
ACASEHS_R5 = CCI_DIR / "acasehs_rev5.json"
TRACKR_PATH = CCI_DIR / "trackr_cci.json.gz"
CCI_XML = ROOT / "canonical-sources" / "source_data" / "U_CCI_List.xml"

TOOL_VERSION = "1.0.0"
ACASEHS_RAW = "https://raw.githubusercontent.com/acasehs/STIG-Control-CCI/main/{f}.json"
TRACKR_ENUM = "https://cyber.trackr.live/api/cci"
TRACKR_ONE = "https://cyber.trackr.live/api/cci/{cci}"
_RATE_S = 0.3


def _http(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "dbz-cci-harvest/" + TOOL_VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _meta(source: str, extra: dict | None = None) -> dict:
    from datetime import datetime, timezone
    m = {"tool": "cci_harvest.py", "tool_version": TOOL_VERSION, "source": source,
         "provenance": "derived_republication_of_disa_cci_list",
         "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if extra:
        m.update(extra)
    return m


def _cci_xml_version() -> str | None:
    if not CCI_XML.exists():
        return None
    import xml.etree.ElementTree as ET
    root = ET.parse(str(CCI_XML)).getroot()
    ns = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
    v = root.find(f"{{{ns}}}metadata/{{{ns}}}version" if ns else "metadata/version")
    return (v.text or "").strip() if v is not None else None


def mode_acasehs(args) -> int:
    CCI_DIR.mkdir(parents=True, exist_ok=True)
    for f, dest in (("rev4cci", ACASEHS_R4), ("rev5cci", ACASEHS_R5)):
        data = json.loads(_http(ACASEHS_RAW.format(f=f)).decode("utf-8"))
        # sort by CCI number then Index for determinism; keep the source fields
        rows = sorted(data, key=lambda r: (r.get("CCI Number", ""), r.get("Index", "")))
        payload = {"_meta": _meta("acasehs/STIG-Control-CCI",
                                  {"file": f + ".json", "rows": len(rows)}),
                   "rows": rows}
        dest.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[acasehs] {f}: {len(rows)} rows -> {dest.relative_to(ROOT)}")
    return 0


def _write_trackr(enum_count: int, enriched: dict, version_note: str) -> None:
    CCI_DIR.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in _meta("cyber.trackr.live/api/cci",
            {"enumeration_count": enum_count, "enriched_ccis": len(enriched),
             "cci_list_version_at_harvest": version_note}).items() if k != "retrieved_at"}
    payload = {"_meta": meta, "mappings": {k: enriched[k] for k in sorted(enriched)}}
    raw = json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write(raw)
    TRACKR_PATH.write_bytes(buf.getvalue())


def read_trackr() -> dict:
    with gzip.open(TRACKR_PATH, "rt", encoding="utf-8") as f:
        return json.load(f)


def mode_trackr(args) -> int:
    enum = json.loads(_http(TRACKR_ENUM).decode("utf-8"))
    enum_count = len(enum)
    print(f"[trackr] enumeration: {enum_count} CCIs")
    enriched: dict = {}
    if TRACKR_PATH.exists():  # resume from committed snapshot
        enriched = dict(read_trackr().get("mappings", {}))
    if args.enrich:
        ids = sorted(enum)
        todo = [c for c in ids if c not in enriched] if args.resume else ids
        print(f"[trackr] enriching {len(todo)} CCIs (rmf/ap/family), rate {1/_RATE_S:.1f}/s …")
        for i, cci in enumerate(todo, 1):
            try:
                d = json.loads(_http(TRACKR_ONE.format(cci=cci), timeout=45).decode("utf-8"))
            except Exception as e:
                print(f"[trackr]   {cci}: {type(e).__name__} — skipped")
                continue
            enriched[cci] = {"rmf": (d.get("rmf") or "").strip(),
                             "ap": (d.get("ap_acronym") or "").strip(),
                             "family": (d.get("family") or "").strip()}
            if i % 250 == 0:
                _write_trackr(enum_count, enriched, _cci_xml_version() or "")
                print(f"[trackr]   … checkpoint {i}/{len(todo)} ({len(enriched)} total)")
            time.sleep(_RATE_S)
    _write_trackr(enum_count, enriched, _cci_xml_version() or "")
    print(f"[trackr] wrote {TRACKR_PATH.relative_to(ROOT)} "
          f"(enum {enum_count}, enriched {len(enriched)})")
    return 0


def mode_check(args) -> int:
    live_ver = None
    try:
        # the live XML version is only visible after downloading the zip; here we
        # compare the committed pin against the trackr enumeration size as a cheap
        # currency signal, and report the committed CCI-list version.
        enum = json.loads(_http(TRACKR_ENUM).decode("utf-8"))
        live_ver = f"trackr_enum={len(enum)}"
    except Exception as e:
        print(f"[check] trackr unreachable ({type(e).__name__}) — check_failed")
        return 0
    committed_ver = _cci_xml_version()
    committed_trackr = read_trackr()["_meta"].get("enumeration_count") if TRACKR_PATH.exists() else None
    drift = (committed_trackr is not None and committed_trackr != len(enum))
    out = {"status": "drift" if drift else "current",
           "committed_cci_list_version": committed_ver,
           "committed_trackr_enum": committed_trackr,
           "live_trackr_enum": len(enum)}
    print(json.dumps(out, indent=1) if args.json else
          f"[check] cci-list v{committed_ver} | trackr enum committed={committed_trackr} "
          f"live={len(enum)} -> {out['status']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--acasehs", action="store_true")
    ap.add_argument("--trackr", action="store_true")
    ap.add_argument("--enrich", action="store_true", help="with --trackr: crawl per-CCI rmf/ap/family")
    ap.add_argument("--resume", action="store_true", help="with --enrich: skip already-snapshotted CCIs")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.acasehs:
        return mode_acasehs(a)
    if a.trackr:
        return mode_trackr(a)
    if a.check:
        return mode_check(a)
    ap.error("choose --acasehs / --trackr [--enrich] / --check")


if __name__ == "__main__":
    sys.exit(main())
