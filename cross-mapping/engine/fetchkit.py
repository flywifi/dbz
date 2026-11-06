#!/usr/bin/env python3
"""
fetchkit.py — shared politeness / caching / resilience layer for all live fetching.

The keep-current subsystem talks to ~160 external hosts. This module gives every
caller the same three behaviors so dbz stays a polite citizen of those hosts and
survives their bad days:

  RateGovernor  — per-host pacing (min interval + jitter, robots.txt Crawl-delay),
                  Retry-After / RateLimit-Reset respect, a circuit breaker
                  (4 consecutive 403/429/503 -> 15-min cooldown), persisted learned
                  limits (.fetch-cache/host_limits.json), and — since phase 50 — each
                  host's PUBLISHED usage rule from canonical-sources/host_policies.json:
                  per-run caps, rolling windows (NVD: 5 per 30 s), meta-first downloads
                  (NCP: read the .meta before the feed), required headers (eCFR:
                  Accept-Encoding), and robots.txt Disallow with RFC 9309 status
                  semantics. A broken rule raises PolicyRefused and is recorded in the
                  per-run ledger (run_ledger / save_ledger); the run budget is only a
                  runaway ceiling.
  FetchCache    — per-URL ETag / Last-Modified conditional-GET validators plus a
                  sha256 unchanged check (.fetch-cache/fetch_state.json), so repeat
                  runs are mostly 304 header exchanges.
  resilient_get — one live prong (urllib, gzip-aware, conditional headers) and one
                  labeled Wayback-snapshot prong used ONLY on hard failure.

HONESTY RULE (non-negotiable): a Wayback result is never live currency. The meta
dict always carries source="live" or source="wayback" (+ snapshot_ts), a monitor
consuming a wayback body must record that label in its notes, and HEAD-based
currency polls must pass allow_wayback=False. See docs/standards-refresh-runbook.md.

Runtime-only: build_db.py performs no network I/O, so nothing here can affect
table digests. Stdlib only. State lives under .fetch-cache/ (gitignored).
"""

import gzip
import hashlib
import io
import json
import os
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".fetch-cache"

DEFAULT_MIN_INTERVAL = 1.5   # seconds between requests to one host (plus jitter)
DEFAULT_BUDGET = 600           # runaway ceiling per run (1.8x the 328 measured by the phase-50 census); per-host caps are the guard
DEFAULT_RUN_CAP = 25           # per host per run when a host publishes nothing (busiest such host measured: 19)
ROBOTS_MAX_BYTES = 512 * 1024  # RFC 9309 §2.5: parse at least 500 KiB
ROBOTS_ATTEMPTS = 3
ROBOTS_BACKOFF_S = 5.0
ROBOTS_AGENT = "dbz-standards-monitor"   # product token that robots.txt groups are matched against
POLICY_PATH = ROOT / "canonical-sources" / "host_policies.json"
BREAKER_FAILS = 4            # consecutive 403/429/503 before the breaker trips
BREAKER_COOLDOWN = 15 * 60   # seconds
BREAKER_STATUSES = {403, 429, 503}
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) dbz-standards-monitor "
              "(GRC framework currency check; contact via repo)")
WAYBACK_API = "https://archive.org/wayback/available?url="
_STATE_FILE = object()      # default state_path: the shared file under .fetch-cache/


class HostCooldown(Exception):
    """Raised when a host's circuit breaker is active — skip, don't hammer."""


class PolicyRefused(Exception):
    """The request would break the host's recorded usage rule or its robots.txt.
    Skip it, report it (run ledger), never retry it in the same run."""


def _host(url: str) -> str:
    return url.split("//", 1)[-1].split("/", 1)[0].lower()


