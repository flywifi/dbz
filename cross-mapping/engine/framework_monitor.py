#!/usr/bin/env python3
"""
Framework Update Monitor — GRC news-feed crawler.

Reads feed_registry.json, checks each authoritative source for version changes,
and outputs a news-feed JSON (`framework_updates_feed.json`) that records what
changed, when, and which source_manifest.json keys need re-pinning.

The monitor is designed to be run on a schedule (cron / CI / manual).
Each run produces a diff vs the previous feed and flags NEW or CHANGED items.

Strategies implemented
----------------------
  poll_landing   : HTTP HEAD/GET → inspect ETag, Last-Modified, content hash
  github_release : GitHub Releases API → latest tag and published_at
  rss_feed       : Parse RSS/Atom feed URL for latest entry

Usage:
    python framework_monitor.py [--registry canonical-sources/feed_registry.json]
                                [--out cross-mapping/output/framework_updates_feed.json]
                                [--dry-run]

Requirements: requests (standard; stdlib fallback via urllib for basic HEAD checks)
"""

import hashlib
import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _github_auth_header() -> dict:
    """
    Return an Authorization header for the GitHub API only when the
    'github_authenticated' feature flag is effective (enabled + GITHUB_TOKEN set).
    Off by default → unauthenticated public access (lower rate limit).
    """
    try:
        from feature_flags import FeatureFlags
        flags = FeatureFlags.load()
        if flags.effective("github_authenticated"):
            token = os.environ.get("GITHUB_TOKEN", "")
            if token:
                return {"Authorization": f"Bearer {token}"}
    except Exception:
        pass
    return {}

DEFAULT_REGISTRY = _REPO_ROOT / "canonical-sources" / "feed_registry.json"
DEFAULT_OUT = _HERE.parent / "output" / "framework_updates_feed.json"

MONITOR_VERSION = "1.0.0"

USER_AGENT = (
    "dbz-grc-framework-monitor/1.0 "
    "(GRC compliance update tracker; github.com/flywifi/dbz)"
)

