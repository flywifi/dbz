#!/usr/bin/env python3
"""
GRC Framework Crawler — the "transverser" that seeds the update repository.

A polite, robots-respecting crawler that walks the official download pages of
GRC frameworks (NIST, FedRAMP, CMMC, HITRUST, ISO, DISA, CSA, AICPA, HHS),
discovers downloadable standards artifacts (PDF / Excel / CSV / JSON), and
reports what is NEW or CHANGED versus stored sha256 / size / Last-Modified
baselines. This is how the catalog stays current: run it on a schedule, and
it tells you exactly which source files to re-download and re-pin.

Design (ethical public-data crawler — NOT an evasion tool)
----------------------------------------------------------
  - Respects robots.txt (skips disallowed paths) — compliance, not bypass.
  - One honest, identifying User-Agent (no browser-impersonation / rotation).
  - Polite randomized delays; honors Retry-After / RateLimit-Reset and backs
    OFF on 429/503 rather than hammering.
  - Detects JS-required / CAPTCHA pages and reports them instead of faking a scrape.
  - Single-domain scoping: only follows links within each seed's registered domain.

Pattern adapted from the educator-tools standards-updater crawler
(tools/standards_refresh.py) — the proven "detect → polite-crawl → report" design.

Stdlib only (urllib + robotparser + html.parser). Network required for --crawl.

Usage
-----
  python3 framework_crawler.py --check                      # offline: validate registry + plan
  python3 framework_crawler.py --crawl                      # discover docs, report NEW/CHANGED
  python3 framework_crawler.py --crawl --feed nist-800-53   # one framework only
  python3 framework_crawler.py --crawl --update-baselines   # save discovered docs as the new baseline
  python3 framework_crawler.py --crawl --report out.json    # write the crawl report JSON
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

DEFAULT_REGISTRY = _REPO_ROOT / "canonical-sources" / "feed_registry.json"
DEFAULT_BASELINE = _REPO_ROOT / "canonical-sources" / "crawl_baselines.json"
DEFAULT_REPORT = _HERE.parent / "output" / "framework_crawl_report.json"

CRAWLER_VERSION = "1.0.0"


def _cloud_render_enabled() -> bool:
    """True only when the 'cloud_render' feature flag is effective (opt-in)."""
    try:
        from feature_flags import FeatureFlags
        return FeatureFlags.load().effective("cloud_render")
    except Exception:
        return False

# Downloadable standards artifacts we care about
DOC_EXTS = (".pdf", ".xlsx", ".xlsm", ".xls", ".csv", ".json", ".docx", ".zip", ".oscal")

DEFAULT_UA = (
    "dbz-grc-framework-crawler/1.0 "
    "(+polite GRC framework update checker; respects robots.txt; github.com/flywifi/dbz)"
)

JS_INDICATORS = ("enable javascript", "javascript is required",
                 "please enable javascript", "<noscript")
CAPTCHA_INDICATORS = ("recaptcha", "hcaptcha", "verify you are human",
                      "prove you are human", "cloudflare")


# ── Link extraction ─────────────────────────────────────────────────────────────

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(v)


def reg_domain(netloc: str) -> str:
    """Registered domain: last two labels of the host (ignores port/subdomain)."""
    return ".".join(netloc.lower().split(":")[0].split(".")[-2:])


def _retry_after_seconds(headers: dict) -> Optional[float]:
    """Honor the server's own backoff: Retry-After (secs or HTTP-date) / RateLimit-Reset."""
    if not headers:
        return None
    h = {k.lower(): v for k, v in headers.items()}
    ra = h.get("retry-after")
    if ra:
        try:
            return float(int(str(ra).strip()))
        except ValueError:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(ra)
                return max(0.0, (dt - datetime.now(dt.tzinfo)).total_seconds())
            except Exception:
                return None
    reset = h.get("ratelimit-reset") or h.get("x-ratelimit-reset")
    if reset:
        try:
            return float(int(str(reset).strip()))
        except ValueError:
            return None
    return None


# ── Polite, robots-respecting fetcher ───────────────────────────────────────────

