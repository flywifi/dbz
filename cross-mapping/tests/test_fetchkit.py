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


if __name__ == "__main__":
    for fn in [test_breaker_trips_and_cools, test_retry_after_honored, test_budget_exhausts,
               test_cache_304_and_sha, test_governor_state_roundtrip,
               test_resilient_live_and_unchanged, test_wayback_only_on_hard_fail,
               test_no_wayback_on_success]:
        fn()
    print(f"\nfetchkit tests: {PASS} assertions PASS")
