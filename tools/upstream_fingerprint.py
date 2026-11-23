#!/usr/bin/env python3
"""
upstream_fingerprint.py — does the issuer still serve what this repository committed?

A source that the issuer edits in place (same URL, same version label) never moves a release tag,
so the release comparison in standards_refresh cannot see it. Phase 54 measured seven such changes
that no check reported: the FedRAMP consolidated rules (2026.09.13.02 -> 2026.11.02.01) and their
schema, all eleven FedRAMP schemas (edited under an unchanged dated filename), the FedRAMP 2026
documentation corpus, NIST's SP 800-53 OSCAL catalog (same release 5.2.0, new file), NIST's CSF 2.0
CPRT export, and the community CCI mapping.

Every source_manifest entry that carries an `upstream_check` is fetched once (through fetchkit, so
host rules apply) and compared with the committed file itself — there is no second pin to go stale:

    "upstream_check": {"method": "sha256", "expect": "json"}            # the body's bytes == the committed file's
    "upstream_check": {"method": "json_equal", "path": "rows"}          # parsed body == committed document[path]
    optional: "url" (default: the entry's source_url), "file" (default: the entry's file)

`expect` ("json" | "pdf") names what the body must be before it is compared: a bot-challenge or
error page served with HTTP 200 is a failed check, never a reported change.

Rows are `same`, `changed` or `check_failed`. The run's status is `drift` when any row changed,
`check_failed` when none changed but one could not be checked, else `current`. Report-only: this
tool never writes a canonical file; an ingest is a reviewed change of its own.

    python3 tools/upstream_fingerprint.py --check      # JSON report on stdout; exit 1 on drift, 2 on check_failed
    python3 tools/upstream_fingerprint.py --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "canonical-sources" / "source_manifest.json"
METHODS = ("sha256", "json_equal")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _is(expect: str | None, body: bytes) -> bool:
    if expect == "json":
        try:
            json.loads(body)
        except ValueError:
            return False
    elif expect == "pdf":
        return body[:5] == b"%PDF-"
    return True


def compare(spec: dict, upstream: bytes, committed: bytes) -> tuple:
    """(status, detail) for one source. Never raises on the issuer's bytes."""
    method = spec.get("method")
    if method not in METHODS:
        return "check_failed", f"unknown method {method!r}"
    if not _is(spec.get("expect"), upstream):
        return "check_failed", (f"the issuer's response is not {spec['expect']} ({len(upstream):,} B starting "
                                f"{upstream[:24]!r}) — an error or challenge page, not the artifact")
    if method == "sha256":
        a, b = _sha(upstream), _sha(committed)
        if a == b:
            return "same", None
        return "changed", f"issuer sha256 {a[:12]} ({len(upstream):,} B) != committed {b[:12]} ({len(committed):,} B)"
    try:
        up = json.loads(upstream)
    except ValueError:
        return "check_failed", "the issuer's response is not JSON"
    doc = json.loads(committed)
    for key in (spec.get("path") or "").split("."):
        if key:
            doc = doc[key]
    if up == doc:
        return "same", None
    n = (f"{len(up):,} vs {len(doc):,} entries" if isinstance(up, (list, dict)) and isinstance(doc, (list, dict))
         else "different values")
    return "changed", f"issuer JSON != committed {spec.get('path') or 'document'} ({n})"


def _fetch(url: str) -> bytes:
    sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
    import fetchkit
    r = fetchkit.fetch(url, timeout=120, retries=2, retry_on=(429, 502, 503), backoff=3.0)
    if r.status != 200:
        raise RuntimeError(f"HTTP {r.status}")
    return r.body


def run(fetch=None, manifest: dict | None = None, root: Path = ROOT) -> dict:
    """Check every manifest source that declares an upstream_check. `fetch(url) -> bytes`."""
    fetch = fetch or _fetch
    manifest = manifest if manifest is not None else json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for e in manifest.get("sources", []):
        spec = e.get("upstream_check")
        if not isinstance(spec, dict):
            continue
        url = spec.get("url") or e.get("source_url")
        rel = spec.get("file") or e.get("file")
        row = {"id": e["id"], "method": spec.get("method"), "url": url, "file": rel}
        path = root / rel if rel else None
        if not url or path is None or not path.is_file():
            row.update(status="check_failed", detail="no upstream URL or no committed file to compare")
        else:
            try:
                body = fetch(url)
            except Exception as x:  # noqa: BLE001 — includes PolicyRefused/HostCooldown: reported, never routed around
                row.update(status="check_failed", detail=f"{type(x).__name__}: {str(x)[:140]}")
            else:
                status, detail = compare(spec, body, path.read_bytes())
                row.update(status=status, detail=detail)
        rows.append(row)
    n = {s: sum(1 for r in rows if r["status"] == s) for s in ("same", "changed", "check_failed")}
    status = "drift" if n["changed"] else "check_failed" if n["check_failed"] else "current"
    return {"upstream_status": status, "upstream_counts": n, "upstream_signals": rows}


