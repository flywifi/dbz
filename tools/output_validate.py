#!/usr/bin/env python3
"""
output_validate.py — deterministic fabrication/leak gate for GRC analysis output.

dbz gates its repo files (health_audit) but agent-produced ANALYSIS output —
crosswalks, gap analyses, overlap narratives from the skills or from a chat —
is where a fabricated control id, an unsourced "92% overlap", or an
overconfident "definitively maps" does real damage. This tool checks any JSON
or markdown output file mechanically against the actual catalog:

  (a) ID reality (HIGH "possible fabrication"): every CCI-nnnnnn must exist in
      disa_ccis; every 800-53-shaped id (AC-2, AC-2(3)) must exist in
      controls/enhancements; every claimed framework name must canonicalize
      through the grc.db framework_labels table (framework_vocab.json when no
      DB is built). Unknown -> the id may be invented; resolution is to ingest
      the source or tag the id [unverified] — never to whitelist ad hoc.
  (b) Unsourced numbers (MEDIUM): percentages and large counts must sit near a
      citation marker (per grc.db / a provenance tier / a source name) or carry
      an explicit [unverified]/[estimated] label.
  (c) Confidence-tier alignment (MEDIUM "overconfident phrasing"): sentences
      using confirmed/established/definitive about a framework pair must be
      backed by a master_mappings edge in an authoritative tier
      (owner_direct / nist_stated / owner_stated); consensus- or bundled-only
      support does not justify that language. Needs grc.db; skipped otherwise.
  (d) Leak scan (HIGH): reuses health_audit._PUB_PATTERNS (session links,
      emails, provider-proprietary ER-/REQ- ids) — imported, not copied.

Exit 1 when any HIGH finding exists; the JSON report always carries
human_review_required: true when findings exist. Degrades honestly without a
built grc.db (DB-dependent checks are skipped with a note, never guessed).

Usage:
  python3 tools/output_validate.py REPORT.md [--format json|table]
  python3 tools/output_validate.py --selftest
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "cross-mapping" / "output" / "grc.db"
VOCAB_PATH = ROOT / "canonical-sources" / "framework_vocab.json"
FIXTURES = ROOT / "cross-mapping" / "tests" / "fixtures" / "output_validate"

sys.path.insert(0, str(ROOT / "tools"))
from health_audit import _PUB_PATTERNS  # single source of truth for leak patterns

CCI_RE = re.compile(r"\bCCI-(\d{6})\b")
C80053_RE = re.compile(r"\b([A-Z]{2}-\d{1,2})(\((\d{1,2})\))?\b")
NUMBER_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%|\b\d{1,3}(?:,\d{3})+\b|\$\s?\d[\d,]*\b")
CITE_MARKERS = re.compile(
    r"per grc\.db|owner_direct|nist_stated|owner_stated|\bhub\b|\bbundled\b|"
    r"\bconsensus\b|production_aggregate|\[unverified\]|\[estimated\]|"
    r"source_manifest|BENCHMARK|oracle|measured", re.IGNORECASE)
CONFIDENT_RE = re.compile(
    r"[^.\n]*\b(confirmed|established|definitive(?:ly)?)\b[^.\n]*", re.IGNORECASE)
AUTHORITATIVE_TIERS = {"owner_direct", "nist_stated", "owner_stated"}
CITE_WINDOW = 220  # chars around a number in which a citation marker must appear


def _load_db():
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(DB_PATH)


def _known_ids(conn):
    controls = {r[0] for r in conn.execute("SELECT nist_id FROM controls")}
    controls |= {r[0] for r in conn.execute("SELECT id FROM enhancements")}
    ccis = {r[0] for r in conn.execute("SELECT cci_id FROM disa_ccis")}
    labels = {r[0].lower() for r in conn.execute("SELECT alias FROM framework_labels")}
    labels |= {r[0].lower() for r in conn.execute("SELECT canonical FROM framework_labels")}
    return controls, ccis, labels


def _vocab_frameworks():
    try:
        v = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
        names = set()
        for k, vals in v.items():
            if isinstance(vals, list):
                names.update(str(x).lower() for x in vals)
            elif isinstance(vals, str):
                names.add(vals.lower())
        return names
    except Exception:
        return set()


def validate_text(text: str, conn=None):
    """Returns (findings, notes). Each finding: {severity, check, detail}."""
    findings, notes = [], []
    controls = ccis = labels = None
    if conn is not None:
        controls, ccis, labels = _known_ids(conn)
    else:
        notes.append("grc.db not built — ID-reality limited to framework_vocab; tier check skipped")
        labels = _vocab_frameworks()

    # (a) ID reality
    for m in sorted(set(CCI_RE.findall(text))):
        cid = f"CCI-{m}"
        if ccis is not None and cid not in ccis:
            findings.append({"severity": "HIGH", "check": "id_reality",
                             "detail": f"{cid} not in the DISA CCI dictionary — possible fabrication"})
    if controls is not None:
        for base, _, enh in sorted(set(C80053_RE.findall(text))):
            cid = f"{base}({enh})" if enh else base
            if cid not in controls:
                findings.append({"severity": "HIGH", "check": "id_reality",
                                 "detail": f"{cid} not in the 800-53 catalog — possible fabrication"})

    # (b) unsourced numbers
    for m in NUMBER_RE.finditer(text):
        lo, hi = max(0, m.start() - CITE_WINDOW), m.end() + CITE_WINDOW
        if not CITE_MARKERS.search(text[lo:hi]):
            findings.append({"severity": "MEDIUM", "check": "unsourced_number",
                             "detail": f"'{m.group(0)}' has no nearby citation marker "
                                       "(tag [estimated]/[unverified] or cite the source)"})

    # (c) confidence-tier alignment
    if conn is not None and labels:
        for sm in CONFIDENT_RE.finditer(text):
            sent = sm.group(0)
            hits = sorted((l for l in labels if len(l) > 3 and l in sent.lower()),
                          key=lambda s: (-len(s), s))
            mentioned = []  # keep the longest, drop aliases that are substrings of a pick
            for l in hits:
                if not any(l in p or p in l for p in mentioned):
                    mentioned.append(l)
            if len(mentioned) >= 2:
                q = ("SELECT tier FROM master_mappings WHERE "
                     "(lower(fw_a) LIKE ? AND lower(fw_b) LIKE ?) OR "
                     "(lower(fw_a) LIKE ? AND lower(fw_b) LIKE ?) LIMIT 500")
                a, b = f"%{mentioned[0]}%", f"%{mentioned[1]}%"
                tiers = {r[0] for r in conn.execute(q, (a, b, b, a))}
                if tiers and not (tiers & AUTHORITATIVE_TIERS):
                    findings.append({
                        "severity": "MEDIUM", "check": "overconfident_phrasing",
                        "detail": f"high-confidence wording about {mentioned[0]}/{mentioned[1]} "
                                  f"but support is {sorted(tiers)} only (no authoritative tier)"})

    # (d) leak scan — imported patterns
    for pat, label in _PUB_PATTERNS:
        m = pat.search(text)
        if m:
            findings.append({"severity": "HIGH", "check": "leak",
                             "detail": f"{label}: '{m.group(0)[:40]}'"})
    return findings, notes


def validate_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    conn = _load_db()
    try:
        findings, notes = validate_text(text, conn)
    finally:
        if conn:
            conn.close()
    high = sum(1 for f in findings if f["severity"] == "HIGH")
    return {"file": str(path), "findings": findings, "notes": notes,
            "high": high, "medium": len(findings) - high,
            "human_review_required": bool(findings)}


def selftest():
    """Fixtures assert the four behaviors; exit non-zero on any mismatch."""
    expect = {
        "clean_report.md": lambda r: r["high"] == 0 and r["medium"] == 0,
        "fabricated_ids.md": lambda r: (
            any(f["check"] == "id_reality" and f["severity"] == "HIGH" for f in r["findings"])
            if DB_PATH.exists()  # without a build, id reality can't fire — the leak still must
            else any(f["check"] == "leak" for f in r["findings"])),
        "unsourced_number.md": lambda r: any(f["check"] == "unsourced_number"
                                             for f in r["findings"]) and r["high"] == 0,
        "overconfident_consensus.md": lambda r: (
            any(f["check"] == "overconfident_phrasing" for f in r["findings"])
            if DB_PATH.exists() else True),
    }
    failures = 0
    for name, check in expect.items():
        r = validate_file(FIXTURES / name)
        status = "ok" if check(r) else "FAIL"
        if status == "FAIL":
            failures += 1
        print(f"  {status}: {name} (high={r['high']} medium={r['medium']})")
        if not DB_PATH.exists() and name == "overconfident_consensus.md":
            print("        (tier check skipped without a built grc.db)")
    print("selftest:", "PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="deterministic GRC output validator")
    ap.add_argument("file", nargs="?", help="JSON or markdown output file to validate")
    ap.add_argument("--format", choices=["json", "table"], default="table")
    ap.add_argument("--selftest", action="store_true", help="run the fixture battery")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.file:
        ap.error("provide a file or --selftest")
    report = validate_file(Path(a.file))
    if a.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for n in report["notes"]:
            print(f"  [note] {n}")
        for f in report["findings"]:
            print(f"  [{f['severity']:6}] {f['check']:22} {f['detail']}")
        print(f"\n  {report['high']} HIGH / {report['medium']} MEDIUM — "
              f"human_review_required={report['human_review_required']}")
    return 1 if report["high"] else 0


if __name__ == "__main__":
    sys.exit(main())
