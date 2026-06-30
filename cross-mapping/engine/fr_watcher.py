#!/usr/bin/env python3
"""
fr_watcher.py
Federal Register API watcher for cybersecurity and privacy regulatory activity.

Monitors proposed rules, final rules, and notices published in the Federal Register
that mention cybersecurity or privacy topics relevant to GRC cross-mapping.  Fetches
entries via the Federal Register JSON API, classifies each document into the same
change_type vocabulary used by announcement_monitor.py, and merges results into
canonical-sources/announcements_feed.json while preserving any existing entries
that carry human_reviewed=true.

Monitored agencies: HHS, FTC, SEC, CISA/DHS, DoD, FCC, FRB, OCC, FDIC, FinCEN
Filter terms: cybersecurity, data breach, incident reporting, privacy, HIPAA,
              zero trust, ransomware, CIRCIA, safeguards

Output: canonical-sources/announcements_feed.json  (merged, newest-first)

Usage:
    python3 fr_watcher.py --days 90 --dry-run --format summary
    python3 fr_watcher.py --days 30 --format json
    python3 fr_watcher.py --days 180 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
OUTPUT_PATH = _REPO_ROOT / "canonical-sources" / "announcements_feed.json"

# ---------------------------------------------------------------------------
# Federal Register API
# ---------------------------------------------------------------------------
FR_API_BASE = "https://www.federalregister.gov/api/v1/documents.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_BASE = 2.0        # seconds; doubles each retry
POLITE_DELAY = 4.0        # seconds between paginated API calls
DEFAULT_DAYS = 90
PAGE_SIZE = 100           # FR API max per_page
USER_AGENT = (
    "dbz-fr-watcher/1.0 (GRC cross-mapping research; polite client)"
)

# ---------------------------------------------------------------------------
# Agency slugs recognised by the Federal Register API
# ---------------------------------------------------------------------------
# Each entry maps a human label → the FR API "agency_slug" values.
# Multiple slugs per agency handle renamed / split agency identifiers.
AGENCY_SLUGS: dict[str, list[str]] = {
    "HHS":    ["health-and-human-services-department"],
    "FTC":    ["federal-trade-commission"],
    "SEC":    ["securities-and-exchange-commission"],
    "CISA":   ["cybersecurity-and-infrastructure-security-agency"],
    "DHS":    ["homeland-security-department"],
    "DoD":    ["defense-department"],
    "FCC":    ["federal-communications-commission"],
    "FRB":    ["federal-reserve-system"],
    "OCC":    ["comptroller-of-the-currency-office"],
    "FDIC":   ["federal-deposit-insurance-corporation"],
    "FinCEN": ["financial-crimes-enforcement-network"],
}

# Flat list of all slugs for the API query
ALL_AGENCY_SLUGS: list[str] = [
    slug
    for slugs in AGENCY_SLUGS.values()
    for slug in slugs
]

# Reverse map: FR slug → human label (first match wins)
_SLUG_TO_LABEL: dict[str, str] = {}
for _label, _slugs in AGENCY_SLUGS.items():
    for _slug in _slugs:
        _SLUG_TO_LABEL.setdefault(_slug, _label)

# ---------------------------------------------------------------------------
# Filter terms (applied as OR across title + abstract)
# ---------------------------------------------------------------------------
FILTER_TERMS: list[str] = [
    "cybersecurity",
    "data breach",
    "incident reporting",
    "privacy",
    "HIPAA",
    "zero trust",
    "ransomware",
    "CIRCIA",
    "safeguards",
]

# ---------------------------------------------------------------------------
# Document types to monitor
# ---------------------------------------------------------------------------
MONITORED_DOC_TYPES: set[str] = {"RULE", "PRORULE", "NOTICE", "PROPOSED_RULE"}

# ---------------------------------------------------------------------------
# doc_type → change_type mapping
# ---------------------------------------------------------------------------
# "RULE" requires a title-text heuristic to distinguish major_revision vs minor_update.
_CORRECTION_PATTERN = re.compile(
    r"\b(correction|errata|correcting amendment)\b", re.IGNORECASE
)
_DRAFT_NOTICE_PATTERN = re.compile(
    r"\b(proposed|draft|advance notice|ANPR|request for comment)\b", re.IGNORECASE
)


def _classify_doc_type(doc_type: str, title: str) -> str:
    """
    Map Federal Register doc_type + title text → change_type vocab.

    change_type values (matching announcement_monitor.py):
        major_revision   — final rule (substantial regulatory change)
        minor_update     — final rule with correction/errata in title
        public_comment   — proposed rule or PRORULE
        informational    — notice (general)
        draft_release    — notice that mentions draft/proposed text
    """
    dt = doc_type.upper().strip()
    if dt == "RULE":
        if _CORRECTION_PATTERN.search(title):
            return "minor_update"
        return "major_revision"
    if dt in ("PRORULE", "PROPOSED_RULE"):
        return "public_comment"
    if dt == "NOTICE":
        if _DRAFT_NOTICE_PATTERN.search(title):
            return "draft_release"
        return "informational"
    # Fallback for any unexpected type
    return "informational"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch_with_retry(url: str) -> Optional[bytes]:
    """
    GET *url* with up to MAX_RETRIES retries and exponential backoff.
    Picks up HTTPS_PROXY automatically via urllib.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except HTTPError as exc:
            if exc.code in (429, 503):
                wait = BACKOFF_BASE ** attempt
                retry_after = exc.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = max(wait, float(retry_after))
                    except ValueError:
                        pass
                print(
                    f"  [WARN] HTTP {exc.code} — sleeping {wait:.1f}s "
                    f"(attempt {attempt}/{MAX_RETRIES})",
                    file=sys.stderr,
                )
                time.sleep(wait)
            elif exc.code == 404:
                print(f"  [WARN] HTTP 404: {url}", file=sys.stderr)
                return None
            else:
                print(f"  [WARN] HTTP {exc.code}: {url}", file=sys.stderr)
                if attempt == MAX_RETRIES:
                    return None
                time.sleep(BACKOFF_BASE ** attempt)
        except URLError as exc:
            print(f"  [WARN] URLError ({exc.reason}): {url}", file=sys.stderr)
            if attempt == MAX_RETRIES:
                return None
            time.sleep(BACKOFF_BASE ** attempt)
        except Exception as exc:
            print(f"  [WARN] Unexpected error fetching {url}: {exc}", file=sys.stderr)
            if attempt == MAX_RETRIES:
                return None
            time.sleep(BACKOFF_BASE ** attempt)
    return None


