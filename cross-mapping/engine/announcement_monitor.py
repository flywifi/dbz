#!/usr/bin/env python3
"""
announcement_monitor.py
Monitors RSS/Atom announcement feeds from standards bodies for early-warning
signals about framework updates. Precedes file-level changes by weeks.

Output: canonical-sources/announcements_feed.json

Usage:
    python3 announcement_monitor.py [--dry-run] [--feed FEED_ID] [--days N]
    python3 announcement_monitor.py --dry-run --feed nist-800-53
    python3 announcement_monitor.py --feed fedramp --days 90
"""

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = REPO_ROOT / "canonical-sources" / "feed_registry.json"
OUTPUT_PATH = REPO_ROOT / "canonical-sources" / "announcements_feed.json"

WINDOW_DAYS_DEFAULT = 180
TIMEOUT = 20
USER_AGENT = "dbz-announcement-monitor/1.0 (GRC cross-mapping research)"

# Regex scoring rules for change_type classification.
# Each entry: list of (pattern, weight) pairs.
# Winning type = highest (sum_matched / max_possible) ratio, threshold 0.15.
CHANGE_TYPE_RULES: dict[str, list[tuple[str, float]]] = {
    "major_revision": [
        (r"\bfinal\s+(?:rule|standard|publication|release)\b", 4.0),
        (r"\brev(?:ision)?\s*[56789]\b", 4.0),
        (r"\bnew\s+edition\b", 3.5),
        (r"\bversion\s*\d+\.\d+\b", 2.5),
        (r"\bv\d+\.\d+\s+(?:final|release|published)\b", 3.0),
        (r"\bfinal\b", 2.0),
        (r"\brelease[sd]?\b", 1.0),
    ],
    "minor_update": [
        (r"\berrata\b", 5.0),
        (r"\bcorrection\b", 4.0),
        (r"\bpatch\b", 4.0),
        (r"\bclarification\b", 3.5),
        (r"\bpoint\s+release\b", 4.0),
        (r"\bupdate\b", 1.5),
        (r"\bminor\b", 2.0),
    ],
    "draft_release": [
        (r"\binitial\s+public\s+draft\b", 6.0),
        (r"\b[Ii]PD\b", 5.0),
        (r"\bpre-release\b", 4.5),
        (r"\brelease\s+candidate\b", 4.5),
        (r"\b[Rr][Cc]\d*\b", 4.0),
        (r"\bdraft\b", 3.0),
        (r"\bpreview\b", 2.0),
    ],
    "public_comment": [
        (r"\bpublic\s+comment\s+period\b", 6.0),
        (r"\bcomment\s+period\b", 5.0),
        (r"\bpublic\s+comment\b", 4.5),
        (r"\bstakeholder\s+(?:input|feedback|consultation)\b", 4.0),
        (r"\bopen\s+for\s+(?:review|comment)\b", 4.0),
        (r"\bfeedback\b", 1.5),
        (r"\bconsultation\b", 3.0),
    ],
    "new_framework": [
        (r"\bnew\s+standard\b", 5.0),
        (r"\bfirst\s+edition\b", 5.0),
        (r"\binaugural\b", 4.0),
        (r"\bintroduce[sd]?\b", 2.5),
        (r"\blaunch(?:es|ed|ing)?\b", 2.0),
        (r"\bpublish(?:es|ed)?\s+new\b", 3.0),
    ],
    "retired": [
        (r"\bwithdrawn\b", 6.0),
        (r"\bsuperseded\b", 6.0),
        (r"\bobsolet(?:e|ed)\b", 6.0),
        (r"\bretired\b", 5.0),
        (r"\breplaced\s+by\b", 5.0),
        (r"\bno\s+longer\s+(?:valid|active)\b", 4.0),
    ],
}

_MAX_POSSIBLE = {ct: sum(w for _, w in rules) for ct, rules in CHANGE_TYPE_RULES.items()}

ATOM_NS = "http://www.w3.org/2005/Atom"


def entry_fingerprint(url: str, title: str) -> str:
    """SHA1 of url+NUL+title, first 16 hex chars. Stable across runs."""
    raw = f"{url.strip()}\x00{title.strip()}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def classify_change_type(title: str, summary: str = "") -> tuple[str, list[str]]:
    """
    Score each change_type by matching regex rules against title+summary.
    Returns (best_type, keywords_matched). Falls back to 'informational'.
    """
    text = (title + " " + summary).lower()
    best_type = "informational"
    best_score = 0.0
    all_keywords: list[str] = []

    for ctype, rules in CHANGE_TYPE_RULES.items():
        score = 0.0
        for pattern, weight in rules:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                score += weight
                kw = m.group(0).strip()
                if kw not in all_keywords:
                    all_keywords.append(kw)
        normalized = score / _MAX_POSSIBLE[ctype] if _MAX_POSSIBLE[ctype] > 0 else 0.0
        if normalized > best_score:
            best_score = normalized
            best_type = ctype

    return (best_type if best_score >= 0.15 else "informational"), all_keywords


