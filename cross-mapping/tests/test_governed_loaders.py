#!/usr/bin/env python3
"""Offline tests for the phase-51 governed loaders: every hand-run loader fetches through
fetchkit.fetch (host_policies.json caps, pacing, breaker, ledger), keeps its old return contract,
retries only transient failures, and never retries a policy refusal. No network: a fake opener
answers every request, and a direct urllib.request.urlopen call fails the test."""

import gzip
import io
import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
import fetchkit  # noqa: E402
import attack_stix_loader  # noqa: E402
import cprt_traverser  # noqa: E402
import ecfr_loader  # noqa: E402
import eurlex_loader  # noqa: E402
import fips_cmvp_loader  # noqa: E402
import fr_watcher  # noqa: E402
import horizon_monitor  # noqa: E402
import kev_loader  # noqa: E402
import nvd_api_loader  # noqa: E402
import olir_crawler  # noqa: E402
import oscal_diff  # noqa: E402

PASS = 0
SLEPT = []
SCRIPT, SENT = [], []


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok: {label}")


def _raw(*a, **k):
    raise AssertionError("ungoverned urlopen call")


class R(io.BytesIO):
    def __init__(self, body=b"", status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(req, timeout):
    if req.full_url.endswith("/robots.txt"):
        raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, io.BytesIO(b""))
    SENT.append(req)
    item = SCRIPT.pop(0)
    if isinstance(item, int):
        raise urllib.error.HTTPError(req.full_url, item, "x", {}, io.BytesIO(b""))
    return item(req) if callable(item) else item


def gov(cap=99):
    g = fetchkit.RateGovernor(state_path=None, opener=opener, sleeper=lambda s: None,
                              policies={"_default": {"enforced": {"run_cap": cap, "min_interval_s": 0}}, "hosts": {}})
    fetchkit._GOV = g
    SENT.clear()
    return g


def case(label, script, fn, want, cap=99):
    g = gov(cap)
    SCRIPT[:] = script
    try:
        got = fn()
    except Exception as e:  # noqa: BLE001
        got = f"raises {type(e).__name__}"
    good = want(got) if callable(want) else got == want
    ok(good, f"{label} (sent={len(SENT)} refused={sum(len(v) for v in g.refusals.values())})")
    return g


U = "https://h.example/x"
J = lambda o: R(json.dumps(o).encode())  # noqa: E731


