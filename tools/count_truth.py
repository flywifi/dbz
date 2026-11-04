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
    if key == "changelog_latest":
        # Registered in phase 46: phase 45 bumped the changelog to 0.12.1 while VERSION
        # stayed 0.12.0, and nothing was watching. The latest changelog heading is the
        # authority; the VERSION file is the cited restatement that must match it.
        src = (ROOT / "changes" / "CHANGELOG.md").read_text(encoding="utf-8")
        m = re.search(r"^## \[(\d+\.\d+\.\d+)\]", src, re.MULTILINE)
        return (m.group(1), None) if m else (None, "no version heading in CHANGELOG.md")
    if key.startswith("manifest:"):
        if not MANIFEST_PATH.exists():
            return None, "grc_manifest.json not built (fresh checkout)"
        rc = _load(MANIFEST_PATH).get("row_counts", {})
        name = key.split(":", 1)[1]
        return (rc[name], None) if name in rc else (None, f"row_counts has no '{name}'")
    if key == "scorer:weights":
        # dict-valued claim: every (dimension, weight) in the scorer code must appear
        # as a table row in the cited protocol doc — code and doc cannot drift apart.
        import importlib.util
        sp = ROOT / "cross-mapping" / "engine" / "score_output.py"
        spec = importlib.util.spec_from_file_location("_score_output", sp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.WEIGHTS, None
    if key == "db:cci_confirmed":
        # The repository's headline deliverable. Registered in phase 43: it had been restated
        # by hand in the docs while count_truth guarded thirteen lesser numbers, because the
        # manifest's row_counts list was hand-kept and never learned the table.
        if not DB_PATH.exists():
            return None, "grc.db not built (fresh checkout)"
        conn = sqlite3.connect(DB_PATH)
        n = conn.execute("SELECT COUNT(*) FROM framework_cci_confirmation "
                         "WHERE verdict='confirmed'").fetchone()[0]
        conn.close()
        return n, None
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
def _context_findings(cid: str, spec: dict, value, rel: str, text: str) -> list:
    """Every-occurrence mode (phase 50). Each context pattern has ONE capture group; every match in
    the cited file must equal the current value. Lifts the phase-43 'states it somewhere' limit
    for the claims that opt in via "context_patterns"."""
    out = []
    if not isinstance(value, int):
        return out
    for pat in spec.get("context_patterns") or []:
        rx = re.compile(pat)
        for ln, line in enumerate(text.splitlines(), 1):
            for m in rx.finditer(line):
                got = m.group(1).replace(",", "")
                if got.isdigit() and int(got) != value:
                    out.append((rel, cid, f"line {ln} states {m.group(1)} (current {value}): {line.strip()[:90]}"))
    return out


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
        for rel in spec["cited_in"]:
            path = ROOT / rel
            if not path.exists():
                findings.append((rel, cid, f"cited file missing (current value: {value})"))
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if isinstance(value, dict):
                for k, v in sorted(value.items()):
                    row = re.compile(re.escape(k) + r"\s*\|\s*" + re.escape(f"{v:.2f}"))
                    if not row.search(text):
                        findings.append((rel, cid, f"missing/mismatched row for {k} = {v:.2f}"))
                continue
            pats = _patterns_for(value)
            if not any(p.search(text) for p in pats):
                findings.append((rel, cid, f"does not state current value {value}"))
            findings += _context_findings(cid, spec, value, rel, text)
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
            # RFC 2606/6761 reserved names are unreachable by definition — test
            # fixtures, never fetch targets; provenance does not apply.
            if host.endswith((".invalid", ".test", ".localhost")) or \
                    host in ("example.com", "example.org", "example.net") or \
                    host.endswith((".example.com", ".example.org", ".example.net", ".example")):
                continue
            if host and host not in allowed:
                findings.append((str(path.relative_to(ROOT)), url))
    return sorted(set(findings))


# ── CLI ──────────────────────────────────────────────────────────────────────

def selftest_context() -> int:
    """Every-occurrence mode must fail on the real phase-49 defect: README.md at 910e28c stated the
    current feed count once in a table and a stale one in prose, and the horizon count likewise.
    The fixtures are those lines verbatim; the patterns are the registered ones."""
    claims = _load(CLAIMS_PATH)["claims"]
    stale = ("| **Keep-current** | 162 official sources watched for changes, plus a horizon of 77 anticipated future revisions |\n"
             "dbz watches **161 official sources** (`canonical-sources/feed_registry.json`) for version changes\n"
             "and keeps a **horizon** of 76 anticipated future revisions (`canonical-sources/anticipated_updates.json`)\n")
    clean = stale.replace("**161 official", "**162 official").replace("of 76 ", "of 77 ")
    cases = [("feeds_count", 162, stale, 1), ("horizon_count", 77, stale, 1),
             ("feeds_count", 162, clean, 0), ("horizon_count", 77, clean, 0)]
    bad = 0
    for cid, value, text, want in cases:
        got = len(_context_findings(cid, claims[cid], value, "README.md", text))
        bad += got != want
        print(f"  [{'ok' if got == want else 'FAIL'}] {cid} on {'stale' if text is stale else 'clean'} text: "
              f"{got} finding(s) (want {want})")
    print(f"[selftest] every-occurrence claims: {len(cases) - bad}/{len(cases)} passed")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="doc-number truth + URL provenance checks")
    ap.add_argument("--list", action="store_true", help="show all claims + current values")
    ap.add_argument("--check", action="store_true", help="(default) fail on drift")
    ap.add_argument("--selftest", action="store_true",
                    help="prove every-occurrence mode fails on the real phase-49 stale lines")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest_context()

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
