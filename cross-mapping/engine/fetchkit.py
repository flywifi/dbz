#!/usr/bin/env python3
"""
fetchkit.py — shared politeness / caching / resilience layer for all live fetching.

The keep-current subsystem talks to ~160 external hosts. This module gives every
caller the same three behaviors so dbz stays a polite citizen of those hosts and
survives their bad days:

  RateGovernor  — per-host pacing (min interval + jitter, robots.txt Crawl-delay),
                  Retry-After / RateLimit-Reset respect, a circuit breaker
                  (4 consecutive 403/429/503 -> 15-min cooldown), a per-run request
                  budget, and persisted learned limits (.fetch-cache/host_limits.json).
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
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".fetch-cache"

DEFAULT_MIN_INTERVAL = 1.5   # seconds between requests to one host (plus jitter)
DEFAULT_BUDGET = 200         # requests per run per governor
BREAKER_FAILS = 4            # consecutive 403/429/503 before the breaker trips
BREAKER_COOLDOWN = 15 * 60   # seconds
BREAKER_STATUSES = {403, 429, 503}
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) dbz-standards-monitor "
              "(GRC framework currency check; contact via repo)")
WAYBACK_API = "https://archive.org/wayback/available?url="


class HostCooldown(Exception):
    """Raised when a host's circuit breaker is active — skip, don't hammer."""


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


class RateGovernor:
    """Per-host pacing + breaker + budget. Persisted across runs."""

    def __init__(self, state_path: Path | None = None, *,
                 min_interval: float = DEFAULT_MIN_INTERVAL,
                 budget: int = DEFAULT_BUDGET,
                 opener=_default_open, clock=time.time, sleeper=time.sleep):
        self.state_path = state_path if state_path is not None else STATE_DIR / "host_limits.json"
        self.min_interval = min_interval
        self.budget_remaining = budget
        self._opener = opener
        self._clock = clock
        self._sleep = sleeper
        self.hosts: dict = {}          # host -> {last_ts, interval, fails, breaker_until}
        self._robots_checked: set = set()
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

    def _robots_crawl_delay(self, host: str):
        """Best-effort, once per host per run; failure -> keep default interval."""
        if host in self._robots_checked:
            return
        self._robots_checked.add(host)
        try:
            req = urllib.request.Request(f"https://{host}/robots.txt",
                                         headers={"User-Agent": USER_AGENT})
            with self._opener(req, 10) as resp:
                text = _read_body(resp).decode("utf-8", errors="replace")
            m = re.search(r"(?im)^crawl-delay:\s*(\d+(?:\.\d+)?)", text)
            if m:
                e = self._entry(host)
                e["interval"] = max(e["interval"], float(m.group(1)))
        except Exception:
            pass

    def wait(self, host: str):
        """Block until this host may be contacted. Raises HostCooldown / RuntimeError."""
        now = self._clock()
        e = self._entry(host)
        if now < e.get("breaker_until", 0.0):
            raise HostCooldown(f"{host} cooling down until {e['breaker_until']:.0f}")
        if self.budget_remaining <= 0:
            raise RuntimeError("fetch budget exhausted for this run")
        self._robots_crawl_delay(host)
        e = self._entry(host)
        wait_for = e["last_ts"] + e["interval"] + random.uniform(0, 0.4) - now
        if wait_for > 0:
            self._sleep(wait_for)
        e["last_ts"] = self._clock()
        self.budget_remaining -= 1

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


def polite_urlopen(req: urllib.request.Request, timeout: float = 30, gov: RateGovernor | None = None):
    """Drop-in wrapper around urlopen that paces + breaker-tracks the host.
    Raises HostCooldown when the host is in cooldown."""
    gov = gov or governor()
    host = _host(req.full_url)
    gov.wait(host)
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
    """GET with pacing, conditional headers, and a labeled Wayback fallback.

    Returns (status, body_bytes_or_None, meta) where meta = {
      "source": "live" | "wayback" | "cache",
      "cache": "unchanged" | "changed" | None,
      "trail": [attempt strings],
      "snapshot_ts": wayback timestamp when source == "wayback",
    }. A 304 / sha-identical response returns body=None with cache="unchanged".
    """
    gov = gov or governor()
    fcache = fcache or cache()
    trail = []
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip",
               **fcache.validators(url), **(extra_headers or {})}
    req = urllib.request.Request(url, headers=headers)

    # prong 1 — live
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

    # prong 2 — Wayback, hard-fail only, ALWAYS labeled
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