def _parse_date(text: Optional[str]) -> Optional[str]:
    """Parse RFC2822 or ISO8601 date string → UTC ISO8601 Z string, or None."""
    if not text:
        return None
    text = text.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text[:len(fmt)], fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    try:
        # handles RFC2822 "Tue, 15 Nov 1994 08:12:31 GMT"
        dt = parsedate_to_datetime(text)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    return None


def _el_text(el: Optional[ET.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _find_first(parent: ET.Element, *tags: str) -> Optional[ET.Element]:
    for tag in tags:
        el = parent.find(tag)
        if el is not None:
            return el
    return None


def _is_after(published_at: Optional[str], since: datetime) -> bool:
    if not published_at:
        return True  # include if date unknown
    try:
        dt = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt >= since
    except Exception:
        return True


def _fetch_xml(url: str) -> Optional[bytes]:
    try:
        req = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
            },
        )
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except HTTPError as e:
        print(f"  [WARN] HTTP {e.code} {url}", file=sys.stderr)
    except URLError as e:
        print(f"  [WARN] URLError {url}: {e.reason}", file=sys.stderr)
    except Exception as e:
        print(f"  [WARN] Error {url}: {e}", file=sys.stderr)
    return None


def _parse_atom(root: ET.Element, since: datetime) -> list[dict]:
    entries = []
    for item in root.findall(f"{{{ATOM_NS}}}entry") or root.findall("entry"):
        title = _el_text(item.find(f"{{{ATOM_NS}}}title") or item.find("title"))
        link_el = item.find(f"{{{ATOM_NS}}}link") or item.find("link")
        link = (link_el.get("href", "") if link_el is not None else "") or _el_text(link_el)
        pub_el = _find_first(
            item,
            f"{{{ATOM_NS}}}published",
            f"{{{ATOM_NS}}}updated",
            "published",
            "updated",
        )
        pub_at = _parse_date(_el_text(pub_el))
        summary_el = _find_first(
            item,
            f"{{{ATOM_NS}}}summary",
            f"{{{ATOM_NS}}}content",
            "summary",
            "content",
        )
        summary = _el_text(summary_el)[:600]
        if title and link and _is_after(pub_at, since):
            entries.append({"title": title, "url": link, "published_at": pub_at, "summary": summary})
    return entries


def _parse_rss(root: ET.Element, since: datetime) -> list[dict]:
    entries = []
    channel = root.find("channel") or root
    for item in channel.findall("item"):
        title = _el_text(item.find("title"))
        link = _el_text(item.find("link"))
        pub_el = item.find("pubDate") or item.find("{http://purl.org/dc/elements/1.1/}date")
        pub_at = _parse_date(_el_text(pub_el))
        desc = _el_text(item.find("description"))[:600]
        if title and link and _is_after(pub_at, since):
            entries.append({"title": title, "url": link, "published_at": pub_at, "summary": desc})
    return entries


def fetch_announcements(feed_cfg: dict, window_days: int) -> list[dict]:
    """Fetch one RSS/Atom feed URL; return raw entry dicts within the window."""
    url = feed_cfg["url"]
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    raw = _fetch_xml(url)
    if raw is None:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  [WARN] XML parse error {url}: {e}", file=sys.stderr)
        return []

    # Detect Atom vs RSS by root tag
    tag = root.tag.lower()
    if "atom" in tag or root.tag in (f"{{{ATOM_NS}}}feed", "feed"):
        return _parse_atom(root, since)
    elif "rss" in tag or "channel" in tag or root.find("channel") is not None:
        return _parse_rss(root, since)
    else:
        # Try Atom first, then RSS
        atom_entries = _parse_atom(root, since)
        return atom_entries if atom_entries else _parse_rss(root, since)


def _keywords_in_text(keywords: list[str], text: str) -> bool:
    """Return True if any keyword (case-insensitive) appears in text."""
    tl = text.lower()
    return any(k.lower() in tl for k in keywords)