def _default_open(req: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(req, timeout=timeout)


def _read_body(resp) -> bytes:
    body = resp.read()
    if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
        try:
            body = gzip.GzipFile(fileobj=io.BytesIO(body)).read()
        except OSError:
            pass  # mislabeled encoding — keep raw bytes, never crash the fetch
    return body


def read_body(resp) -> bytes:
    """Public: read a response body, decoding Content-Encoding: gzip (required-header hosts)."""
    return _read_body(resp)


def load_policies(path: Path | None = None) -> dict:
    """canonical-sources/host_policies.json, or a built-in default when absent (offline tests)."""
    default = {"_default": {"enforced": {"min_interval_s": DEFAULT_MIN_INTERVAL,
                                         "run_cap": DEFAULT_RUN_CAP}}, "hosts": {}}
    try:
        data = json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    data.setdefault("hosts", {})
    data.setdefault("_default", default["_default"])
    return data


def robots_lines(body: str) -> list:
    """RFC 9309 groups rules by user-agent lines; blank lines carry no meaning. The stdlib parser
    ends a group at a blank line, which silently drops the Disallow rules of eCFR's and the
    Federal Register's real robots.txt (measured phase 50) — strip comments and blank lines."""
    return [ln for ln in (x.split("#", 1)[0].strip() for x in body.splitlines()) if ln]


def _robots_match(pattern: str, path: str) -> bool:
    """RFC 9309 §2.2.3 path match: '*' matches any sequence, a trailing '$' anchors the end."""
    anchored = pattern.endswith("$")
    core = pattern[:-1] if anchored else pattern
    rx = "".join(".*" if c == "*" else re.escape(c) for c in core)
    return re.match(rx + ("$" if anchored else ""), path, re.S) is not None


class RobotsRules:
    """robots.txt rules evaluated as RFC 9309 requires. Replaces urllib.robotparser, which
    (1) ends a group at a blank line and (2) applies the FIRST matching rule, where §2.2.2 requires
    the MOST SPECIFIC match (the longest pattern) with an allow winning a tie. Both were measured
    on real files in phase 50: (1) dropped eCFR's and the Federal Register's Disallows; (2) refused
    www.ismap.go.jp/csm ('Disallow: /' listed before 'Allow: /csm') on the first live dispatch.
    Groups (§2.2.1): consecutive user-agent lines open one group; every group whose product token
    equals ours (case-insensitive) is merged, else every '*' group; no group -> allow."""

    def __init__(self, body: str):
        self.groups: list = []          # [(agents: set[str], rules: [(allow: bool, pattern: str)])]
        agents, rules, in_rules = set(), [], False
        for ln in robots_lines(body):
            key, _, val = ln.partition(":")
            key, val = key.strip().lower(), urllib.parse.unquote(val.strip())
            if key == "user-agent":
                if in_rules:
                    self.groups.append((agents, rules))
                    agents, rules, in_rules = set(), [], False
                agents.add(val.lower().split("/", 1)[0].strip())
            elif key != "sitemap" and agents:
                # Any group record ends the run of user-agent lines, not only allow/disallow:
                # law.lis.virginia.gov reads "User-agent: * / Crawl-delay: 10 / User-agent: GPTBot
                # / Disallow: /". Counting only allow/disallow merged GPTBot into '*' and refused
                # everyone (second CI dispatch, run 41940244303). Sitemap is a global record.
                in_rules = True
                if key in ("allow", "disallow") and val:   # an empty Disallow is no rule
                    rules.append((key == "allow", val))
        if agents:
            self.groups.append((agents, rules))

    def rules_for(self, agent: str) -> list:
        token = agent.lower().split("/", 1)[0].strip()
        matched = [r for ags, r in self.groups if token in ags]
        if not matched:
            matched = [r for ags, r in self.groups if "*" in ags]
        return [rule for r in matched for rule in r]

    def can_fetch(self, agent: str, url: str) -> bool:
        path = urllib.parse.unquote(_path_of(url).split("#", 1)[0])
        if path == "/robots.txt":
            return True                      # §2.2.2: /robots.txt is implicitly allowed
        best = None                          # (pattern length, allow)
        for allow, pattern in self.rules_for(agent):
            if _robots_match(pattern, path):
                n = len(pattern.encode("utf-8"))
                if best is None or n > best[0] or (n == best[0] and allow):
                    best = (n, allow)
        return True if best is None else best[1]


def robots_verdict(status: int, body: str):
    """RFC 9309 status semantics. 2xx -> parse (an HTML page, or a body without directives, is not
    a robots file -> no rules); 4xx 'unavailable' -> allow all (§2.3.1.3); 5xx or a network
    failure 'unreachable' -> complete disallow (§2.3.1.4). Returns "allow_all" | "disallow_all" |
    a RobotsRules."""
    if status == 0 or 500 <= status <= 599:
        return "disallow_all"
    if 400 <= status <= 499:
        return "allow_all"
    head = body.lstrip()[:300].lower()
    if (head.startswith(("<!doctype", "<html")) or "<head" in head
            or not re.search(r"(?im)^\s*(user-agent|disallow|allow)\s*:", body)):
        return "allow_all"
    return RobotsRules(body)


def _path_of(url: str) -> str:
    rest = url.split("//", 1)[-1]
    return "/" + rest.split("/", 1)[1] if "/" in rest else "/"


def _meta_key(url: str) -> str:
    """'…/feed.meta' and '…/feed.xml.gz' share the key '…/feed' (meta-first pairing)."""
    return re.sub(r"\.(meta|xml\.gz|xml\.zip|zip|gz|xml)$", "", url.split("?", 1)[0])


class RateGovernor:
    """Per-host pacing + breaker + recorded host usage rules + runaway ceiling.
    Learned limits persist across runs (.fetch-cache/host_limits.json); per-run counts never do."""

    def __init__(self, state_path=_STATE_FILE, *,
                 min_interval: float = DEFAULT_MIN_INTERVAL,
                 budget: int = DEFAULT_BUDGET,
                 opener=_default_open, clock=time.time, sleeper=time.sleep,
                 policies: dict | None = None):
        # Omitted -> the shared .fetch-cache/host_limits.json. None -> no persisted state: nothing
        # loaded, nothing saved. (Before 0.15.1 None also meant the shared file, so offline tests and
        # the census inherited live breakers: the census undercounted 304 vs 327 after a live run.)
        self.state_path = STATE_DIR / "host_limits.json" if state_path is _STATE_FILE else state_path
        self.min_interval = min_interval
        self.budget_remaining = budget
        self._opener = opener
        self._clock = clock
        self._sleep = sleeper
        self.policies = policies if policies is not None else load_policies()
        self.hosts: dict = {}          # host -> {last_ts, interval, fails, breaker_until}
        self.counts: dict = {}         # host -> requests admitted this run
        self.refusals: dict = {}       # host -> [reason, ...] this run
        self.meta_seen: set = set()    # _meta_key()s whose .meta was fetched this run
        self._robots: dict = {}        # host -> robots verdict, once per run (RFC 9309 §2.4)
        self._robots_why: dict = {}    # host -> why robots.txt was unreachable (TLS, timeout, 5xx)
        self._window: dict = {}        # host -> admitted timestamps inside the rolling window
        if self.state_path and self.state_path.exists():
            try:
                saved = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.hosts = saved.get("hosts", {})
            except (OSError, ValueError):
                self.hosts = {}

    def _entry(self, host: str) -> dict:
        return self.hosts.setdefault(host, {
            "last_ts": 0.0, "interval": self.min_interval,
            "fails": 0, "breaker_until": 0.0})

    def _policy(self, host: str) -> dict:
        p = dict(self.policies.get("_default", {}).get("enforced", {}))
        p.update(self.policies.get("hosts", {}).get(host, {}).get("enforced", {}))
        p.setdefault("run_cap", DEFAULT_RUN_CAP)
        p.setdefault("min_interval_s", self.min_interval)
        return p

    def _robots_for(self, host: str):
        """Fetch robots.txt once per host per run; learn Crawl-delay; keep the verdict. A 5xx or a
        timeout/reset is retried (ROBOTS_ATTEMPTS, backoff 5 s, 10 s) before RFC 9309 §2.3.1.4's complete
        disallow applies: one MITRE gateway 502 refused the first scheduled ATT&CK check (2026-11-05).
        TLS verification failures are not retried; they never change within a run."""
        if host in self._robots:
            return self._robots[host]
        status, body = 0, ""
        for attempt in range(1, ROBOTS_ATTEMPTS + 1):
            status, body, transient = 0, "", False
            self._robots_why.pop(host, None)
            try:
                req = urllib.request.Request(f"https://{host}/robots.txt", headers={"User-Agent": USER_AGENT})
                with self._opener(req, 10) as resp:
                    status = getattr(resp, "status", 200) or 200
                    body = _read_body(resp)[:ROBOTS_MAX_BYTES].decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                status = e.code
            except Exception as e:  # transport failure: name it in the refusal (TLS, timeout, reset)
                reason = getattr(e, "reason", e)
                self._robots_why[host] = f"{type(e).__name__}: {str(reason)[:80]}"
                transient = not isinstance(reason, ssl.SSLError)
            if 500 <= status <= 599:
                self._robots_why[host] = f"HTTP {status}"
                transient = True
            if not transient or attempt == ROBOTS_ATTEMPTS:
                break
            self._sleep(ROBOTS_BACKOFF_S * attempt)
        verdict = robots_verdict(status, body)
        if not isinstance(verdict, str):
            m = re.search(r"(?im)^\s*crawl-delay:\s*(\d+(?:\.\d+)?)", body)
            if m:
                e = self._entry(host)
                e["interval"] = max(e["interval"], float(m.group(1)))
        self._robots[host] = verdict
        return verdict

    def _documented_api(self, host: str, path: str) -> bool:
        """A robots Disallow may be overridden only for a path the issuer's own API documentation
        publishes, and only when BOTH citations are recorded in host_policies.json."""
        for x in self._policy(host).get("documented_api_paths") or []:
            if path.startswith(x.get("prefix", "\0")) and x.get("robots_line") and x.get("api_doc"):
                return True
        return False

    def _refuse(self, host: str, reason: str):
        self.refusals.setdefault(host, []).append(reason)
        raise PolicyRefused(f"{host}: {reason}")

    def wait(self, host: str, url: str = ""):
        """Block until this host may be contacted under its recorded rules.
        Raises HostCooldown / PolicyRefused / RuntimeError (runaway ceiling)."""
        now = self._clock()
        e = self._entry(host)
        if now < e.get("breaker_until", 0.0):
            raise HostCooldown(f"{host} cooling down until {e['breaker_until']:.0f}")
        if self.budget_remaining <= 0:
            raise RuntimeError("fetch budget exhausted for this run")
        p = self._policy(host)
        path = _path_of(url) if url else ""
        if self.counts.get(host, 0) >= int(p["run_cap"]):
            self._refuse(host, f"run cap {p['run_cap']} reached")
        mf = p.get("meta_first")
        if url and mf and re.search(mf, path) and _meta_key(url) not in self.meta_seen:
            self._refuse(host, f"{path.rsplit('/', 1)[-1]} requested before its .meta (published rule)")
        verdict = self._robots_for(host)
        if url and not path.endswith("/robots.txt") and not self._documented_api(host, path):
            if verdict == "disallow_all":
                self._refuse(host, f"robots.txt unreachable ({self._robots_why.get(host, 'no response')}) "
                                   "-> complete disallow (RFC 9309 2.3.1.4)")
            if not isinstance(verdict, str) and not verdict.can_fetch(ROBOTS_AGENT, url):
                self._refuse(host, f"robots.txt disallows {path}")
        e = self._entry(host)
        e["interval"] = max(e["interval"], float(p["min_interval_s"]))
        win = p.get("window")
        if p.get("key_env") and os.environ.get(p["key_env"]) and p.get("window_with_key"):
            win = p["window_with_key"]
        if win:
            n, secs = int(win[0]), float(win[1])
            ts = [t for t in self._window.get(host, []) if self._clock() - t < secs]
            if len(ts) >= n:
                self._sleep(secs - (self._clock() - ts[0]) + 0.05)
            self._window[host] = ts
        wait_for = e["last_ts"] + e["interval"] + random.uniform(0, 0.4) - self._clock()
        if wait_for > 0:
            self._sleep(wait_for)
        e["last_ts"] = self._clock()
        if win:
            self._window[host].append(e["last_ts"])
        self.budget_remaining -= 1
        self.counts[host] = self.counts.get(host, 0) + 1
        if url and path.endswith(".meta"):
            self.meta_seen.add(_meta_key(url))

    def note(self, host: str, status: int, headers=None):
        """Record a response: learn server-provided limits, trip/clear the breaker."""
        e = self._entry(host)
        headers = headers or {}
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                e["interval"] = max(e["interval"], min(float(retry_after), 300.0))
            except ValueError:
                pass  # HTTP-date form — the breaker path below covers it
        reset = headers.get("RateLimit-Reset") or headers.get("X-RateLimit-Reset")
        if reset and status in BREAKER_STATUSES:
            try:
                until = float(reset)
                if until > 1e9:  # epoch form
                    e["breaker_until"] = max(e["breaker_until"], until)
                else:            # delta-seconds form
                    e["breaker_until"] = max(e["breaker_until"], self._clock() + min(until, 3600))
            except ValueError:
                pass
        if status in BREAKER_STATUSES:
            e["fails"] = e.get("fails", 0) + 1
            if e["fails"] >= BREAKER_FAILS:
                e["breaker_until"] = max(e.get("breaker_until", 0.0),
                                         self._clock() + BREAKER_COOLDOWN)
        else:
            e["fails"] = 0

    def ledger(self) -> dict:
        """Per-host requests admitted and refused this run, with distinct refusal reasons."""
        hosts = sorted(set(self.counts) | set(self.refusals))
        return {h: {"requests": self.counts.get(h, 0),
                    "refused": len(self.refusals.get(h, [])),
                    "reasons": sorted(set(self.refusals.get(h, [])))} for h in hosts}

    def save(self):
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"hosts": self.hosts}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")