def test_contracts():
    case("kev 200 -> bytes", [R(b"{}")], lambda: kev_loader._fetch(U), b"{}")
    case("kev 429 then 200 -> retried once", [429, R(b"{}")], lambda: kev_loader._fetch(U), b"{}")
    case("kev 404 -> None, not retried", [404], lambda: kev_loader._fetch(U), None)
    g = case("kev run cap 0 -> refused, None, nothing sent", [], lambda: kev_loader._fetch(U), None, cap=0)
    ok(not SENT and sum(len(v) for v in g.refusals.values()) == 1, "a refusal sends nothing and is recorded once")
    case("nvd 200 -> dict", [J({"totalResults": 0})], lambda: nvd_api_loader._fetch_json(U, {"a": 1}, None), {"totalResults": 0})
    case("nvd 403 x3 -> RuntimeError", [403, 403, 403], lambda: nvd_api_loader._fetch_json(U, {}, None), "raises RuntimeError")
    case("nvd 400 -> HTTPError, not retried", [400], lambda: nvd_api_loader._fetch_json(U, {}, None), "raises HTTPError")
    case("fr 503 then 200", [503, R(b"[]")], lambda: fr_watcher._fetch_with_retry(U), b"[]")
    case("fr 404 -> None", [404], lambda: fr_watcher._fetch_with_retry(U), None)
    case("ecfr mislabelled gzip body decoded", [R(gzip.compress(b"<x/>"))], lambda: ecfr_loader._fetch_with_retry(U), b"<x/>")
    case("eurlex Cellar XHTML 200 -> text",
         [R(b"<html><p>Article 1</p></html>", headers={"Content-Type": "application/xhtml+xml;charset=UTF-8"})],
         lambda: eurlex_loader._fetch_cellar("32016R0679"), "<html><p>Article 1</p></html>")
    case("eurlex 202 bot challenge -> FetchRejected (nothing written)",
         [R(b"<html><script>awswaf challenge</script></html>", 202, {"Content-Type": "text/html; charset=UTF-8"})],
         lambda: eurlex_loader._fetch_cellar("32016R0679"), "raises FetchRejected")
    case("eurlex text/html body -> FetchRejected (not the XHTML manifestation)",
         [R(b"<html/>", headers={"Content-Type": "text/html; charset=UTF-8"})],
         lambda: eurlex_loader._fetch_cellar("32016R0679"), "raises FetchRejected")
    case("eurlex 404 -> HTTPError", [404], lambda: eurlex_loader._fetch_cellar("32016R0679"), "raises HTTPError")
    case("fips 405 -> None", [405], lambda: fips_cmvp_loader._fetch(U, {"q": 1}), None)
    case("fips 200 JSON", [J([1, 2])], lambda: fips_cmvp_loader._fetch(U), [1, 2])
    case("olir 500 -> None (retries only 429/503)", [500], lambda: olir_crawler._fetch(U), None)
    case("cprt 200 JSON", [J({"k": 1})], lambda: cprt_traverser._fetch_json(U), {"k": 1})
    case("attack 200 bytes", [R(b"{}")], lambda: attack_stix_loader._fetch_url(U), b"{}")
    case("attack 404 -> HTTPError", [404], lambda: attack_stix_loader._fetch_url(U), "raises HTTPError")
    case("horizon 200 -> (True, text)", [R(b"hello")], lambda: horizon_monitor._http_ok(U), (True, "hello"))
    case("horizon refused -> (False, PolicyRefused)", [], lambda: horizon_monitor._http_ok(U), (False, "PolicyRefused"), cap=0)


def test_oscal_windows():
    doc = json.dumps({"catalog": {"x": "y" * 1_200_000}}).encode()

    def ranged(req):
        a, b = (int(x) for x in req.get_header("Range").split("=")[1].split("-"))
        return R(doc[a:b + 1], 206, {"Content-Range": f"bytes {a}-{b}/{len(doc)}"})
    want = 1 + -(-len(doc) // oscal_diff.WINDOW)
    case(f"oscal {len(doc):,} B in 512 KiB windows", [ranged] * want,
         lambda: len(json.dumps(oscal_diff.fetch_large_json(U))) > 1_000_000, True)
    ok(len(SENT) == want, f"oscal: every window is one governed request ({want})")


def test_run_cli_saves_ledger():
    with tempfile.TemporaryDirectory() as d:
        saved_dir, saved_state = fetchkit.STATE_DIR, fetchkit.save_state
        fetchkit.STATE_DIR, fetchkit.save_state = Path(d), (lambda: None)
        try:
            gov()
            SCRIPT[:] = [R(b"{}")]
            rc = fetchkit.run_cli(lambda: (kev_loader._fetch(U), 7)[1], "kev_loader")
            led = json.loads((Path(d) / "ledger" / "kev_loader.json").read_text(encoding="utf-8"))
        finally:
            fetchkit.STATE_DIR, fetchkit.save_state = saved_dir, saved_state
    ok(rc == 7 and led == {"h.example": {"requests": 1, "refused": 0, "reasons": []}},
       "run_cli returns main's value and writes the loader's ledger")


if __name__ == "__main__":
    time.sleep = lambda s: SLEPT.append(s)
    urllib.request.urlopen = _raw
    for m in (kev_loader, fr_watcher, ecfr_loader, olir_crawler, cprt_traverser):
        if hasattr(m, "urlopen"):
            m.urlopen = _raw
    for fn in (test_contracts, test_oscal_windows, test_run_cli_saves_ledger):
        fn()
    ok(SLEPT == [2.0, 6.0, 12.0, 2.0], f"backoff only on transient failures: {SLEPT}")
    print(f"\ngoverned-loader tests: {PASS} assertions PASS")