# ---------------------------------------------------------------------------
# Feed ID / fingerprint
# ---------------------------------------------------------------------------

def _make_feed_id(document_number: str, title: str) -> str:
    """
    Stable feed_id: SHA1 of document_number + NUL + title (first 16 hex chars).
    Matches the style used in announcement_monitor.py (entry_fingerprint).
    """
    raw = f"fr:{document_number.strip()}\x00{title.strip()}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Agency resolution
# ---------------------------------------------------------------------------

def _resolve_agency_label(agencies: list[dict]) -> str:
    """
    Given the FR API 'agencies' list for a document, return the best
    human-readable label from AGENCY_SLUGS or fall back to the raw name.
    """
    for agency in agencies:
        slug = agency.get("slug", "")
        if slug in _SLUG_TO_LABEL:
            return _SLUG_TO_LABEL[slug]
    # Fallback: use the first agency's short name
    if agencies:
        return agencies[0].get("short_name") or agencies[0].get("name", "Unknown")
    return "Unknown"


def _agency_slug_in_monitored(agencies: list[dict]) -> bool:
    """Return True if any agency slug in *agencies* is in our monitored set."""
    monitored_set = set(ALL_AGENCY_SLUGS)
    return any(a.get("slug", "") in monitored_set for a in agencies)


# ---------------------------------------------------------------------------
# Term matching
# ---------------------------------------------------------------------------

def _matches_filter_terms(title: str, abstract: str) -> bool:
    """Return True if any FILTER_TERMS appears (case-insensitive) in title or abstract."""
    combined = (title + " " + abstract).lower()
    return any(term.lower() in combined for term in FILTER_TERMS)


# ---------------------------------------------------------------------------
# Federal Register API fetch (paginated)
# ---------------------------------------------------------------------------

def _build_query_url(
    page: int,
    since_date: str,
    through_date: str,
) -> str:
    """
    Build the FR API query URL for one page of results.

    The FR API accepts multi-value params as conditions[agencies][]= repeated.
    We encode them manually because urlencode handles lists differently.
    """
    base_params: list[tuple[str, str]] = [
        ("per_page", str(PAGE_SIZE)),
        ("page", str(page)),
        ("order", "newest"),
        ("conditions[publication_date][gte]", since_date),
        ("conditions[publication_date][lte]", through_date),
    ]
    # Multi-value: doc types
    for dt in sorted(MONITORED_DOC_TYPES):
        base_params.append(("conditions[type][]", dt))
    # Multi-value: agencies
    for slug in ALL_AGENCY_SLUGS:
        base_params.append(("conditions[agencies][]", slug))

    # Fields to retrieve
    fields = [
        "document_number",
        "title",
        "publication_date",
        "type",
        "html_url",
        "agencies",
        "docket_ids",
        "abstract",
    ]
    for f in fields:
        base_params.append(("fields[]", f))

    return FR_API_BASE + "?" + urlencode(base_params)