class FetchCache:
    """Conditional-GET validators + sha256 unchanged detection, persisted per URL."""

    def __init__(self, state_path=_STATE_FILE):
        # Omitted -> the shared .fetch-cache/fetch_state.json; None -> no persisted validators.
        self.state_path = STATE_DIR / "fetch_state.json" if state_path is _STATE_FILE else state_path
        self.hits = 0
        self.misses = 0
        self.urls: dict = {}
        if self.state_path and self.state_path.exists():
            try:
                self.urls = json.loads(self.state_path.read_text(encoding="utf-8")).get("urls", {})
            except (OSError, ValueError):
                self.urls = {}

    def validators(self, url: str) -> dict:
        e = self.urls.get(url, {})
        h = {}
        if e.get("etag"):
            h["If-None-Match"] = e["etag"]
        if e.get("last_modified"):
            h["If-Modified-Since"] = e["last_modified"]
        return h

    def note_response(self, url: str, status: int, headers, body: bytes | None) -> str:
        """Returns 'unchanged' (304 or identical sha) or 'changed'."""
        headers = headers or {}
        if status == 304:
            self.hits += 1
            self.urls.setdefault(url, {})["checked_at"] = time.time()
            return "unchanged"
        sha = hashlib.sha256(body or b"").hexdigest()
        prev = self.urls.get(url, {}).get("sha256")
        self.urls[url] = {
            "etag": headers.get("ETag", "") or headers.get("etag", ""),
            "last_modified": headers.get("Last-Modified", "") or headers.get("last-modified", ""),
            "sha256": sha, "checked_at": time.time(),
        }
        if prev == sha:
            self.hits += 1
            return "unchanged"
        self.misses += 1
        return "changed"

    def cached_sha(self, url: str):
        return self.urls.get(url, {}).get("sha256")

    def save(self):
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"urls": self.urls}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")


