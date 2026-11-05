#!/usr/bin/env python3
"""Offline unit tests for cross-mapping/engine/fetchkit.py — injected fake opener,
no network, no persisted state (state_path=None via tmp files)."""

import io
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import fetchkit  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok: {label}")


class FakeResp:
    def __init__(self, status=200, headers=None, body=b"data"):
        self.status = status
        self.headers = headers or {}
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_opener(script):
    """script: list of FakeResp | Exception, consumed per call (robots calls get 404)."""
    calls = []

    def opener(req, timeout):
        calls.append(req.full_url)
        if req.full_url.endswith("/robots.txt"):
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, io.BytesIO(b""))
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    opener.calls = calls
    return opener


def gov(script, **kw):
    return fetchkit.RateGovernor(state_path=None, opener=make_opener(script),
                                 clock=FakeClock(), sleeper=lambda s: None, **kw)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        self.t += 0.01
        return self.t


def test_breaker_trips_and_cools():
    g = gov([])
    for _ in range(3):
        g.note("h.example", 503, {})
    g.wait("h.example")  # 3 fails — not yet tripped
    g.note("h.example", 503, {})  # 4th -> breaker
    try:
        g.wait("h.example")
        ok(False, "breaker should raise HostCooldown")
    except fetchkit.HostCooldown:
        ok(True, "breaker trips after 4 consecutive 503s")
    e = g.hosts["h.example"]
    ok(e["breaker_until"] > 1000.0, "cooldown timestamp set (~15 min)")
    e["breaker_until"] = 0.0  # simulate cooldown expiry
    g.wait("h.example")
    ok(True, "host usable again after cooldown expires")
    g.note("h.example", 200, {})
    ok(g.hosts["h.example"]["fails"] == 0, "success resets the fail counter")


def test_retry_after_honored():
    g = gov([])
    g.note("h2.example", 429, {"Retry-After": "30"})
    ok(g.hosts["h2.example"]["interval"] >= 30.0, "Retry-After raises the host interval")


def test_budget_exhausts():
    g = gov([], budget=2)
    g.wait("a.example")
    g.wait("b.example")
    try:
        g.wait("c.example")
        ok(False, "budget should exhaust")
    except RuntimeError:
        ok(True, "per-run budget exhausts after N requests")


def test_cache_304_and_sha():
    with tempfile.TemporaryDirectory() as td:
        c = fetchkit.FetchCache(state_path=Path(td) / "s.json")
        v = c.note_response("http://x/y", 200, {"ETag": '"abc"'}, b"hello")
        ok(v == "changed", "first 200 is a change")
        ok(c.validators("http://x/y").get("If-None-Match") == '"abc"', "ETag becomes validator")
        ok(c.note_response("http://x/y", 304, {}, None) == "unchanged", "304 -> unchanged")
        ok(c.note_response("http://x/y", 200, {}, b"hello") == "unchanged",
           "sha-identical 200 -> unchanged")
        ok(c.note_response("http://x/y", 200, {}, b"world") == "changed", "new body -> changed")
        c.save()
        c2 = fetchkit.FetchCache(state_path=Path(td) / "s.json")
        ok(c2.cached_sha("http://x/y") is not None, "cache state round-trips through disk")


def test_governor_state_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "hosts.json"
        g = fetchkit.RateGovernor(state_path=p, opener=make_opener([]),
                                  clock=FakeClock(), sleeper=lambda s: None)
        g.note("persist.example", 429, {"Retry-After": "60"})
        g.save()
        g2 = fetchkit.RateGovernor(state_path=p, opener=make_opener([]),
                                   clock=FakeClock(), sleeper=lambda s: None)
        ok(g2.hosts["persist.example"]["interval"] >= 60.0, "learned limits persist across runs")


def test_resilient_live_and_unchanged():
    with tempfile.TemporaryDirectory() as td:
        c = fetchkit.FetchCache(state_path=Path(td) / "s.json")
        g = gov([FakeResp(200, {"ETag": '"e1"'}, b"body-1"),
                 FakeResp(200, {"ETag": '"e1"'}, b"body-1")])
        s, body, meta = fetchkit.resilient_get("https://live.example/a", gov=g, fcache=c)
        ok(s == 200 and body == b"body-1" and meta["source"] == "live", "live 200 fetch")
        s, body, meta = fetchkit.resilient_get("https://live.example/a", gov=g, fcache=c)
        ok(body is None and meta["cache"] == "unchanged", "sha-identical repeat -> unchanged, no body")