class Fetcher:
    """Honest, robots-respecting, polite fetcher. Backs off; never evades."""

    def __init__(self, ua: str = DEFAULT_UA, timeout: float = 30.0,
                 respect_robots: bool = True):
        self.ua = ua
        self.timeout = timeout
        self.respect_robots = respect_robots
        self._robots: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        pr = urllib.parse.urlparse(url)
        base = f"{pr.scheme}://{pr.netloc}"
        if base not in self._robots:
            self._robots[base] = self._load_robots(base)
        rp = self._robots[base]
        # rp is None when there is no *valid* robots.txt → standard interpretation: allowed
        return True if rp is None else rp.can_fetch(self.ua, url)

    def _load_robots(self, base: str) -> Optional[urllib.robotparser.RobotFileParser]:
        """
        Fetch and parse robots.txt, but only honor it when it is a *real* robots
        file. Many gov sites (e.g. csrc.nist.gov) serve an HTML soft-404 for
        /robots.txt; RobotFileParser mis-parses that into "disallow all". We
        guard against that: if the body isn't plausibly a robots file, treat the
        site as having no robots.txt (→ allowed), which is the correct reading.
        """
        robots_url = base + "/robots.txt"
        req = urllib.request.Request(robots_url, headers={"User-Agent": self.ua})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                ctype = resp.headers.get("Content-Type", "").lower()
                body = resp.read(65536).decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            # 404/410 → no robots.txt → allowed. 401/403 → be conservative, disallow.
            if e.code in (401, 403):
                rp = urllib.robotparser.RobotFileParser()
                rp.disallow_all = True
                return rp
            return None
        except Exception:
            return None  # unreachable → treat as allowed (matches stdlib behavior)

        # Validate it's actually a robots.txt, not an HTML error page
        low = body.lstrip().lower()
        looks_html = low.startswith("<!doctype") or low.startswith("<html") or "<head" in low[:200]
        has_directives = bool(re.search(r"(?im)^\s*(user-agent|disallow|allow|sitemap)\s*:", body))
        if looks_html or not has_directives:
            return None  # bogus/empty robots → no restrictions

        rp = urllib.robotparser.RobotFileParser()
        rp.parse(body.splitlines())
        return rp

    def get(self, url: str) -> Tuple[int, bytes, str, dict]:
        """Return (status, body, content_type, headers). status 0 on transport error."""
        headers = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return (resp.status, resp.read(),
                        resp.headers.get("Content-Type", ""), dict(resp.headers))
        except urllib.error.HTTPError as e:
            return e.code, b"", "", dict(getattr(e, "headers", {}) or {})
        except Exception:
            return 0, b"", "", {}

    def head(self, url: str) -> Tuple[int, dict]:
        """HEAD request for cheap metadata (size, Last-Modified, ETag)."""
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": self.ua})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, dict(getattr(e, "headers", {}) or {})
        except Exception:
            return 0, {}


def detect_obstacles(html: str) -> dict:
    low = html.lower()
    return {
        "js_required": any(t in low for t in JS_INDICATORS) or len(html.strip()) < 500,
        "captcha": any(t in low for t in CAPTCHA_INDICATORS),
    }


# ── Document discovery crawl ────────────────────────────────────────────────────