# ── shared default instances (lazy — monitors just call the helpers) ─────────
_GOV: RateGovernor | None = None
_CACHE: FetchCache | None = None


def governor() -> RateGovernor:
    global _GOV
    if _GOV is None:
        _GOV = RateGovernor()
    return _GOV


def cache() -> FetchCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = FetchCache()
    return _CACHE


def save_state():
    if _GOV is not None:
        _GOV.save()
    if _CACHE is not None:
        _CACHE.save()


def run_ledger() -> dict:
    """This process's per-host ledger (empty when nothing was fetched)."""
    return _GOV.ledger() if _GOV is not None else {}


def save_ledger(tool: str, state_dir: Path | None = None):
    """Write this process's ledger to .fetch-cache/ledger/<tool>.json for the drift report."""
    d = (state_dir or STATE_DIR) / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tool}.json").write_text(json.dumps(run_ledger(), indent=2, sort_keys=True) + "\n",
                                    encoding="utf-8")


def polite_urlopen(req: urllib.request.Request, timeout: float = 30, gov: RateGovernor | None = None):
    """Drop-in wrapper around urlopen: applies the host's recorded rules (pacing, caps, rolling
    window, meta-first, robots, required headers) and breaker-tracks the host.
    Raises HostCooldown / PolicyRefused."""
    gov = gov or governor()
    host = _host(req.full_url)
    gov.wait(host, req.full_url)
    for k, v in (gov._policy(host).get("require_headers") or {}).items():
        if not req.has_header(k.capitalize()):
            req.add_header(k, v)
    try:
        resp = gov._opener(req, timeout)
    except urllib.error.HTTPError as e:
        gov.note(host, e.code, dict(e.headers or {}))
        raise
    except Exception:
        gov.note(host, 0, {})
        raise
    gov.note(host, resp.status, dict(resp.headers))
    return resp