def test_wayback_only_on_hard_fail():
    with tempfile.TemporaryDirectory() as td:
        c = fetchkit.FetchCache(state_path=Path(td) / "s.json")
        wb = json.dumps({"archived_snapshots": {"closest": {
            "url": "https://web.archive.org/web/20260101000000/https://dead.example/x",
            "timestamp": "20260101000000"}}}).encode()
        g = gov([urllib.error.HTTPError("https://dead.example/x", 500, "boom", {}, io.BytesIO(b"")),
                 FakeResp(200, {}, wb),
                 FakeResp(200, {}, b"archived-body")])
        s, body, meta = fetchkit.resilient_get("https://dead.example/x", gov=g, fcache=c)
        ok(meta["source"] == "wayback" and body == b"archived-body", "hard fail falls back to wayback")
        ok(meta["snapshot_ts"] == "20260101000000", "wayback result carries its snapshot label")
        # allow_wayback=False: hard fail returns the failure, no archive prong
        g2 = gov([urllib.error.HTTPError("https://dead.example/y", 500, "boom", {}, io.BytesIO(b""))])
        s, body, meta = fetchkit.resilient_get("https://dead.example/y", gov=g2, fcache=c,
                                               allow_wayback=False)
        ok(s == 500 and body is None and meta["source"] == "live",
           "allow_wayback=False never touches the archive")
        ok(not any("archive.org" in u for u in g2._opener.calls),
           "no archive.org request was made")


def test_no_wayback_on_success():
    with tempfile.TemporaryDirectory() as td:
        c = fetchkit.FetchCache(state_path=Path(td) / "s.json")
        g = gov([FakeResp(200, {}, b"fine")])
        fetchkit.resilient_get("https://ok.example/z", gov=g, fcache=c)
        ok(not any("archive.org" in u for u in g._opener.calls),
           "successful live fetch never consults wayback")


# ── phase 50: recorded host usage rules (canonical-sources/host_policies.json) ─────────────
# Fixtures are the hosts' real robots.txt files (fetched 2026-11-04); statuses below mirror the
# measured ones: www.cisa.gov 403 (CDN), web.archive.org connection reset, dl.dod.cyber.mil 404.

ROBOTS_FIX = Path(__file__).resolve().parent / "fixtures" / "robots"
POLICIES = json.loads((Path(__file__).resolve().parents[2] / "canonical-sources"
                       / "host_policies.json").read_text(encoding="utf-8"))


class StepClock:
    """A clock that advances only when the governor sleeps — sleeps become measurable."""
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(0.0, s)


SENT = []


def policy_opener(req, timeout):
    url, host = req.full_url, fetchkit._host(req.full_url)
    if url.endswith("/robots.txt"):
        if host == "www.cisa.gov":
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(b""))
        if host == "web.archive.org":
            raise ConnectionResetError("reset by peer")
        fx = ROBOTS_FIX / f"{host}.txt"
        if fx.exists():
            return FakeResp(200, {}, fx.read_bytes())
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))
    SENT.append(req)
    return FakeResp(200, {}, b"ok")


def policy_gov():
    c = StepClock()
    return fetchkit.RateGovernor(state_path=None, opener=policy_opener, clock=c,
                                 sleeper=c.sleep, policies=POLICIES), c


def refusal(g, url):
    try:
        g.wait(fetchkit._host(url), url)
        return None
    except fetchkit.PolicyRefused as e:
        return str(e)


def test_policy_registry_cites_every_rule():
    for host, v in POLICIES["hosts"].items():
        ok(all(v.get(k) for k in ("published_rule", "source_url", "verified", "probe",
                                  "robots", "enforced")), f"{host}: rule, source, date, probe recorded")
        for x in v["enforced"].get("documented_api_paths", []):
            ok(all(x.get(k) for k in ("prefix", "robots_line", "api_doc", "api_doc_url")),
               f"{host}: robots override {x.get('prefix')} carries both citations")