def crawl_seed(
    seed_url: str,
    fetcher: Fetcher,
    max_pages: int = 25,
    max_depth: int = 1,
    min_delay: float = 1.0,
    max_delay: float = 2.5,
    max_retries: int = 2,
    doc_exts: Tuple[str, ...] = DOC_EXTS,
) -> Tuple[Dict[str, str], dict]:
    """
    Crawl a single seed page (and up to max_depth of same-domain links),
    discovering downloadable document links (PDF/Excel/CSV/JSON).

    Returns (docs, report):
      docs   : dict[absolute_doc_url → filename]
      report : crawl diagnostics (visited, skipped_robots, js_required, etc.)
    """
    seen, docs, retries = set(), {}, {}
    report = {
        "seed": seed_url,
        "visited": 0,
        "skipped_robots": [],
        "js_required": [],
        "captcha": [],
        "rate_limited": [],
        "errors": [],
        "stop_reason": None,
    }
    allowed_dom = reg_domain(urllib.parse.urlparse(seed_url).netloc)
    queue: List[Tuple[str, int]] = [(seed_url, 0)]

    while queue and report["visited"] < max_pages:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        if not fetcher.allowed(url):
            seen.add(url)
            report["skipped_robots"].append(url)
            continue

        status, body, ctype, headers = fetcher.get(url)

        if status in (429, 503):  # honor backoff, retry a bounded number of times
            wait = min(_retry_after_seconds(headers) or (max_delay * 2), 120.0)
            if retries.get(url, 0) < max_retries:
                retries[url] = retries.get(url, 0) + 1
                time.sleep(wait)
                queue.insert(0, (url, depth))  # re-try SAME url; never evade
                continue
            seen.add(url)
            report["rate_limited"].append(url)
            continue

        seen.add(url)
        if status == 0 or status >= 400 or not body:
            report["errors"].append(f"{url} (status {status})")
            continue

        report["visited"] += 1
        time.sleep(random.uniform(min_delay, max_delay))  # polite jitter

        if "html" not in ctype.lower():
            continue
        text = body.decode("utf-8", "ignore")

        flags = detect_obstacles(text)
        if flags["captcha"]:
            report["captcha"].append(url)
        if flags["js_required"]:
            report["js_required"].append(url)  # reported, not faked

        parser = LinkParser()
        try:
            parser.feed(text)
        except Exception:
            continue

        for href in parser.links:
            absu = urllib.parse.urljoin(url, href).split("#")[0]
            pr = urllib.parse.urlparse(absu)
            if pr.scheme not in ("http", "https"):
                continue
            if reg_domain(pr.netloc) != allowed_dom:
                continue
            if pr.path.lower().endswith(doc_exts):
                fname = urllib.parse.unquote(pr.path.rsplit("/", 1)[-1])
                docs.setdefault(absu, fname)
            elif depth < max_depth and absu not in seen:
                queue.append((absu, depth + 1))

    if report["stop_reason"] is None:
        report["stop_reason"] = ("max_pages" if report["visited"] >= max_pages
                                 else "frontier_exhausted")
    return docs, report


# ── Document fingerprinting (NEW/CHANGED detection) ─────────────────────────────

def fingerprint_doc(url: str, fetcher: Fetcher) -> dict:
    """
    Cheap fingerprint of a document via HEAD (size + Last-Modified + ETag).
    Falls back to a content hash of the first 256KB if HEAD gives nothing.
    """
    status, headers = fetcher.head(url)
    h = {k.lower(): v for k, v in headers.items()}
    size = h.get("content-length", "")
    last_mod = h.get("last-modified", "")
    etag = h.get("etag", "")

    fp = {
        "url": url,
        "status": status,
        "size": size,
        "last_modified": last_mod,
        "etag": etag,
        "content_hash": "",
    }

    # If the server gives no useful metadata, hash a content sample
    if status == 200 and not (size or last_mod or etag):
        gstatus, body, _, _ = fetcher.get(url)
        if gstatus == 200 and body:
            fp["content_hash"] = hashlib.sha256(body[:262144]).hexdigest()[:16]

    return fp


def _doc_signature(fp: dict) -> str:
    """Stable comparison signature for a document fingerprint."""
    return "|".join([
        str(fp.get("size", "")),
        str(fp.get("last_modified", "")),
        str(fp.get("etag", "")),
        str(fp.get("content_hash", "")),
    ])


# ── Change intelligence ─────────────────────────────────────────────────────────