def process_feed_entry(framework_id: str, feed_cfg: dict, window_days: int, dry_run: bool) -> list[dict]:
    """Fetch one announcement feed config; produce classified entry dicts."""
    url = feed_cfg["url"]
    feed_type = feed_cfg.get("type", "rss").upper()
    filter_keywords: list[str] = feed_cfg.get("filter_keywords", [])

    print(f"    {feed_type} {url}")
    raw_entries = fetch_announcements(feed_cfg, window_days)
    print(f"      → {len(raw_entries)} raw entries in window")

    result: list[dict] = []
    for raw in raw_entries:
        # Apply keyword filter if configured
        text = raw["title"] + " " + raw["summary"]
        if filter_keywords and not _keywords_in_text(filter_keywords, text):
            continue

        change_type, keywords_matched = classify_change_type(raw["title"], raw["summary"])
        eid = entry_fingerprint(raw["url"], raw["title"])

        entry: dict = {
            "entry_id": eid,
            "framework_ids": [framework_id],
            "title": raw["title"],
            "published_at": raw["published_at"],
            "url": raw["url"],
            "source_feed": url,
            "change_type": change_type,
            "keywords_matched": keywords_matched,
            "human_reviewed": False,
            "action_items": [],
        }
        result.append(entry)

        if dry_run:
            pub = raw["published_at"] or "unknown date"
            print(f"      [{change_type:20s}] {pub:25s} {raw['title'][:65]}")

    return result


def deduplicate(new_entries: list[dict], existing_entries: list[dict]) -> list[dict]:
    """Return entries from new_entries whose entry_id is not in existing_entries."""
    seen = {e["entry_id"] for e in existing_entries}
    return [e for e in new_entries if e["entry_id"] not in seen]


def merge_with_existing(new_entries: list[dict], output_path: Path) -> tuple[list[dict], int]:
    """
    Load existing announcements_feed.json, preserve human_reviewed=True entries as-is,
    append deduplicated new entries, return (merged_list, added_count).
    """
    existing_entries: list[dict] = []
    if output_path.exists():
        try:
            doc = json.loads(output_path.read_text(encoding="utf-8"))
            existing_entries = doc.get("entries", [])
        except Exception as e:
            print(f"[WARN] Could not read existing {output_path}: {e}", file=sys.stderr)

    truly_new = deduplicate(new_entries, existing_entries)
    merged = existing_entries + truly_new
    return merged, len(truly_new)


def run(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    output_path = Path(args.output)

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Cannot read feed registry {registry_path}: {e}", file=sys.stderr)
        return 1

    feeds: dict = registry.get("feeds", {})
    target_ids = [args.feed] if args.feed else list(feeds.keys())

    if args.feed and args.feed not in feeds:
        print(f"[ERROR] Unknown feed id: {args.feed!r}. Available: {', '.join(feeds)}", file=sys.stderr)
        return 1

    all_new: list[dict] = []
    skipped = 0

    for fw_id in target_ids:
        entry = feeds[fw_id]
        af_list: list[dict] = entry.get("announcement_feeds", [])
        if not af_list:
            skipped += 1
            continue
        print(f"\n[{fw_id}] {entry.get('label', fw_id)}")
        for af in af_list:
            results = process_feed_entry(fw_id, af, args.days, args.dry_run)
            all_new.extend(results)

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Found {len(all_new)} matching entries across feeds ({skipped} feeds skipped — no announcement_feeds configured)")

    if args.dry_run:
        print("[DRY-RUN] No files written.")
        return 0

    merged, added = merge_with_existing(all_new, output_path)
    doc = {
        "schema_version": "1.0.0",
        "_purpose": "Structured announcements from standards-body RSS/Atom feeds. Populated by announcement_monitor.py.",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": args.days,
        "entries": sorted(merged, key=lambda e: e.get("published_at") or "", reverse=True),
    }
    output_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(merged)} total entries ({added} new) → {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitor standards-body RSS/Atom feeds for framework update announcements.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and classify entries but do not write to disk",
    )
    parser.add_argument(
        "--feed",
        metavar="FEED_ID",
        help="Process only this feed ID from feed_registry.json (default: all feeds)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=WINDOW_DAYS_DEFAULT,
        metavar="N",
        help=f"Look-back window in days (default: {WINDOW_DAYS_DEFAULT})",
    )
    parser.add_argument(
        "--registry",
        default=str(REGISTRY_PATH),
        metavar="PATH",
        help="Path to feed_registry.json",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        metavar="PATH",
        help="Path to announcements_feed.json output",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
