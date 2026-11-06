#!/usr/bin/env python3
"""Offline tests for the phase-52 EUR-Lex loader (Publications Office Cellar source; fail closed).
Pins: the saved EUR-Lex 202 AWS WAF challenge (2026-11-05) is refused and nothing is written; a body
below the per-regulation article floor is refused; a non-XHTML content type is refused; the loader's
own field names reach build_db (article_id / title / text), so no regulation collapses to one row."""

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
import eurlex_loader as el  # noqa: E402

PASS = 0
FIX = ROOT / "cross-mapping" / "tests" / "fixtures"


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok: {label}")


class F:
    def __init__(self, body, status=200, ctype="application/xhtml+xml;charset=UTF-8"):
        self.body, self.status, self.headers = body, status, {"content-type": ctype}


def run_with(resp, reg="gdpr"):
    """Run the loader (not dry) against one canned response in a temp output dir; return (errors, files)."""
    saved_fetch, saved_dir = el.fetchkit.fetch, el._EURLEX_DIR
    d = Path(tempfile.mkdtemp())
    el.fetchkit.fetch = lambda url, **k: resp
    el._EURLEX_DIR = d
    try:
        L = el.EURLexLoader()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            L.run([reg], dry_run=False)
        return L.errors, sorted(p.name for p in d.glob("*.json"))
    finally:
        el.fetchkit.fetch, el._EURLEX_DIR = saved_fetch, saved_dir


def xhtml(n_articles):
    body = "".join(f'<p class="oj-ti-art">Article {i}</p><p class="oj-sti-art">Title {i}</p><p>Text of article {i} shall apply.</p>'
                   for i in range(1, n_articles + 1))
    return f"<html><body>{body}</body></html>".encode()


def test_fail_closed():
    challenge = (FIX / "eurlex_waf_challenge_202.html").read_bytes()
    err, files = run_with(F(challenge, 202, "text/html; charset=UTF-8"))
    ok("gdpr" in err and "HTTP 202" in err["gdpr"] and files == [], "the saved EUR-Lex 202 WAF challenge is refused; nothing written")
    err, files = run_with(F(challenge, 200, "text/html; charset=UTF-8"))
    ok("gdpr" in err and files == [], "a challenge page served as 200 is still refused")
    err, files = run_with(F(xhtml(3)))
    ok("gdpr" in err and "floor" in err["gdpr"] and files == [], "a body below the article floor (3 < 99) is refused")
    err, files = run_with(F(xhtml(99), 200, "text/html"))
    ok("gdpr" in err and files == [], "a non-XHTML content type is refused")


def test_accept_and_build_contract():
    sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
    import ast
    src = (ROOT / "cross-mapping" / "engine" / "build_db.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "load_eurlex_data")
    ns = {"json": json, "Path": Path}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "build_db.py", "exec"), ns)   # build_db itself imports pandas
    saved_fetch, saved_dir = el.fetchkit.fetch, el._EURLEX_DIR
    d = Path(tempfile.mkdtemp())
    el.fetchkit.fetch = lambda url, **k: F(xhtml(99))
    el._EURLEX_DIR = d
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = el.EURLexLoader().run(["gdpr"], dry_run=False)
    finally:
        el.fetchkit.fetch, el._EURLEX_DIR = saved_fetch, saved_dir
    doc = json.loads((d / "gdpr-articles.json").read_text(encoding="utf-8"))
    ok(res["gdpr"]["metadata"]["total_articles"] == 99 and "_consolidated_date" not in doc
       and doc["metadata"]["cellar_uri"].startswith("https://publications.europa.eu/resource/celex/")
       and "superseded_source" in doc["metadata"], "99 articles accepted; metadata names the Cellar and the superseded source; no false consolidation date")
    ok(all(a["nist_families"] == [] for a in doc["articles"]), "no article carries a guessed NIST family")
    rows = ns["load_eurlex_data"](d)
    ok(len(rows) == 99 and len({r["article_id"] for r in rows}) == 99 and all(r["title"] and r["text"] for r in rows),
       "build_db reads the loader's field names: 99 distinct rows with title and text (not one empty row)")


if __name__ == "__main__":
    test_fail_closed()
    test_accept_and_build_contract()
    print(f"\neurlex tests: {PASS} assertions PASS")