def fetch_fr_documents(days: int) -> list[dict]:
    """
    Fetch all Federal Register documents matching our filters for the past *days*.
    Handles pagination automatically.  Returns list of raw API document dicts.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    since_date = since.strftime("%Y-%m-%d")
    through_date = now.strftime("%Y-%m-%d")

    print(
        f"  Querying Federal Register API: {since_date} → {through_date}",
        file=sys.stderr,
    )

    all_docs: list[dict] = []
    page = 1
    total_pages = None

    while True:
        url = _build_query_url(page, since_date, through_date)
        print(f"    Page {page}" + (f"/{total_pages}" if total_pages else "") + f": {url[:120]}…", file=sys.stderr)

        raw = _fetch_with_retry(url)
        if raw is None:
            print("  [WARN] Failed to fetch page; stopping pagination.", file=sys.stderr)
            break

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"  [WARN] JSON parse error on page {page}: {exc}", file=sys.stderr)
            break

        docs = data.get("results", [])
        all_docs.extend(docs)

        # Pagination metadata
        count = data.get("count", 0)
        if total_pages is None and count and PAGE_SIZE:
            total_pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)

        print(f"    → {len(docs)} docs on this page ({len(all_docs)} total so far)", file=sys.stderr)

        if len(docs) < PAGE_SIZE:
            break
        if total_pages and page >= total_pages:
            break

        page += 1
        # Polite delay between paginated calls
        time.sleep(POLITE_DELAY)

    return all_docs


# ---------------------------------------------------------------------------
# Document → entry conversion
# ---------------------------------------------------------------------------

def _parse_publication_date(date_str: str) -> str:
    """
    Parse FR API date string (YYYY-MM-DD) → UTC ISO8601 with time component.
    FR API returns dates only (no time), so we use midnight UTC.
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return date_str  # Return as-is if unparseable


def _extract_docket_number(doc: dict) -> str:
    """Return the first docket ID from the document, or empty string."""
    docket_ids = doc.get("docket_ids") or []
    if isinstance(docket_ids, list) and docket_ids:
        return str(docket_ids[0])
    return ""


def document_to_entry(doc: dict) -> Optional[dict]:
    """
    Convert a raw FR API document dict → a feed entry dict.

    Returns None if the document does not pass agency or term filters.
    Entry fields:
        feed_id, title, published_at, url, change_type, doc_type,
        agency, docket_number, human_reviewed
    """
    agencies: list[dict] = doc.get("agencies") or []
    title: str = doc.get("title", "").strip()
    abstract: str = doc.get("abstract", "") or ""
    doc_type: str = (doc.get("type", "") or "").upper().strip()
    document_number: str = doc.get("document_number", "") or ""
    html_url: str = doc.get("html_url", "") or ""
    pub_date: str = doc.get("publication_date", "") or ""

    # Agency filter: must include at least one monitored agency
    if not _agency_slug_in_monitored(agencies):
        return None

    # Doc type filter
    if doc_type not in MONITORED_DOC_TYPES:
        return None

    # Term filter: title or abstract must match at least one term
    if not _matches_filter_terms(title, abstract):
        return None

    feed_id = _make_feed_id(document_number, title)
    change_type = _classify_doc_type(doc_type, title)
    agency_label = _resolve_agency_label(agencies)
    docket_number = _extract_docket_number(doc)
    published_at = _parse_publication_date(pub_date) if pub_date else None

    return {
        "feed_id": feed_id,
        "title": title,
        "published_at": published_at,
        "url": html_url,
        "change_type": change_type,
        "doc_type": doc_type,
        "agency": agency_label,
        "docket_number": docket_number,
        "human_reviewed": False,
        "human_review_required": True,
    }


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def _load_existing(output_path: Path) -> list[dict]:
    """Load existing announcements_feed.json entries, or return []."""
    if not output_path.exists():
        return []
    try:
        doc = json.loads(output_path.read_text(encoding="utf-8"))
        return doc.get("entries", [])
    except Exception as exc:
        print(f"[WARN] Could not read existing {output_path}: {exc}", file=sys.stderr)
        return []