def test_ncp_meta_first_and_run_cap():
    g, _ = policy_gov()
    base = "https://ncp.nist.gov/feeds/xml/ncp/checklist-0.1-feed"
    ok("before its .meta" in (refusal(g, base + ".xml.gz") or ""),
       "NCP feed download refused before its .meta (published rule)")
    ok(refusal(g, base + ".meta") is None and refusal(g, base + ".xml.gz") is None,
       "NCP feed admitted after its .meta")
    n = 2
    while refusal(g, base + ".meta") is None:
        n += 1
    ok(n == POLICIES["hosts"]["ncp.nist.gov"]["enforced"]["run_cap"],
       f"NCP run cap enforced at {n} requests (published: <200/day)")


def test_nvd_rolling_window():
    import os
    url = "https://services.nvd.nist.gov/rest/json/cves/2.0?x"
    g, c = policy_gov()
    t0 = c.t
    for _ in range(6):
        g.wait("services.nvd.nist.gov", url)
    ok(c.t - t0 >= 30, f"NVD without key: 6 requests took {c.t - t0:.1f}s (rule: 5 per 30 s)")
    os.environ["NVD_API_KEY"] = "test"
    try:
        g, c = policy_gov()
        t0 = c.t
        for _ in range(6):
            g.wait("services.nvd.nist.gov", url)
        ok(c.t - t0 < 30, f"NVD with key: 6 requests took {c.t - t0:.1f}s (rule: 50 per 30 s)")
    finally:
        del os.environ["NVD_API_KEY"]


def test_robots_rfc9309():
    g, _ = policy_gov()
    cases = [("https://www.ecfr.gov/api/versioner/v1/full/2026-08-01/title-32.xml?part=170", None),
             ("https://www.ecfr.gov/search?q=x", "disallows"),
             ("https://www.ecfr.gov/api/versioner/v1/structure/current/title-45.json", None),
             ("https://www.federalregister.gov/articles/search?x=1", "disallows"),
             ("https://www.federalregister.gov/api/v1/documents.json?per_page=1", None),
             ("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", None),
             ("https://web.archive.org/wayback/available?url=x", "unreachable"),
             ("https://ncp.nist.gov/feeds/xml/ncp/checklist-0.1-feed.meta", None),
             ("https://www.nist.gov/search/site?x", "disallows"),
             ("https://www.nist.gov/blogs/cybersecurity-insights/rss.xml", None),
             ("https://cyber.trackr.live/search/x", "disallows"),
             ("https://cyber.trackr.live/api/stig", None)]
    for url, want in cases:
        got = refusal(g, url)
        good = (got is None) if want is None else (got is not None and want in got)
        ok(good, f"robots {'allow' if want is None else 'deny (' + want + ')'}: {url[:70]}")


def test_stdlib_blank_line_grouping_is_neutralised():
    body = (ROBOTS_FIX / "www.ecfr.gov.txt").read_text(encoding="utf-8")
    import urllib.robotparser
    naive = urllib.robotparser.RobotFileParser()
    naive.parse(body.splitlines())
    url = "https://www.ecfr.gov/api/versioner/v1/full/2026-01-01/title-45.xml"
    ok(naive.can_fetch(fetchkit.ROBOTS_AGENT, url),
       "stdlib parser alone allows a path eCFR disallows (the defect, pinned)")
    ok(not fetchkit.robots_verdict(200, body).can_fetch(fetchkit.ROBOTS_AGENT, url),
       "robots_verdict honours eCFR's Disallow after blank-line normalisation")