def resilient_get(url: str, *, gov: RateGovernor | None = None,
                  fcache: FetchCache | None = None,
                  allow_wayback: bool = True, timeout: float = 30,
                  extra_headers: dict | None = None):
    """GET with recorded host rules, conditional headers, and a labeled Wayback fallback that is
    used ONLY on hard failure — never after a PolicyRefused (an archive copy must not route
    around a host's rules or its robots.txt)."""
    gov = gov or governor()
    fcache = fcache or cache()
    trail = []
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip",
               **fcache.validators(url), **(extra_headers or {})}
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = polite_urlopen(req, timeout=timeout, gov=gov)
        body = _read_body(resp)
        verdict = fcache.note_response(url, resp.status, dict(resp.headers), body)
        trail.append(f"live:{resp.status}:{verdict}")
        if verdict == "unchanged":
            return resp.status, None, {"source": "cache", "cache": "unchanged",
                                       "trail": trail, "snapshot_ts": None}
        return resp.status, body, {"source": "live", "cache": verdict,
                                   "trail": trail, "snapshot_ts": None}
    except HostCooldown as e:
        trail.append(f"live:cooldown:{e}")
        return 0, None, {"source": "live", "cache": None, "trail": trail, "snapshot_ts": None}
    except PolicyRefused as e:
        trail.append(f"live:refused:{e}")
        return 0, None, {"source": "live", "cache": None, "trail": trail, "snapshot_ts": None}
    except urllib.error.HTTPError as e:
        if e.code == 304:
            fcache.note_response(url, 304, {}, None)
            trail.append("live:304:unchanged")
            return 304, None, {"source": "cache", "cache": "unchanged",
                               "trail": trail, "snapshot_ts": None}
        trail.append(f"live:{e.code}")
        status = e.code
    except Exception as e:
        trail.append(f"live:error:{type(e).__name__}")
        status = 0
    if not allow_wayback:
        return status, None, {"source": "live", "cache": None, "trail": trail, "snapshot_ts": None}
    try:
        wb_req = urllib.request.Request(WAYBACK_API + url, headers={"User-Agent": USER_AGENT})
        with polite_urlopen(wb_req, timeout=timeout, gov=gov) as resp:
            data = json.loads(_read_body(resp) or b"{}")
        closest = (data.get("archived_snapshots") or {}).get("closest") or {}
        snap_url, snap_ts = closest.get("url"), closest.get("timestamp")
        if not snap_url:
            trail.append("wayback:no-snapshot")
            return status, None, {"source": "live", "cache": None, "trail": trail, "snapshot_ts": None}
        snap_req = urllib.request.Request(snap_url, headers={"User-Agent": USER_AGENT,
                                                             "Accept-Encoding": "gzip"})
        with polite_urlopen(snap_req, timeout=timeout, gov=gov) as resp:
            body = _read_body(resp)
        trail.append(f"wayback:{resp.status}:{snap_ts}")
        return resp.status, body, {"source": "wayback", "cache": None,
                                   "trail": trail, "snapshot_ts": snap_ts}
    except Exception as e:
        trail.append(f"wayback:error:{type(e).__name__}")
        return status, None, {"source": "live", "cache": None, "trail": trail, "snapshot_ts": None}


