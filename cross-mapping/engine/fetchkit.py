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
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".fetch-cache"

DEFAULT_MIN_INTERVAL = 1.5   # seconds between requests to one host (plus jitter)
DEFAULT_BUDGET = 600           # runaway ceiling per run (1.8x the 328 measured by the phase-50 census); per-host caps are the guard
DEFAULT_RUN_CAP = 25           # per host per run when a host publishes nothing (busiest such host measured: 19)
ROBOTS_MAX_BYTES = 512 * 1024  # RFC 9309 §2.5: parse at least 500 KiB
ROBOTS_AGENT = "dbz-standards-monitor"   # product token that robots.txt groups are matched against
POLICY_PATH = ROOT / "canonical-sources" / "host_policies.json"
BREAKER_FAILS = 4            # consecutive 403/429/503 before the breaker trips
BREAKER_COOLDOWN = 15 * 60   # seconds
BREAKER_STATUSES = {403, 429, 503}
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) dbz-standards-monitor "
              "(GRC framework currency check; contact via repo)")
WAYBACK_API = "https://archive.org/wayback/available?url="


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


def robots_verdict(status: int, body: str):
    """RFC 9309 status semantics. 2xx -> parse (an HTML page, or a body without directives, is not
    a robots file -> no rules); 4xx 'unavailable' -> allow all (§2.3.1.3); 5xx or a network
    failure 'unreachable' -> complete disallow (§2.3.1.4). Returns "allow_all" | "disallow_all" |
    a RobotFileParser."""
    if status == 0 or 500 <= status <= 599:
        return "disallow_all"
    if 400 <= status <= 499:
        return "allow_all"
    head = body.lstrip()[:300].lower()
    if (head.startswith(("<!doctype", "<html")) or "<head" in head
            or not re.search(r"(?im)^\s*(user-agent|disallow|allow)\s*:", body)):
        return "allow_all"
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_lines(body))
    return rp


def _path_of(url: str) -> str:
    rest = url.split("//", 1)[-1]
    return "/" + rest.split("/", 1)[1] if "/" in rest else "/"


def _meta_key(url: str) -> str:
    """'…/feed.meta' and '…/feed.xml.gz' share the key '…/feed' (meta-first pairing)."""
    return re.sub(r"\.(meta|xml\.gz|xml\.zip|zip|gz|xml)$", "", url.split("?", 1)[0])


class RateGovernor:
    """Per-host pacing + breaker + recorded host usage rules + runaway ceiling.
    Learned limits persist across runs (.fetch-cache/host_limits.json); per-run counts never do."""

    def __init__(self, state_path: Path | None = None, *,
                 min_interval: float = DEFAULT_MIN_INTERVAL,
                 budget: int = DEFAULT_BUDGET,
                 opener=_default_open, clock=time.time, sleeper=time.sleep,
                 policies: dict | None = None):
        self.state_path = state_path if state_path is not None else STATE_DIR / "host_limits.json"
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
        """Fetch robots.txt once per host per run; learn Crawl-delay; keep the verdict."""
        if host in self._robots:
            return self._robots[host]
        status, body = 0, ""
        try:
            req = urllib.request.Request(f"https://{host}/robots.txt",
                                         headers={"User-Agent": USER_AGENT})
            with self._opener(req, 10) as resp:
                status = getattr(resp, "status", 200) or 200
                body = _read_body(resp)[:ROBOTS_MAX_BYTES].decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            status = e.code
        except Exception:
            status = 0
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
                self._refuse(host, "robots.txt unreachable -> complete disallow (RFC 9309 2.3.1.4)")
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

    def __init__(self, state_path: Path | None = None):
        self.state_path = state_path if state_path is not None else STATE_DIR / "fetch_state.json"
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