def test_longest_match_wins():
    """RFC 9309 §2.2.2: the most specific (longest) rule decides; allow wins a tie. The stdlib
    parser applies the first match — on the first live dispatch (run 41936204283) it refused
    www.ismap.go.jp/csm, the only path ISMAP's robots.txt allows."""
    import urllib.robotparser
    body = (ROBOTS_FIX / "www.ismap.go.jp.txt").read_text(encoding="utf-8")
    naive = urllib.robotparser.RobotFileParser()
    naive.parse(fetchkit.robots_lines(body))
    ok(not naive.can_fetch(fetchkit.ROBOTS_AGENT, "https://www.ismap.go.jp/csm"),
       "stdlib first-match refuses ISMAP /csm (the defect, pinned)")
    v = fetchkit.robots_verdict(200, body)
    ok(v.can_fetch(fetchkit.ROBOTS_AGENT, "https://www.ismap.go.jp/csm")
       and v.can_fetch(fetchkit.ROBOTS_AGENT, "https://www.ismap.go.jp/csm/news"),
       "ISMAP /csm allowed ('Allow: /csm' is longer than 'Disallow: /')")
    ok(not v.can_fetch(fetchkit.ROBOTS_AGENT, "https://www.ismap.go.jp/")
       and not v.can_fetch(fetchkit.ROBOTS_AGENT, "https://www.ismap.go.jp/en/"),
       "ISMAP paths outside /csm stay disallowed")
    rfc = [("allow: /p\ndisallow: /", "/page", True),
           ("allow: /folder\ndisallow: /folder", "/folder/page", True),
           ("allow: /page\ndisallow: /*.html", "/page.html", False),
           ("allow: /page\ndisallow: /*.html", "/page.php5", True),
           ("allow: /$\ndisallow: /", "/", True),
           ("allow: /$\ndisallow: /", "/page.htm", False)]
    for rules, path, want in rfc:
        got = fetchkit.RobotsRules("user-agent: *\n" + rules).can_fetch(fetchkit.ROBOTS_AGENT, "https://x" + path)
        ok(got == want, f"RFC 9309 §2.2.2 example {rules.splitlines()} {path} -> {'allow' if want else 'deny'}")
    own = fetchkit.RobotsRules("User-agent: *\nDisallow: /\n\nUser-agent: dbz-standards-monitor\nDisallow:\n")
    ok(own.can_fetch(fetchkit.ROBOTS_AGENT, "https://x/a"),
       "a group naming our product token replaces the '*' group (§2.2.1)")
    ok(not fetchkit.RobotsRules("User-agent: Googlebot\nDisallow: /\nUser-agent: *\nDisallow: /private\n")
       .can_fetch(fetchkit.ROBOTS_AGENT, "https://x/private/x"),
       "with no group of our own, the '*' group applies")
    g, _ = policy_gov()
    ok(refusal(g, "https://www.ismap.go.jp/csm") is None,
       "the governor admits ISMAP /csm (the registered japan-ismap landing)")


def test_group_boundaries_and_wildcards():
    """Any group record (not only allow/disallow) ends a run of user-agent lines. Real file:
    law.lis.virginia.gov ('User-agent: * / Crawl-delay: 10 / User-agent: GPTBot / Disallow: /').
    Counting only allow/disallow merged GPTBot into '*' and refused a registered statute page on
    the second CI dispatch (run 41940244303). GitHub lines quoted verbatim from github.com/robots.txt
    (read 2026-11-05): its '*' group disallows '/*.atom$', which the stdlib cannot express."""
    body = (ROBOTS_FIX / "law.lis.virginia.gov.txt").read_text(encoding="utf-8")
    v = fetchkit.robots_verdict(200, body)
    ok(v.can_fetch(fetchkit.ROBOTS_AGENT, "https://law.lis.virginia.gov/vacodefull/toc.aspx?1=59.1-571"),
       "Virginia: the '*' group (Crawl-delay only) allows the statute page")
    ok(not v.can_fetch("GPTBot", "https://law.lis.virginia.gov/vacodefull/"),
       "Virginia: GPTBot keeps its own 'Disallow: /'")
    g, c = policy_gov()
    g.policies = {"_default": {"enforced": {"run_cap": 99, "min_interval_s": 0}}, "hosts": {}}
    t0 = c.t
    g.wait("law.lis.virginia.gov", "https://law.lis.virginia.gov/vacodefull/toc.aspx?1=59.1-571")
    g.wait("law.lis.virginia.gov", "https://law.lis.virginia.gov/vacodefull/toc.aspx?1=59.1-571")
    ok(c.t - t0 >= 10, f"Virginia: Crawl-delay 10 learned from the '*' group ({c.t - t0:.1f}s for 2 requests)")
    gh = ("# If you would like to crawl GitHub contact us via https://support.github.com?tags=dotcom-robots\n"
          "# We also provide an extensive API: https://docs.github.com\n"
          "Sitemap: https://github.com/sitemap_marketing.xml\n\n"
          "User-agent: baidu\ncrawl-delay: 1\n\n"
          "User-agent: *\nDisallow: /*.atom$\nDisallow: /*/*/tags$\n")
    r = fetchkit.robots_verdict(200, gh)
    ok(not r.can_fetch(fetchkit.ROBOTS_AGENT, "https://github.com/OAI/OpenAPI-Specification/releases.atom"),
       "GitHub: repository releases.atom is disallowed ('/*.atom$'); release currency uses the API")
    ok(r.can_fetch(fetchkit.ROBOTS_AGENT, "https://github.com/OAI/OpenAPI-Specification/releases"),
       "GitHub: the releases page itself is allowed ('$' anchors the .atom rule)")