TIMEOUT = 15


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _http_head(url: str) -> dict:
    """
    Send HEAD request to url. Returns metadata dict:
      {status, etag, last_modified, content_length, error}
    """
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return {
                "status": resp.status,
                "etag": resp.headers.get("ETag", ""),
                "last_modified": resp.headers.get("Last-Modified", ""),
                "content_length": resp.headers.get("Content-Length", ""),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        return {"status": e.code, "etag": "", "last_modified": "", "content_length": "", "error": str(e)}
    except Exception as e:
        return {"status": 0, "etag": "", "last_modified": "", "content_length": "", "error": str(e)}


def _http_get_text(url: str, max_bytes: int = 32768) -> Optional[str]:
    """Fetch up to max_bytes of text from url. Returns None on error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None


def _content_fingerprint(url: str) -> str:
    """Return a short hash of the first 32KB of content at url."""
    text = _http_get_text(url)
    if text is None:
        return ""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── GitHub Releases strategy ───────────────────────────────────────────────────

GITHUB_API = "https://api.github.com"


def _github_latest_release(repo: str) -> dict:
    """
    Query GitHub Releases API for repo (e.g. 'GSA/fedramp-automation').
    Returns {tag_name, published_at, html_url, prerelease, error}.
    """
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                **_github_auth_header(),  # opt-in via 'github_authenticated' flag
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
            return {
                "tag_name": data.get("tag_name", ""),
                "published_at": data.get("published_at", ""),
                "html_url": data.get("html_url", ""),
                "prerelease": data.get("prerelease", False),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        # 404 = no releases yet
        if e.code == 404:
            return _github_latest_tag(repo)
        return {"tag_name": "", "published_at": "", "html_url": "", "prerelease": False,
                "error": str(e)}
    except Exception as e:
        return {"tag_name": "", "published_at": "", "html_url": "", "prerelease": False,
                "error": str(e)}


def _github_latest_tag(repo: str) -> dict:
    """Fallback: get latest tag from GitHub tags API."""
    url = f"{GITHUB_API}/repos/{repo}/tags"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json",
                     **_github_auth_header()},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            tags = json.loads(resp.read())
            if tags:
                return {
                    "tag_name": tags[0].get("name", ""),
                    "published_at": "",
                    "html_url": f"https://github.com/{repo}/releases/tag/{tags[0].get('name','')}",
                    "prerelease": False,
                    "error": None,
                }
    except Exception:
        pass
    return {"tag_name": "", "published_at": "", "html_url": "", "prerelease": False, "error": "no tags"}


# ── RSS/Atom strategy ──────────────────────────────────────────────────────────

_ITEM_DATE_RE = re.compile(
    r"<(?:pubDate|updated|dc:date)>([^<]+)</", re.IGNORECASE
)
_ITEM_TITLE_RE = re.compile(r"<(?:title)>([^<]+)</", re.IGNORECASE)
_LINK_RE = re.compile(r"<(?:link|id)>([^<]+)</", re.IGNORECASE)


def _parse_rss_latest(url: str) -> dict:
    """
    Fetch RSS/Atom feed and extract the most recent entry date.
    Returns {latest_date, latest_title, latest_link, error}.
    """
    text = _http_get_text(url, max_bytes=65536)
    if text is None:
        return {"latest_date": "", "latest_title": "", "latest_link": "", "error": "fetch failed"}
    dates = _ITEM_DATE_RE.findall(text)
    titles = _ITEM_TITLE_RE.findall(text)
    links = _LINK_RE.findall(text)
    return {
        "latest_date": dates[0].strip() if dates else "",
        "latest_title": titles[1].strip() if len(titles) > 1 else (titles[0].strip() if titles else ""),
        "latest_link": links[0].strip() if links else url,
        "error": None,
    }


# ── Per-strategy check ─────────────────────────────────────────────────────────

def _check_feed_entry(feed_id: str, entry: dict) -> dict:
    """
    Run the appropriate check strategy for one feed entry.
    Returns a status record:
      {feed_id, strategy, checked_at, version_signal, version_detected,
       last_modified_header, etag, fingerprint, release_tag, release_date,
       release_url, error, update_likely}
    """
    strategy = entry.get("check_strategy", "poll_landing")
    urls = entry.get("urls", {})
    checked_at = datetime.now(timezone.utc).isoformat()

    result = {
        "feed_id": feed_id,
        "label": entry.get("label", ""),
        "strategy": strategy,
        "checked_at": checked_at,
        "current_version": entry.get("current_version", ""),
        "last_known_change": entry.get("last_changed", ""),
        "source_manifest_keys": entry.get("source_manifest_keys", []),
        "version_signal": "",
        "last_modified_header": "",
        "etag": "",
        "fingerprint": "",
        "release_tag": "",
        "release_date": "",
        "release_url": "",
        "rss_latest_date": "",
        "rss_latest_title": "",
        "error": None,
        "update_likely": False,
        "update_notes": "",
    }

    # Feeds explicitly exempt from live polling (artifact already on disk, or the
    # origin presents a cert chain we cannot verify from this environment) report a
    # clean note rather than an error, so the run stays green.
    if strategy == "manual" or entry.get("poll_exempt"):
        result["version_signal"] = "manual"
        result["update_notes"] = entry.get("poll_exempt_reason", "poll-exempt (verify manually)")
        return result

    if strategy == "github_release":
        repo = entry.get("github_repo", "")
        if not repo:
            result["error"] = "github_repo not set"
            return result
        rel = _github_latest_release(repo)
        result.update({
            "release_tag": rel.get("tag_name", ""),
            "release_date": rel.get("published_at", ""),
            "release_url": rel.get("html_url", ""),
            "error": rel.get("error"),
        })
        if rel.get("tag_name"):
            result["version_signal"] = rel["tag_name"]

    elif strategy == "rss_feed":
        rss_url = urls.get("rss") or urls.get("feed", "")
        if not rss_url:
            result["error"] = "no rss/feed URL in entry"
            return result
        rss = _parse_rss_latest(rss_url)
        result.update({
            "rss_latest_date": rss.get("latest_date", ""),
            "rss_latest_title": rss.get("latest_title", ""),
            "version_signal": rss.get("latest_date", ""),
            "error": rss.get("error"),
        })

    else:  # poll_landing (default)
        landing_url = urls.get("landing", "")
        if not landing_url:
            result["error"] = "no landing URL"
            return result
        head = _http_head(landing_url)
        last_mod = head.get("last_modified", "")
        etag = head.get("etag", "")
        result.update({
            "last_modified_header": last_mod,
            "etag": etag,
            "error": head.get("error"),
        })
        # Many GRC landing pages (csrc.nist.gov etc.) serve no Last-Modified/ETag,
        # so fall back to a content fingerprint as the version signal.
        if not head.get("error"):
            if last_mod or etag:
                result["version_signal"] = last_mod or etag
            else:
                fp = _content_fingerprint(landing_url)
                result["fingerprint"] = fp
                result["version_signal"] = f"fp:{fp}" if fp else ""

    return result


# ── Change detection ───────────────────────────────────────────────────────────

def _detect_changes(current_results: List[dict], previous_feed: Optional[dict]) -> List[dict]:
    """
    Compare current check results against the previous feed.
    Annotate each result with change_status: new | changed | unchanged | unknown.
    """
    if not previous_feed:
        for r in current_results:
            r["change_status"] = "new"
        return current_results

    prev_by_id = {r["feed_id"]: r for r in previous_feed.get("results", [])}

    for r in current_results:
        fid = r["feed_id"]
        prev = prev_by_id.get(fid)
        if prev is None:
            r["change_status"] = "new"
            continue

        # Compare version signals
        prev_sig = prev.get("version_signal", "")
        curr_sig = r.get("version_signal", "")
        prev_tag = prev.get("release_tag", "")
        curr_tag = r.get("release_tag", "")
        prev_fp  = prev.get("fingerprint", "")
        curr_fp  = r.get("fingerprint", "")

        if curr_sig and prev_sig and curr_sig != prev_sig:
            r["change_status"] = "changed"
            r["previous_version_signal"] = prev_sig
            r["update_likely"] = True
            r["update_notes"] = f"Version signal changed: {prev_sig!r} → {curr_sig!r}"
        elif curr_tag and prev_tag and curr_tag != prev_tag:
            r["change_status"] = "changed"
            r["previous_release_tag"] = prev_tag
            r["update_likely"] = True
            r["update_notes"] = f"Release tag changed: {prev_tag!r} → {curr_tag!r}"
        elif curr_fp and prev_fp and curr_fp != prev_fp:
            r["change_status"] = "changed"
            r["previous_fingerprint"] = prev_fp
            r["update_likely"] = True
            r["update_notes"] = f"Content fingerprint changed (possible update)"
        elif r.get("error"):
            r["change_status"] = "error"
        else:
            r["change_status"] = "unchanged"

    return current_results


# ── Main ────────────────────────────────────────────────────────────────────────

def run_monitor(
    registry_path: Path = DEFAULT_REGISTRY,
    out_path: Path = DEFAULT_OUT,
    dry_run: bool = False,
    feed_ids: Optional[List[str]] = None,
) -> dict:
    """
    Run the framework monitor. Returns the full feed dict.

    Parameters
    ----------
    registry_path : Path to feed_registry.json
    out_path      : Where to write the output feed
    dry_run       : If True, print results but don't write the output file
    feed_ids      : If given, only check these feed IDs (for targeted updates)
    """
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)

    feeds: dict = registry.get("feeds", {})

    # Load previous feed if it exists (for change detection)
    previous_feed = None
    if out_path.exists():
        try:
            with open(out_path, encoding="utf-8") as f:
                previous_feed = json.load(f)
        except Exception:
            pass

    target_ids = feed_ids or list(feeds.keys())
    results = []

    print(f"[*] Checking {len(target_ids)} framework sources …")
    for fid in target_ids:
        entry = feeds.get(fid)
        if not entry:
            print(f"    [warn] Unknown feed_id: {fid}")
            continue
        print(f"    [{fid}] strategy={entry.get('check_strategy','poll_landing')} …", end=" ")
        r = _check_feed_entry(fid, entry)
        results.append(r)
        if r.get("error"):
            print(f"ERROR: {r['error']}")
        else:
            print(f"OK  version_signal={r.get('version_signal','—')!r}")

    results = _detect_changes(results, previous_feed)

    changed = [r for r in results if r.get("change_status") == "changed"]
    errors  = [r for r in results if r.get("error") and r.get("change_status") != "changed"]

    # Action items: which source_manifest.json keys need re-pinning?
    action_items = []
    for r in changed:
        for key in r.get("source_manifest_keys", []):
            action_items.append({
                "action": "re-pin source_manifest.json",
                "manifest_key": key,
                "reason": r.get("update_notes", ""),
                "feed_id": r["feed_id"],
                "label": r.get("label", ""),
            })

    feed_doc = {
        "_schema_version": MONITOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_path": str(registry_path),
        "summary": {
            "total_checked": len(results),
            "changed": len(changed),
            "errors": len(errors),
            "unchanged": len([r for r in results if r.get("change_status") == "unchanged"]),
        },
        "action_items": action_items,
        "results": results,
    }

    if changed:
        print(f"\n[!] {len(changed)} CHANGED source(s):")
        for r in changed:
            print(f"    {r['feed_id']}: {r.get('update_notes', '')}")

    if action_items:
        print(f"\n[!] Action items — re-pin source_manifest.json for:")
        for ai in action_items:
            print(f"    {ai['manifest_key']}  ({ai['feed_id']})")

    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(feed_doc, f, indent=2, ensure_ascii=False)
        print(f"\n[✓] Feed written: {out_path}")
    else:
        print("\n[dry-run] Feed NOT written (--dry-run)")

    return feed_doc


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="GRC Framework Update Monitor")
    parser.add_argument(
        "--registry", "-r",
        default=str(DEFAULT_REGISTRY),
        help="Path to feed_registry.json",
    )
    parser.add_argument(
        "--out", "-o",
        default=str(DEFAULT_OUT),
        help="Output path for framework_updates_feed.json",
    )
    parser.add_argument(
        "--feed", "-f",
        nargs="+",
        help="Only check these feed IDs (space-separated)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print results without writing the output file",
    )
    args = parser.parse_args()

    run_monitor(
        registry_path=Path(args.registry),
        out_path=Path(args.out),
        dry_run=args.dry_run,
        feed_ids=args.feed,
    )


if __name__ == "__main__":
    main()