def _merge_entries(
    new_entries: list[dict],
    existing_entries: list[dict],
) -> tuple[list[dict], int]:
    """
    Merge *new_entries* into *existing_entries*.

    Rules:
    - Existing entries with human_reviewed=true are preserved as-is.
    - New entries whose feed_id already exists in existing_entries are skipped
      (deduplication), so existing human_reviewed flags are never overwritten.
    - New entries are appended and the combined list is sorted newest-first.

    Returns (merged_list, added_count).
    """
    existing_ids: set[str] = {e.get("feed_id", "") for e in existing_entries}
    truly_new = [e for e in new_entries if e.get("feed_id", "") not in existing_ids]
    merged = existing_entries + truly_new
    # Sort newest-first; entries without a date sort last
    merged.sort(key=lambda e: e.get("published_at") or "", reverse=True)
    return merged, len(truly_new)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_summary(entries: list[dict], days: int) -> None:
    print(f"\n  Federal Register documents (last {days} days) — {len(entries)} matched:")
    by_agency: dict[str, int] = {}
    by_change_type: dict[str, int] = {}
    for e in entries:
        by_agency[e["agency"]] = by_agency.get(e["agency"], 0) + 1
        by_change_type[e["change_type"]] = by_change_type.get(e["change_type"], 0) + 1

    print("\n  By change_type:")
    for ct, cnt in sorted(by_change_type.items(), key=lambda x: -x[1]):
        print(f"    {ct:<20s}: {cnt}")

    print("\n  By agency:")
    for agency, cnt in sorted(by_agency.items(), key=lambda x: -x[1]):
        print(f"    {agency:<12s}: {cnt}")

    print("\n  Entries (newest first):")
    for e in entries[:20]:
        pub = (e.get("published_at") or "")[:10]
        print(f"    [{e['change_type']:<16s}] [{e['agency']:<8s}] {pub}  {e['title'][:65]}")
    if len(entries) > 20:
        print(f"    … and {len(entries) - 20} more")


def _write_output(
    merged: list[dict],
    added: int,
    days: int,
    output_path: Path,
) -> None:
    doc = {
        "schema_version": "1.0.0",
        "_purpose": (
            "Structured announcements from Federal Register API and standards-body feeds. "
            "Populated by announcement_monitor.py and fr_watcher.py."
        ),
        "_usage": (
            "Entries with human_reviewed=false are automated signals; "
            "set to true after a human verifies on the primary source."
        ),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": days,
        "entries": merged,
    }
    output_path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {len(merged)} total entries ({added} new) → {output_path}")


# ---------------------------------------------------------------------------
# Main run logic
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    print(
        f"\n[fr_watcher] Fetching Federal Register documents — last {args.days} days",
        file=sys.stderr,
    )

    raw_docs = fetch_fr_documents(args.days)
    print(f"\n  Total raw documents fetched: {len(raw_docs)}", file=sys.stderr)

    # Convert and filter
    entries: list[dict] = []
    for doc in raw_docs:
        entry = document_to_entry(doc)
        if entry is not None:
            entries.append(entry)

    print(f"  After agency + term filter: {len(entries)} entries", file=sys.stderr)

    if not entries:
        print("\n  No matching documents found.")
        if args.dry_run:
            print("[DRY-RUN] No files written.")
        return 0

    if args.fmt == "summary" or args.dry_run:
        _print_summary(entries, args.days)

    if args.fmt == "json" and args.dry_run:
        print(json.dumps(entries, indent=2, ensure_ascii=False))

    if args.dry_run:
        print(f"\n[DRY-RUN] {len(entries)} entries found. No files written.")
        return 0

    # Merge with existing output
    existing = _load_existing(OUTPUT_PATH)
    merged, added = _merge_entries(entries, existing)
    _write_output(merged, added, args.days, OUTPUT_PATH)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Federal Register watcher: monitor cybersecurity/privacy regulatory activity."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 fr_watcher.py --days 90 --dry-run --format summary
  python3 fr_watcher.py --days 30 --format json
  python3 fr_watcher.py --days 180 --dry-run

Monitored agencies: HHS, FTC, SEC, CISA/DHS, DoD, FCC, FRB, OCC, FDIC, FinCEN
Filter terms: cybersecurity, data breach, incident reporting, privacy, HIPAA,
              zero trust, ransomware, CIRCIA, safeguards
Output: canonical-sources/announcements_feed.json (merged with existing entries)
""",
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS, metavar="N",
        help=f"Look-back window in days (default: {DEFAULT_DAYS})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print results to stdout; do not write to announcements_feed.json",
    )
    parser.add_argument(
        "--format", choices=["summary", "json"], default="summary", dest="fmt",
        help="Output format (default: summary)",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