def test_state_path_none_is_stateless():
    """state_path=None means no persisted state. Before 0.15.1 it silently meant the shared
    .fetch-cache file, so after a live run these tests and the census inherited real breakers
    (www.cisa.gov cooldown -> HostCooldown here; the census counted 304 instead of 327)."""
    with tempfile.TemporaryDirectory() as d:
        saved = fetchkit.STATE_DIR
        fetchkit.STATE_DIR = Path(d)
        try:
            (Path(d) / "host_limits.json").write_text(json.dumps({"hosts": {"www.cisa.gov": {
                "last_ts": 0.0, "interval": 1.5, "fails": 4, "breaker_until": 4e9}}}), encoding="utf-8")
            (Path(d) / "fetch_state.json").write_text(json.dumps({"urls": {"https://x/a": {
                "etag": '"e"', "last_modified": "", "sha256": "", "checked_at": ""}}}), encoding="utf-8")
            try:
                fetchkit.RateGovernor(policies=POLICIES).wait("www.cisa.gov", "")
                shared = "admitted"
            except fetchkit.HostCooldown:
                shared = "cooldown"
            ok(shared == "cooldown", "the default governor loads the shared state (a live breaker holds)")
            g, _ = policy_gov()
            ok(refusal(g, "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json") is None,
               "state_path=None ignores persisted breakers (offline tests, census)")
            ok(fetchkit.FetchCache().validators("https://x/a") and not fetchkit.FetchCache(state_path=None).validators("https://x/a"),
               "FetchCache(state_path=None) carries no persisted validators")
        finally:
            fetchkit.STATE_DIR = saved


def test_required_header_and_no_wayback_after_refusal():
    g, _ = policy_gov()
    SENT.clear()
    fetchkit.polite_urlopen(urllib.request.Request(
        "https://www.ecfr.gov/api/versioner/v1/full/2026-08-01/title-32.xml"), gov=g)
    ok(SENT[-1].get_header("Accept-encoding") == "gzip",
       "eCFR's published Accept-Encoding requirement is added automatically")
    st, body, meta = fetchkit.resilient_get("https://web.archive.org/x", gov=g,
                                            fcache=fetchkit.FetchCache(state_path=None))
    ok(meta["trail"][0].startswith("live:refused") and len(meta["trail"]) == 1,
       "a policy-refused URL never falls through to the Wayback prong")
    led = g.ledger()
    ok(led["web.archive.org"]["refused"] == 1 and led["www.ecfr.gov"]["requests"] == 1,
       "the run ledger records admitted and refused requests per host")


def test_save_ledger_roundtrip():
    g, _ = policy_gov()
    g.wait("www.nist.gov", "https://www.nist.gov/blogs/cybersecurity-insights/rss.xml")
    with tempfile.TemporaryDirectory() as d:
        saved, fetchkit._GOV = fetchkit._GOV, g
        try:
            fetchkit.save_ledger("t", state_dir=Path(d))
        finally:
            fetchkit._GOV = saved
        led = json.loads((Path(d) / "ledger" / "t.json").read_text(encoding="utf-8"))
    ok(led == {"www.nist.gov": {"requests": 1, "refused": 0, "reasons": []}},
       "save_ledger writes this process's ledger for the drift report")


if __name__ == "__main__":
    for fn in [test_breaker_trips_and_cools, test_retry_after_honored, test_budget_exhausts,
               test_cache_304_and_sha, test_governor_state_roundtrip,
               test_resilient_live_and_unchanged, test_wayback_only_on_hard_fail,
               test_no_wayback_on_success, test_policy_registry_cites_every_rule,
               test_ncp_meta_first_and_run_cap, test_nvd_rolling_window, test_robots_rfc9309,
               test_stdlib_blank_line_grouping_is_neutralised, test_longest_match_wins,
               test_group_boundaries_and_wildcards, test_state_path_none_is_stateless,
               test_required_header_and_no_wayback_after_refusal, test_save_ledger_roundtrip]:
        fn()
    print(f"\nfetchkit tests: {PASS} assertions PASS")
