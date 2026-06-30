#!/usr/bin/env python3
"""
EUR-Lex EU Regulation Loader

Fetches the full text of key EU digital-governance regulations via EUR-Lex ELI
(European Legislation Identifier) URIs, parses their articles, and maps each
article to relevant NIST SP 800-53 Rev. 5 control families using a keyword
heuristic.

Supported regulations:
  GDPR        — General Data Protection Regulation        (32016R0679)
  NIS2        — Network and Information Security 2        (32022L2555)
  DORA        — Digital Operational Resilience Act        (32022R2554)
  EU AI Act   — EU Artificial Intelligence Act            (32024R1689)

ELI URI pattern:
  https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{CELEX_ID}

Output: canonical-sources/eurlex/{reg_id}-articles.json  (one file per regulation)

Usage:
  python3 eurlex_loader.py                                  # all regulations
  python3 eurlex_loader.py --regulation gdpr nis2           # subset
  python3 eurlex_loader.py --regulation gdpr --dry-run      # parse, no file write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_CANONICAL_DIR = _REPO_ROOT / "canonical-sources"
_EURLEX_DIR    = _CANONICAL_DIR / "eurlex"

# Polite delay between regulation fetches (seconds)
_REQUEST_DELAY = 3.0

# ── regulation registry ────────────────────────────────────────────────────────

REGULATIONS: Dict[str, Dict[str, str]] = {
    "gdpr": {
        "celex_id": "32016R0679",
        "full_name": "General Data Protection Regulation (EU) 2016/679",
    },
    "nis2": {
        "celex_id": "32022L2555",
        "full_name": "NIS2 Directive (EU) 2022/2555",
    },
    "dora": {
        "celex_id": "32022R2554",
        "full_name": "Digital Operational Resilience Act (EU) 2022/2554",
    },
    "eu-ai-act": {
        "celex_id": "32024R1689",
        "full_name": "EU Artificial Intelligence Act (EU) 2024/1689",
    },
}

ELI_BASE = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex_id}"

# ── NIST family keyword heuristic ────────────────────────────────────────────

# Each tuple: (list_of_keyword_substrings_lower, nist_family_codes)
# Checked in order; all matching families are collected (not first-match only).
_NIST_KEYWORD_MAP: List[Tuple[List[str], str]] = [
    (["access control", "authoris", "authoriz", "access right", "access restriction",
      "right of access", "data subject access"],                                          "AC"),
    (["logging", "audit", "records", "log file", "audit trail", "audit log",
      "record keeping", "documentation of processing"],                                   "AU"),
    (["encryption", "pseudonymis", "pseudonymiz", "cryptograph", "cipher",
      "key management", "anonymis", "anonymiz"],                                          "SC"),
    (["incident", "breach notification", "personal data breach", "reporting obligation",
      "notify", "notification", "major incident"],                                        "IR"),
    (["risk assessment", "risk management", "data protection impact", "dpia",
      "risk analysis", "risk evaluation", "threat assessment"],                           "RA"),
    (["authentication", "identity", "identification", "digital identity",
      "credential", "multi-factor"],                                                      "IA"),
    (["integrity", "accuracy", "correctness", "data quality", "minimis",
      "minimiz", "completeness"],                                                          "SI"),
    (["processor", "controller", "data processor", "data controller",
      "supply chain", "third party", "subprocessor", "vendor", "provider"],               "SA"),
    (["continuity", "availability", "backup", "resilience", "recovery",
      "business continuity", "disaster recovery", "redundanc"],                           "CP"),
    (["configuration", "patch", "update", "vulnerability", "hardening",
      "software update", "security update"],                                               "CM"),
    (["monitoring", "surveillance", "detection", "intrusion", "anomaly",
      "security operation", "siem"],                                                       "SI"),
    (["training", "awareness", "personnel", "staff", "human", "education",
      "competence"],                                                                       "AT"),
    (["physical", "premises", "facility", "hardware", "device", "equipment"],             "PE"),
    (["consent", "lawful basis", "legitimate interest", "purpose limitation",
      "data minimisation", "data minimization"],                                           "AC"),
]


def _map_article_to_nist(text: str) -> List[str]:
    """
    Return a deduplicated list of NIST 800-53 family codes for the article text.
    Uses the keyword heuristic above.
    """
    needle = text.lower()
    families: List[str] = []
    seen: set = set()
    for keywords, family in _NIST_KEYWORD_MAP:
        if family in seen:
            continue
        if any(kw in needle for kw in keywords):
            families.append(family)
            seen.add(family)
    return families if families else ["SI"]   # default: System and Information Integrity


# ── HTML stripping ─────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Minimal HTML → plain-text converter (no external dependencies)."""

    _SKIP_TAGS = {"script", "style", "head", "meta", "link"}
    _BLOCK_TAGS = {
        "p", "div", "br", "li", "tr", "td", "th", "h1", "h2", "h3",
        "h4", "h5", "h6", "article", "section", "table", "tbody",
    }

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        tl = tag.lower()
        if tl in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tl in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tl = tag.lower()
        if tl in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _html_to_text(html: str) -> str:
    """Strip HTML tags and return clean plain text."""
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass
    text = extractor.get_text()
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ── article parsing ───────────────────────────────────────────────────────────