def classify_changes(
    feed_id: str,
    discovered: Dict[str, dict],
    baseline_docs: Dict[str, dict],
    authority: str = "primary",
) -> List[dict]:
    """
    Compare discovered document fingerprints against the stored baseline.
    Returns change records with status (new|changed|unchanged) and confidence.

    Confidence scoring (mirrors standards-updater monitoring_policy):
      - primary-source change with size+last_modified delta  → 0.9
      - primary-source change with only one signal           → 0.7
      - secondary-source change (discovery only)             → 0.4
    """
    changes = []
    for url, fp in discovered.items():
        base = baseline_docs.get(url)
        sig = _doc_signature(fp)
        if base is None:
            changes.append({
                "feed_id": feed_id,
                "url": url,
                "filename": fp.get("filename", ""),
                "change_status": "new",
                "signal": sig,
                "confidence": 0.9 if authority == "primary" else 0.4,
                "human_review_required": True,
            })
            continue
        base_sig = _doc_signature(base)
        if sig != base_sig:
            # Count how many independent signals changed
            deltas = sum([
                fp.get("size") != base.get("size"),
                fp.get("last_modified") != base.get("last_modified"),
                fp.get("etag") != base.get("etag"),
                fp.get("content_hash") != base.get("content_hash"),
            ])
            if authority == "primary":
                conf = 0.9 if deltas >= 2 else 0.7
            else:
                conf = 0.4
            changes.append({
                "feed_id": feed_id,
                "url": url,
                "filename": fp.get("filename", ""),
                "change_status": "changed",
                "signal": sig,
                "previous_signal": base_sig,
                "signals_changed": deltas,
                "confidence": conf,
                "human_review_required": True,
            })
    return changes


# ── Orchestration ───────────────────────────────────────────────────────────────

def run_crawl(
    registry_path: Path = DEFAULT_REGISTRY,
    baseline_path: Path = DEFAULT_BASELINE,
    report_path: Path = DEFAULT_REPORT,
    feed_ids: Optional[List[str]] = None,
    update_baselines: bool = False,
    respect_robots: bool = True,
    max_pages: int = 25,
    timeout: float = 30.0,
    dry_run: bool = False,
) -> dict:
    """
    Crawl framework download pages, discover standards docs, report NEW/CHANGED.

    The crawl_seeds + download_pages come from feed_registry.json.
    Baselines persist in crawl_baselines.json (sha256/size/last-modified per doc).
    """
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)
    feeds = registry.get("feeds", {})

    baselines = {}
    if baseline_path.exists():
        try:
            with open(baseline_path, encoding="utf-8") as f:
                baselines = json.load(f)
        except Exception:
            baselines = {}

    fetcher = Fetcher(timeout=timeout, respect_robots=respect_robots)
    target_ids = feed_ids or list(feeds.keys())

    all_changes = []
    per_feed_reports = []
    new_baselines = dict(baselines.get("docs", {}))

    print(f"[*] Crawling {len(target_ids)} framework download surfaces …")
    for fid in target_ids:
        entry = feeds.get(fid)
        if not entry:
            print(f"    [warn] unknown feed_id: {fid}")
            continue

        authority = entry.get("authority", "primary")
        urls = entry.get("urls", {})
        # Seeds: explicit crawl_seeds, else download pages, else the landing page
        seeds = entry.get("crawl_seeds") or []
        if not seeds:
            for key in ("download_page", "github", "landing"):
                if urls.get(key):
                    seeds.append(urls[key])
                    break

        feed_docs: Dict[str, dict] = {}

        # 1) Known direct document URLs from the registry (authoritative, human-curated).
        #    These are the .xlsx/.pdf/.json files NIST/etc. publish directly. We watch
        #    them for size/last-modified changes regardless of whether the SPA page
        #    that lists them is crawlable.
        known_doc_urls = [
            u for k, u in urls.items()
            if isinstance(u, str) and u.lower().rsplit("?", 1)[0].endswith(DOC_EXTS)
        ]
        for url in known_doc_urls:
            fp = fingerprint_doc(url, fetcher)
            fp["filename"] = urllib.parse.unquote(
                urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
            fp["discovery"] = "registry_known"
            feed_docs[url] = fp

        # 2) Crawl the seed pages to DISCOVER new downloadable docs (PDF/Excel).
        for seed in seeds:
            print(f"    [{fid}] crawl {seed} …", end=" ")
            docs, crawl_report = crawl_seed(
                seed, fetcher, max_pages=max_pages)
            per_feed_reports.append({"feed_id": fid, **crawl_report})
            print(f"{len(docs)} doc(s), visited {crawl_report['visited']}")

            for url, fname in docs.items():
                if url in feed_docs:
                    continue
                fp = fingerprint_doc(url, fetcher)
                fp["filename"] = fname
                fp["discovery"] = "crawl"
                feed_docs[url] = fp

        # Detect changes vs baseline
        changes = classify_changes(
            fid, feed_docs, baselines.get("docs", {}), authority)
        all_changes.extend(changes)

        # Stage new baseline entries
        for url, fp in feed_docs.items():
            new_baselines[url] = fp

    new = [c for c in all_changes if c["change_status"] == "new"]
    changed = [c for c in all_changes if c["change_status"] == "changed"]

    # JS-required pages found across all feeds — these need cloud_render to crawl.
    js_pages = sorted({u for r in per_feed_reports for u in r.get("js_required", [])})
    cloud_render_on = _cloud_render_enabled()

    report_doc = {
        "_schema_version": CRAWLER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_path": str(registry_path),
        "robots_respected": respect_robots,
        "user_agent": DEFAULT_UA,
        "cloud_render_enabled": cloud_render_on,
        "summary": {
            "feeds_crawled": len(target_ids),
            "docs_discovered": len(new_baselines),
            "new": len(new),
            "changed": len(changed),
            "js_required_skipped": 0 if cloud_render_on else len(js_pages),
        },
        "new_documents": new,
        "changed_documents": changed,
        "js_required_pages": js_pages,
        "crawl_diagnostics": per_feed_reports,
    }

    print(f"\n[*] {len(new)} NEW, {len(changed)} CHANGED downloadable standards artifact(s)")
    for c in new[:20]:
        print(f"    NEW     [{c['feed_id']}] {c['filename']}  (conf {c['confidence']})")
    for c in changed[:20]:
        print(f"    CHANGED [{c['feed_id']}] {c['filename']}  (conf {c['confidence']})")
    if js_pages and not cloud_render_on:
        print(f"\n[i] {len(js_pages)} JS-required page(s) skipped. "
              f"Enable the 'cloud_render' feature flag to crawl them "
              f"(python3 feature_flags.py --enable cloud_render + set FIRECRAWL_API_KEY).")

    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_doc, f, indent=2, ensure_ascii=False)
        print(f"\n[✓] Crawl report: {report_path}")

        if update_baselines:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            with open(baseline_path, "w", encoding="utf-8") as f:
                json.dump({
                    "_schema_version": CRAWLER_VERSION,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "docs": new_baselines,
                }, f, indent=2, ensure_ascii=False)
            print(f"[✓] Baselines updated: {baseline_path} ({len(new_baselines)} docs)")

    return report_doc


