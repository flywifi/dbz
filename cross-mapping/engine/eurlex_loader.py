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

Source (phase 52): the Publications Office Cellar, the documented machine reuse channel —
  https://publications.europa.eu/resource/celex/{CELEX_ID}  (Accept: application/xhtml+xml)
Superseded: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{CELEX_ID} answers automated
  clients with HTTP 202 and an AWS WAF JavaScript challenge (2026-11-05); the loader refused it as data.

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

import fetchkit  # governed fetch: host_policies.json caps, pacing, breaker, ledger (phase 51)

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_CANONICAL_DIR = _REPO_ROOT / "canonical-sources"
_EURLEX_DIR    = _CANONICAL_DIR / "eurlex"

# Polite delay between regulation fetches (seconds)

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

CELLAR_BASE = "https://publications.europa.eu/resource/celex/{celex_id}"
SUPERSEDED_SOURCE = ("https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex_id} answers automated clients "
                     "with HTTP 202 and an AWS WAF JavaScript challenge (2026-11-05); EUR-Lex documents the Cellar RESTful "
                     "API as its machine reuse channel")
MIN_ARTICLES = {"gdpr": 99, "nis2": 46, "dora": 64, "eu-ai-act": 113}


class FetchRejected(RuntimeError):
    """The response is not the act; nothing is written."""

# ── NIST family keyword heuristic ────────────────────────────────────────────



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

def _fetch_cellar(celex_id: str, timeout: int = 90) -> str:
    r = fetchkit.fetch(CELLAR_BASE.format(celex_id=celex_id),
                       headers={"User-Agent": "dbz-grc-eurlex-loader/1.0 (GRC cross-mapping backend)",
                                "Accept": "application/xhtml+xml", "Accept-Language": "eng"},
                       timeout=timeout, retries=3, retry_on=(429, 503), backoff=3.0)
    text = r.body.decode("utf-8", errors="replace")
    if r.status != 200:
        raise FetchRejected(f"{celex_id}: HTTP {r.status}, expected 200")
    if "awswaf" in text or "challenge.js" in text:
        raise FetchRejected(f"{celex_id}: a bot-challenge page, not the act")
    if "application/xhtml+xml" not in r.headers.get("content-type", ""):
        raise FetchRejected(f"{celex_id}: content-type {r.headers.get('content-type')!r}, expected application/xhtml+xml")
    return text


# ── main class ────────────────────────────────────────────────────────────────

class EURLexLoader:
    """
    Fetches EU regulations from EUR-Lex and extracts structured article data
    with NIST 800-53 family mappings.
    """

    def fetch_regulation(self, reg_id: str) -> str:
        if reg_id not in REGULATIONS:
            raise ValueError(f"Unknown regulation '{reg_id}'. Known: {list(REGULATIONS.keys())}")
        celex_id = REGULATIONS[reg_id]["celex_id"]
        print(f"  Fetching {reg_id.upper()} ({celex_id}) from the Publications Office Cellar…")
        return _fetch_cellar(celex_id)

    def parse_articles(self, html: str, reg_id: str) -> List[Dict[str, Any]]:
        """
        Parse articles from EUR-Lex HTML for reg_id.

        Returns list of article dicts (without nist_families yet).
        """
        text = _html_to_text(html)
        articles = _parse_articles(text, reg_id)
        print(f"  Parsed {len(articles)} articles from {reg_id.upper()}")
        return articles

    def map_articles_to_nist(self, articles):
        for art in articles:
            art["nist_families"] = []   # no issuer mapping; the keyword table (default 'SI') was a guess
        return articles

    def run(self, reg_ids, dry_run: bool = False):
        print("=== EUR-Lex Regulation Loader (Cellar) ===")
        results, errors = {}, {}
        for reg_id in reg_ids:
            reg_info = REGULATIONS.get(reg_id)
            if not reg_info:
                errors[reg_id] = f"Unknown regulation ID: {reg_id}"
                continue
            try:
                articles = self.map_articles_to_nist(self.parse_articles(self.fetch_regulation(reg_id), reg_id))
                if len(articles) < MIN_ARTICLES.get(reg_id, 1):
                    raise FetchRejected(f"{reg_id}: {len(articles)} articles < floor {MIN_ARTICLES.get(reg_id, 1)}")
                celex_id = reg_info["celex_id"]
                result = {"_celex_id": celex_id,
                          "metadata": {"regulation_id": reg_id, "celex_id": celex_id, "full_name": reg_info["full_name"],
                                       "cellar_uri": CELLAR_BASE.format(celex_id=celex_id),
                                       "superseded_source": SUPERSEDED_SOURCE.format(celex_id=celex_id),
                                       "generated_at": datetime.now(timezone.utc).isoformat(),
                                       "total_articles": len(articles), "human_review_required": True},
                          "articles": articles}
                results[reg_id] = result
                if not dry_run:
                    _EURLEX_DIR.mkdir(parents=True, exist_ok=True)
                    (_EURLEX_DIR / f"{reg_id}-articles.json").write_text(
                        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            except Exception as exc:  # noqa: BLE001 — fail closed: nothing is written for this regulation
                errors[reg_id] = f"{type(exc).__name__}: {exc}"
                print(f"  [error] {reg_id}: {errors[reg_id]}", file=sys.stderr)
        print(f"\n  Done: {len(results)} regulation(s) processed, {len(errors)} error(s)")
        self.errors = errors
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
    fetchkit.run_cli(main, "eurlex_loader")