# Patterns to detect Article headers in EUR-Lex HTML text.
# EUR-Lex structures vary slightly by regulation but articles are always
# labelled "Article N" (English text).
_ART_HEADER_RE = re.compile(
    r"Article\s+(\d+[a-z]?)\s*[\n\r]+\s*([^\n\r]{3,120})",
    re.IGNORECASE,
)
_ART_SIMPLE_RE = re.compile(
    r"Article\s+(\d+[a-z]?)\b",
    re.IGNORECASE,
)


def _parse_articles(text: str, reg_id: str) -> List[Dict[str, Any]]:
    """
    Parse article blocks from plain text extracted from EUR-Lex HTML.

    Splits on Article N headers and extracts:
      article_number, article_title, text_snippet, keywords
    """
    # Find all Article positions
    matches = list(_ART_HEADER_RE.finditer(text))

    # If header pattern found too few, fall back to simple pattern
    if len(matches) < 3:
        matches = list(_ART_SIMPLE_RE.finditer(text))

    articles: List[Dict[str, Any]] = []
    seen_numbers: set = set()

    for i, m in enumerate(matches):
        art_num = m.group(1)
        if art_num in seen_numbers:
            continue
        seen_numbers.add(art_num)

        # Article title: the text after the article number on the same or next line
        if m.lastindex and m.lastindex >= 2:
            try:
                art_title = m.group(2).strip().rstrip(".")
            except IndexError:
                art_title = ""
        else:
            art_title = ""

        # Article body: text from this match to the next Article header
        start = m.end()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body  = text[start:end].strip()

        # Snippet: first 500 chars
        snippet = body[:500]
        if len(body) > 500:
            snippet += "…"

        # Keywords: notable noun phrases (simple extraction)
        keywords = _extract_keywords(art_title + " " + body[:300])

        articles.append(
            {
                "regulation_id":  reg_id,
                "article_number": art_num,
                "article_title":  art_title,
                "text_snippet":   snippet.strip(),
                "keywords":       keywords,
            }
        )

    return articles


_KEYWORD_STOPWORDS = {
    "the", "a", "an", "of", "in", "to", "and", "or", "for", "with",
    "shall", "may", "must", "be", "by", "at", "from", "is", "are",
    "that", "this", "it", "on", "as", "its", "any", "all", "such",
    "where", "which", "each", "other", "their", "not", "have", "has",
    "been", "who", "under", "within", "including", "member", "state",
    "states", "union", "european", "regulation", "directive",
}


def _extract_keywords(text: str, max_kw: int = 10) -> List[str]:
    """
    Extract notable keywords from article text.
    Simple frequency-based extraction; stops at stopwords.
    """
    words = re.findall(r"[a-zA-Z]{4,}", text.lower())
    freq: Dict[str, int] = {}
    for w in words:
        if w not in _KEYWORD_STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq, key=lambda w: freq[w], reverse=True)
    return sorted_words[:max_kw]


# ── network ───────────────────────────────────────────────────────────────────

def _build_proxy_opener() -> urllib.request.OpenerDirector:
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    handlers: List[urllib.request.BaseHandler] = []
    if proxy_url:
        handlers.append(urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url}))
    return urllib.request.build_opener(*handlers)


def _fetch_url(url: str, max_retries: int = 3, initial_delay: float = 3.0, timeout: int = 60) -> str:
    """Fetch URL, return decoded text (UTF-8). Retries with back-off."""
    opener = _build_proxy_opener()
    delay  = initial_delay
    last_exc: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "dbz-grc-eurlex-loader/1.0 (GRC cross-mapping backend)",
                    "Accept-Language": "en-GB,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                # Try to detect encoding from Content-Type
                ct = resp.headers.get("Content-Type", "")
                enc_match = re.search(r"charset=([^\s;]+)", ct, re.IGNORECASE)
                enc = enc_match.group(1) if enc_match else "utf-8"
                try:
                    return raw.decode(enc, errors="replace")
                except LookupError:
                    return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            print(f"  [warn] HTTP {exc.code} on attempt {attempt}/{max_retries}: {url}", file=sys.stderr)
            last_exc = exc
            if exc.code in (429, 503):
                time.sleep(delay)
                delay *= 2
            else:
                raise
        except Exception as exc:
            print(f"  [warn] Network error attempt {attempt}/{max_retries}: {exc}", file=sys.stderr)
            last_exc = exc
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts") from last_exc


# ── main class ────────────────────────────────────────────────────────────────