def check_registry(registry_path: Path = DEFAULT_REGISTRY) -> int:
    """Offline validation: confirm every feed has a crawlable surface."""
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)
    feeds = registry.get("feeds", {})
    issues = 0
    print(f"[*] Validating {len(feeds)} feed entries …")
    for fid, entry in feeds.items():
        urls = entry.get("urls", {})
        seeds = entry.get("crawl_seeds") or []
        surfaces = seeds or [urls[k] for k in ("download_page", "github", "landing") if urls.get(k)]
        if not surfaces:
            print(f"    [✗] {fid}: no crawlable surface (need crawl_seeds or a landing/download URL)")
            issues += 1
        else:
            print(f"    [✓] {fid}: {len(surfaces)} surface(s)")
    if issues:
        print(f"\n[✗] {issues} feed(s) have no crawlable surface")
        return 1
    print("\n[✓] All feeds have a crawlable surface")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GRC Framework Crawler (transverser)")
    ap.add_argument("--registry", "-r", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--baseline", "-b", default=str(DEFAULT_BASELINE))
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    ap.add_argument("--feed", "-f", nargs="+", help="only crawl these feed IDs")
    ap.add_argument("--check", action="store_true", help="offline registry validation")
    ap.add_argument("--crawl", action="store_true", help="run the crawl")
    ap.add_argument("--update-baselines", action="store_true",
                    help="save discovered docs as the new baseline")
    ap.add_argument("--max-pages", type=int, default=25)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--no-robots", action="store_true",
                    help="(not recommended) ignore robots.txt")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if a.check:
        return check_registry(Path(a.registry))

    if a.crawl:
        run_crawl(
            registry_path=Path(a.registry),
            baseline_path=Path(a.baseline),
            report_path=Path(a.report),
            feed_ids=a.feed,
            update_baselines=a.update_baselines,
            respect_robots=not a.no_robots,
            max_pages=a.max_pages,
            timeout=a.timeout,
            dry_run=a.dry_run,
        )
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