def selftest() -> int:
    """Offline. Every outcome on fixtures, including the two that must never read as a change."""
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "a.json").write_text('{"v": 1}\n', encoding="utf-8")
    (d / "w.json").write_text(json.dumps({"_meta": {"tool": "x"}, "rows": [1, 2, 3]}), encoding="utf-8")
    (d / "p.pdf").write_bytes(b"%PDF-1.7 body")
    man = {"sources": [
        {"id": "same-bytes", "file": "a.json", "source_url": "u://same", "upstream_check": {"method": "sha256", "expect": "json"}},
        {"id": "edited-in-place", "file": "a.json", "source_url": "u://edited", "upstream_check": {"method": "sha256", "expect": "json"}},
        {"id": "challenge-page", "file": "a.json", "source_url": "u://challenge", "upstream_check": {"method": "sha256", "expect": "json"}},
        {"id": "host-down", "file": "a.json", "source_url": "u://down", "upstream_check": {"method": "sha256", "expect": "json"}},
        {"id": "wrapped-same", "file": "w.json", "source_url": "u://rows", "upstream_check": {"method": "json_equal", "path": "rows"}},
        {"id": "wrapped-changed", "file": "w.json", "source_url": "u://rows2", "upstream_check": {"method": "json_equal", "path": "rows"}},
        {"id": "pdf-same", "file": "p.pdf", "source_url": "u://pdf", "upstream_check": {"method": "sha256", "expect": "pdf"}},
        {"id": "pdf-html", "file": "p.pdf", "source_url": "u://pdfhtml", "upstream_check": {"method": "sha256", "expect": "pdf"}},
        {"id": "file-gone", "file": "missing.json", "source_url": "u://same", "upstream_check": {"method": "sha256"}},
        {"id": "not-checked", "file": "a.json", "source_url": "u://never"},
    ]}
    served = {"u://same": b'{"v": 1}\n', "u://edited": b'{"v": 2}\n', "u://challenge": b"<html>checking your browser</html>",
              "u://rows": b"[1, 2, 3]", "u://rows2": b"[1, 2, 3, 4]", "u://pdf": b"%PDF-1.7 body", "u://pdfhtml": b"<html>404</html>"}
    asked = []

    def fetch(url):
        asked.append(url)
        if url == "u://down":
            raise RuntimeError("HTTP 503")
        return served[url]
    rep = run(fetch, man, d)
    got = {r["id"]: r["status"] for r in rep["upstream_signals"]}
    want = {"same-bytes": "same", "edited-in-place": "changed", "challenge-page": "check_failed", "host-down": "check_failed",
            "wrapped-same": "same", "wrapped-changed": "changed", "pdf-same": "same", "pdf-html": "check_failed",
            "file-gone": "check_failed"}
    quiet = run(lambda u: served["u://same"], {"sources": man["sources"][:1]}, d)
    failed_only = run(fetch, {"sources": [man["sources"][0], man["sources"][3]]}, d)
    cases = [
        ("each outcome is classified", got == want),
        ("a challenge or error page is a failed check, never a reported change",
         got["challenge-page"] == got["pdf-html"] == "check_failed"),
        ("a source without upstream_check is not fetched", "u://never" not in asked and "not-checked" not in got),
        ("any change makes the run drift", rep["upstream_status"] == "drift" and rep["upstream_counts"]["changed"] == 2),
        ("no change and no failure is current", quiet["upstream_status"] == "current"),
        ("a failure without a change is check_failed, not current", failed_only["upstream_status"] == "check_failed"),
    ]
    bad = [label for label, ok in cases if not ok]
    for label, ok in cases:
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    print(f"[selftest] upstream-fingerprint: {len(cases) - len(bad)}/{len(cases)} passed")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rep = run()
    print(json.dumps(rep, indent=2))
    return {"drift": 1, "check_failed": 2}.get(rep["upstream_status"], 0)


if __name__ == "__main__":
    sys.exit(main())