class EURLexLoader:
    """
    Fetches EU regulations from EUR-Lex and extracts structured article data
    with NIST 800-53 family mappings.
    """

    def fetch_regulation(self, reg_id: str) -> str:
        """
        Fetch raw HTML for a regulation identified by reg_id (e.g. 'gdpr').

        Returns the HTML as a string. Raises ValueError for unknown reg_id,
        RuntimeError on network failure.
        """
        if reg_id not in REGULATIONS:
            raise ValueError(
                f"Unknown regulation '{reg_id}'. Known: {list(REGULATIONS.keys())}"
            )
        celex_id = REGULATIONS[reg_id]["celex_id"]
        url = ELI_BASE.format(celex_id=celex_id)
        print(f"  Fetching {reg_id.upper()} ({celex_id}) from EUR-Lex…")
        return _fetch_url(url)

    def parse_articles(self, html: str, reg_id: str) -> List[Dict[str, Any]]:
        """
        Parse articles from EUR-Lex HTML for reg_id.

        Returns list of article dicts (without nist_families yet).
        """
        text = _html_to_text(html)
        articles = _parse_articles(text, reg_id)
        print(f"  Parsed {len(articles)} articles from {reg_id.upper()}")
        return articles

    def map_articles_to_nist(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Add 'nist_families' field to each article dict.

        Modifies articles in place and returns them.
        """
        for art in articles:
            combined = " ".join([
                art.get("article_title", ""),
                art.get("text_snippet", ""),
                " ".join(art.get("keywords", [])),
            ])
            art["nist_families"] = _map_article_to_nist(combined)
        return articles

    def run(self, reg_ids: List[str], dry_run: bool = False) -> Dict[str, Any]:
        """
        Full pipeline for the given list of regulation IDs.

        Returns dict of {reg_id: result} for all successfully processed regulations.
        """
        print("=== EUR-Lex Regulation Loader ===")
        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}

        for idx, reg_id in enumerate(reg_ids):
            if idx > 0:
                print(f"  (waiting {_REQUEST_DELAY}s between requests…)")
                time.sleep(_REQUEST_DELAY)

            reg_info = REGULATIONS.get(reg_id)
            if not reg_info:
                print(f"  [skip] Unknown regulation ID: {reg_id}", file=sys.stderr)
                errors[reg_id] = f"Unknown regulation ID: {reg_id}"
                continue

            try:
                html     = self.fetch_regulation(reg_id)
                articles = self.parse_articles(html, reg_id)
                articles = self.map_articles_to_nist(articles)

                celex_id = reg_info["celex_id"]
                fetched_at = datetime.now(timezone.utc).isoformat()
                result: Dict[str, Any] = {
                    "_celex_id":          celex_id,
                    "_eli_version":       f"{celex_id[:5]}/{celex_id[5:]}",
                    "_consolidated_date": fetched_at[:10],
                    "metadata": {
                        "regulation_id":     reg_id,
                        "celex_id":          celex_id,
                        "full_name":         reg_info["full_name"],
                        "eli_uri":           ELI_BASE.format(celex_id=celex_id),
                        "generated_at":      fetched_at,
                        "total_articles":    len(articles),
                        "human_review_required": True,
                    },
                    "articles": articles,
                }
                results[reg_id] = result

                if not dry_run:
                    _EURLEX_DIR.mkdir(parents=True, exist_ok=True)
                    out_path = _EURLEX_DIR / f"{reg_id}-articles.json"
                    out_path.write_text(
                        json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(f"  Saved → {out_path}")
                else:
                    print(f"  [dry-run] Skipping file write for {reg_id}")

            except Exception as exc:
                msg = f"Failed to load {reg_id}: {exc}"
                print(f"  [error] {msg}", file=sys.stderr)
                errors[reg_id] = msg

        # Summary
        print(f"\n  Done: {len(results)} regulation(s) processed, {len(errors)} error(s)")
        if errors:
            for reg_id, err in errors.items():
                print(f"    {reg_id}: {err}", file=sys.stderr)

        return results


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch EU regulations from EUR-Lex and map articles to NIST 800-53 families."
    )
    p.add_argument(
        "--regulation",
        nargs="+",
        choices=list(REGULATIONS.keys()),
        default=list(REGULATIONS.keys()),
        metavar="REG_ID",
        help="Regulation(s) to process (default: all). Choices: %(choices)s",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse without writing output files",
    )
    p.add_argument(
        "--format",
        choices=["json", "summary"],
        default="summary",
        help="Output format for stdout (default: summary)",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()
    loader  = EURLexLoader()
    results = loader.run(reg_ids=args.regulation, dry_run=args.dry_run)

    if args.format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for reg_id, data in results.items():
            meta = data["metadata"]
            print(
                f"  {reg_id.upper()}: {meta['total_articles']} articles extracted "
                f"({meta['full_name']})"
            )


if __name__ == "__main__":
    main()