TRANSIENT = (429, 500, 502, 503, 504)


class Fetched(tuple):
    """(status, headers, body); header names lower-cased."""
    __slots__ = ()
    status = property(lambda s: s[0])
    headers = property(lambda s: s[1])
    body = property(lambda s: s[2])


def fetch(url: str, *, headers: dict | None = None, timeout: float = 60, retries: int = 3,
          retry_on: tuple = TRANSIENT, backoff: float = 2.0, max_bytes: int | None = None,
          gov=None, sleeper=None) -> "Fetched":
    """One governed GET with bounded retries, for every hand-run loader (phase 51).
    Pacing, caps, the breaker and the ledger come from the governor (host_policies.json).
    Retries network errors and `retry_on` statuses with backoff, backoff*2, …; the governor has
    already learned any Retry-After. Any other HTTP status raises at once. PolicyRefused and
    HostCooldown are never retried, so a loader cannot route around a host's rule."""
    sleep = sleeper or time.sleep
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    last = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with polite_urlopen(req, timeout=timeout, gov=gov) as resp:
                body = resp.read(max_bytes) if max_bytes else _read_body(resp)
                return Fetched((getattr(resp, "status", 200) or 200,
                                {k.lower(): v for k, v in dict(resp.headers or {}).items()}, body))
        except (PolicyRefused, HostCooldown):
            raise
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in retry_on or attempt == retries:
                raise
        except Exception as e:  # noqa: BLE001 — transport failure: retry, then raise
            last = e
            if attempt == retries:
                raise
        sleep(backoff * 2 ** (attempt - 1))
    raise last


def run_cli(main, tool: str):
    """Run a loader's main() and always persist learned host limits and this run's ledger
    (.fetch-cache/ledger/<tool>.json) — the weekly rotation reads the ledger (phase 51)."""
    try:
        return main()
    finally:
        save_state()
        save_ledger(tool)
