#!/usr/bin/env python3
"""
count_truth.py — machine-checked doc numbers + URL provenance.

Every load-bearing number cited in README/docs is registered in
canonical-sources/doc_claims.json with the authoritative source it is recomputed
from. `--check` recomputes each value and verifies every cited file still states
it; drift is a blocking finding. The checker NEVER edits docs — the fix is a
human doc edit (that friction is the feature: the prose gets re-read in context).

DB-dependent claims resolve from the build artifacts (grc_manifest.json / grc.db)
WHEN PRESENT and are skipped with a printed note when absent — CI runs on a fresh
checkout with no build, so the check degrades honestly instead of failing.

check_url_provenance(): every https?:// literal in tools/*.py and
cross-mapping/engine/*.py must target a host declared in one of the canonical
registries (feed_registry, crawl_seeds, source_manifest, anticipated_updates) or
in tools/url-allowlist.json (each entry with a reason). Host-level match,
warning severity (promotion to blocking is a later, deliberate step).

Stdlib only (sqlite3 included) — health_audit imports these check functions.

Usage:
  python3 tools/count_truth.py --check   # default; exit 1 on drift
  python3 tools/count_truth.py --list    # show all claims + current values
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIMS_PATH = ROOT / "canonical-sources" / "doc_claims.json"
ALLOWLIST_PATH = ROOT / "tools" / "url-allowlist.json"
MANIFEST_PATH = ROOT / "cross-mapping" / "output" / "grc_manifest.json"
DB_PATH = ROOT / "cross-mapping" / "output" / "grc.db"

_URL_RE = re.compile(r"https?://[^\s\"'`<>)\]}]+")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ── value resolvers ──────────────────────────────────────────────────────────

def _resolve_value(key: str):
    """Return (value, None) or (None, skip_reason)."""
    if key == "feeds_count":
        return len(_load(ROOT / "canonical-sources" / "feed_registry.json")["feeds"]), None
    if key == "horizon_count":
        return len(_load(ROOT / "canonical-sources" / "anticipated_updates.json")["records"]), None
    if key == "schema_version":
        src = (ROOT / "cross-mapping" / "engine" / "build_db.py").read_text(encoding="utf-8")
        m = re.search(r'SCHEMA_VERSION\s*=\s*"([^"]+)"', src)
        return (m.group(1), None) if m else (None, "SCHEMA_VERSION not found in build_db.py")
    if key.startswith("manifest:"):
        if not MANIFEST_PATH.exists():
            return None, "grc_manifest.json not built (fresh checkout)"
        rc = _load(MANIFEST_PATH).get("row_counts", {})
        name = key.split(":", 1)[1]
        return (rc[name], None) if name in rc else (None, f"row_counts has no '{name}'")
    if key == "db:master_frameworks":
        if not DB_PATH.exists():
            return None, "grc.db not built (fresh checkout)"
        conn = sqlite3.connect(DB_PATH)
        n = conn.execute(
            "SELECT COUNT(DISTINCT fw) FROM (SELECT fw_a fw FROM master_mappings "
            "UNION SELECT fw_b FROM master_mappings)").fetchone()[0]
        conn.close()
        return n, None
    return None, f"unknown value_from '{key}'"


def _patterns_for(value):
    """Regexes a cited file must match: the plain and thousands-comma renderings,
    boundary-guarded so 160 never matches inside 1600."""
    s = re.escape(str(value))
    tail = r"(?!\d)(?!,\d{3})"  # no digit continuation; not a prefix of a longer comma-group number
    pats = [re.compile(r"(?<![\d.,])" + s + tail)]
    if isinstance(value, int) and value >= 1000:
        pats.append(re.compile(r"(?<![\d.,])" + re.escape(f"{value:,}") + tail))
    return pats


# ── checks (importable by health_audit) ──────────────────────────────────────

def check_doc_claims():
    """Returns (findings, skips): findings = [(file, claim_id, value)] drift;
    skips = [(claim_id, reason)] honestly-skipped claims."""
    findings, skips = [], []
    claims = _load(CLAIMS_PATH)["claims"]
    for cid, spec in sorted(claims.items()):
        value, skip = _resolve_value(spec["value_from"])
        if skip:
            skips.append((cid, skip))
            continue
        pats = _patterns_for(value)
        for rel in spec["cited_in"]:
            path = ROOT / rel
            if not path.exists():
                findings.append((rel, cid, f"cited file missing (current value: {value})"))
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if not any(p.search(text) for p in pats):
                findings.append((rel, cid, f"does not state current value {value}"))
    return findings, skips


def _registry_hosts():
    hosts = set()
    for rel in ("canonical-sources/feed_registry.json",
                "canonical-sources/crawl_seeds.json",
                "canonical-sources/source_manifest.json",
                "canonical-sources/anticipated_updates.json"):
        p = ROOT / rel
        if not p.exists():
            continue
        for url in _URL_RE.findall(p.read_text(encoding="utf-8", errors="replace")):
            host = url.split("//", 1)[1].split("/", 1)[0].lower()
            hosts.add(host)
    return hosts


def check_url_provenance():
    """Returns [(file, url)] for code URL literals whose host is neither
    registry-declared nor allowlisted."""
    allowed = set(_registry_hosts())
    if ALLOWLIST_PATH.exists():
        allowed |= {h.lower() for h in _load(ALLOWLIST_PATH)["allowed_hosts"]}
    findings = []
    scan = sorted((ROOT / "tools").glob("*.py")) + sorted(
        (ROOT / "cross-mapping" / "engine").glob("*.py"))
    for path in scan:
        text = path.read_text(encoding="utf-8", errors="replace")
        for url in _URL_RE.findall(text):
            host = url.split("//", 1)[1].split("/", 1)[0].lower()
            host = host.split("{", 1)[0]  # template hosts: match the literal prefix
            if host and host not in allowed:
                findings.append((str(path.relative_to(ROOT)), url))
    return sorted(set(findings))


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description="doc-number truth + URL provenance checks")
    ap.add_argument("--list", action="store_true", help="show all claims + current values")
    ap.add_argument("--check", action="store_true", help="(default) fail on drift")
    a = ap.parse_args(argv)

    if a.list:
        claims = _load(CLAIMS_PATH)["claims"]
        for cid, spec in sorted(claims.items()):
            value, skip = _resolve_value(spec["value_from"])
            shown = value if skip is None else f"(skipped: {skip})"
            print(f"  {cid:22} = {shown}   cited in {len(spec['cited_in'])} file(s)")
        return 0

    findings, skips = check_doc_claims()
    for cid, reason in skips:
        print(f"  [skip] {cid}: {reason}")
    url_findings = check_url_provenance()
    for f, url in url_findings:
        print(f"  [warn] undeclared URL host in {f}: {url}")
    if findings:
        print("\n[DOC CLAIM DRIFT] — fix the doc (or re-register the claim):")
        for rel, cid, msg in findings:
            print(f"  FAIL {rel}: claim '{cid}' {msg}")
        return 1
    print(f"\n[count-truth OK] {len(_load(CLAIMS_PATH)['claims'])} claims "
          f"({len(skips)} skipped without a build), "
          f"{len(url_findings)} URL provenance warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
