#!/usr/bin/env python3
"""
ecfr_loader.py
Loads CFR sections from the eCFR REST API and structures them for GRC catalog ingestion.

Fetches regulatory text from the Electronic Code of Federal Regulations (eCFR) versioner
API, extracts requirement-like sections, applies a keyword heuristic to map each section
to one or more NIST 800-53 control families, and writes per-part JSON artifacts to
canonical-sources/cfr/.

Supported CFR parts and their NIST family heuristic mappings:
  45 CFR 164 subpart C   (HIPAA Security)       → AU/AC/IA/SC/SI
  16 CFR 314             (GLBA Safeguards)       → AC/IA/SC/IR/CM
  21 CFR 11              (FDA electronic records) → AU/IA/SC
  21 CFR 820             (FDA Quality System)    → CM/SA/RA
  10 CFR 73.54           (NRC Nuclear Cyber)     → AC/AU/IR/SC
  42 CFR 2               (SAMHSA substance use)  → AC/AU
  47 CFR 64 subpart U    (FCC CPNI)              → AC/AU/SC
  17 CFR 229             (SEC cyber)             → IR/AC

Output: canonical-sources/cfr/{title}-cfr-{part}.json

Usage:
    python3 ecfr_loader.py --title 45 --part 164 --subpart C --dry-run
    python3 ecfr_loader.py --title 16 --part 314 --format json
    python3 ecfr_loader.py --title 21 --part 11 --dry-run --format summary
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
CFR_OUTPUT_DIR = _REPO_ROOT / "canonical-sources" / "cfr"

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
ECFR_FULL_URL = (
    "https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml"
)
ECFR_STRUCTURE_URL = (
    "https://www.ecfr.gov/api/versioner/v1/structure/{date}/title-{title}.json"
)
ECFR_VERSIONS_URL = (
    "https://www.ecfr.gov/api/versioner/v1/versions/title-{title}.json"
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_BASE = 2.0          # seconds; doubles each retry
POLITE_DELAY = 4.0          # seconds between distinct API calls
USER_AGENT = (
    "dbz-ecfr-loader/1.0 (GRC cross-mapping research; polite client)"
)

# ---------------------------------------------------------------------------
# NIST family keyword heuristics
# ---------------------------------------------------------------------------
# Each tuple: (keyword_regex_pattern, NIST_family_code)
# Patterns are tested case-insensitively against the full section text.
KEYWORD_FAMILY_MAP: list[tuple[str, str]] = [
    # IA — Identification and Authentication
    (r"\bauthentication\b", "IA"),
    (r"\bpassword\b", "IA"),
    (r"\bmulti.factor\b", "IA"),
    (r"\bidentity\b", "IA"),
    # AC — Access Control
    (r"\baccess control\b", "AC"),
    (r"\bauthorization\b", "AC"),
    (r"\bleast privilege\b", "AC"),
    (r"\brole\b", "AC"),
    # AU — Audit and Accountability
    (r"\baudit\b", "AU"),
    (r"\blog\b", "AU"),
    (r"\brecord\b", "AU"),
    (r"\bmonitor\b", "AU"),
    # SC — System and Communications Protection
    (r"\bencrypt\b", "SC"),
    (r"\bcryptograph\b", "SC"),
    (r"\btls\b", "SC"),
    (r"\bssl\b", "SC"),
    (r"\bcipher\b", "SC"),
    # IR — Incident Response
    (r"\bincident\b", "IR"),
    (r"\bbreach\b", "IR"),
    (r"\brespond\b", "IR"),
    (r"\bnotif(y|ication)\b", "IR"),
    # CM — Configuration Management
    (r"\bconfiguration\b", "CM"),
    (r"\bchange management\b", "CM"),
    (r"\bpatch\b", "CM"),
    (r"\bbaseline\b", "CM"),
    # RA — Risk Assessment
    (r"\brisk assessment\b", "RA"),
    (r"\brisk analysis\b", "RA"),
    (r"\bvulnerabilit(y|ies)\b", "RA"),
    # CP — Contingency Planning
    (r"\bcontinuity\b", "CP"),
    (r"\bbackup\b", "CP"),
    (r"\brecovery\b", "CP"),
    (r"\bdisaster\b", "CP"),
    # SI — System and Information Integrity
    (r"\bintegrity\b", "SI"),
    (r"\bmalicious code\b", "SI"),
    (r"\bantivirus\b", "SI"),
    # SA — System and Services Acquisition
    (r"\bacquisition\b", "SA"),
    (r"\bvendor\b", "SA"),
    (r"\bsupply chain\b", "SA"),
    (r"\bthird.party\b", "SA"),
]

# All recognised NIST family codes (used for ordering output)
ALL_NIST_FAMILIES: list[str] = ["AC", "AU", "CA", "CM", "CP", "IA", "IR", "MA",
                                 "MP", "PE", "PL", "PM", "PS", "PT", "RA", "SA",
                                 "SC", "SI", "SR"]

# ---------------------------------------------------------------------------
# Known CFR part metadata (used for validation / documentation)
# ---------------------------------------------------------------------------
KNOWN_CFR_PARTS: dict[tuple[int, int | str], dict] = {
    (45, 164): {
        "name": "HIPAA Security Rule",
        "subpart": "C",
        "expected_families": ["AU", "AC", "IA", "SC", "SI"],
    },
    (16, 314): {
        "name": "GLBA Safeguards Rule",
        "subpart": None,
        "expected_families": ["AC", "IA", "SC", "IR", "CM"],
    },
    (21, 11): {
        "name": "FDA Electronic Records",
        "subpart": None,
        "expected_families": ["AU", "IA", "SC"],
    },
    (21, 820): {
        "name": "FDA Quality System Regulation",
        "subpart": None,
        "expected_families": ["CM", "SA", "RA"],
    },
    (10, 73): {
        "name": "NRC Nuclear Cyber (73.54)",
        "subpart": None,
        "expected_families": ["AC", "AU", "IR", "SC"],
    },
    (42, 2): {
        "name": "SAMHSA Substance Use Confidentiality",
        "subpart": None,
        "expected_families": ["AC", "AU"],
    },
    (47, 64): {
        "name": "FCC CPNI",
        "subpart": "U",
        "expected_families": ["AC", "AU", "SC"],
    },
    (17, 229): {
        "name": "SEC Cyber Disclosure",
        "subpart": None,
        "expected_families": ["IR", "AC"],
    },
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _build_request(url: str, accept: str = "*/*") -> Request:
    """Build a Request with identifying headers. Proxy is picked up from env."""
    return Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )


def _fetch_with_retry(url: str, accept: str = "*/*") -> Optional[bytes]:
    """
    GET *url* with up to MAX_RETRIES attempts and exponential backoff.
    Honours HTTPS_PROXY via urllib (set automatically from env).
    Returns raw bytes on success, None on permanent failure.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = _build_request(url, accept)
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
                    f"  [WARN] HTTP {exc.code} on {url} — sleeping {wait:.1f}s "
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
# XML helpers for eCFR XML body
# ---------------------------------------------------------------------------

# eCFR uses a custom XML namespace in newer responses; we strip it for portability.
_ECFR_NS_PATTERN = re.compile(r'\s+xmlns(?::\w+)?="[^"]*"', re.IGNORECASE)


def _strip_ns(tag: str) -> str:
    """Return local name without namespace prefix."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _elem_text_recursive(elem: ET.Element, max_chars: int = 2000) -> str:
    """
    Collect all text content from *elem* and its descendants, collapsing
    whitespace. Truncated to max_chars to keep output manageable.
    """
    parts: list[str] = []
    for node in elem.iter():
        if node.text:
            parts.append(node.text.strip())
        if node.tail:
            parts.append(node.tail.strip())
    raw = " ".join(p for p in parts if p)
    raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) > max_chars:
        raw = raw[:max_chars] + " …"
    return raw


def _build_paragraph_hierarchy(elem: ET.Element) -> list[str]:
    """
    Walk immediate children whose tag looks like a paragraph designator
    (P, p, HD, SECTNO, SUBJECT) and return their text as hierarchy labels.
    """
    labels: list[str] = []
    for child in elem:
        tag = _strip_ns(child.tag).upper()
        if tag in ("SECTNO", "SUBJECT", "HD", "P", "FP"):
            text = (child.text or "").strip()
            if text:
                labels.append(text[:200])
    return labels[:10]  # cap at 10 levels


# ---------------------------------------------------------------------------
# Main loader class
# ---------------------------------------------------------------------------

class eCFRLoader:
    """
    Loads CFR sections from the eCFR REST API.

    All network calls respect the HTTPS_PROXY environment variable (urllib
    picks it up automatically). A polite POLITE_DELAY is inserted between
    distinct API calls to avoid hammering the government endpoint.
    """

    def __init__(self) -> None:
        self._last_request_time: float = 0.0
        self._date_cache: dict[int, str] = {}  # title → resolved date

    def _resolve_date(self, title: int) -> str:
        """Return the latest available eCFR version date for *title*.

        Falls back to a hardcoded recent date if the versions API fails, rather
        than using 'current' which eCFR does not support on the full-text endpoint.
        """
        if title in self._date_cache:
            return self._date_cache[title]
        url = ECFR_VERSIONS_URL.format(title=title)
        raw = self._get(url, accept="application/json")
        if raw:
            try:
                data = json.loads(raw)
                dates = sorted(set(
                    v["date"] for v in data.get("content_versions", [])
                    if v.get("date")
                ))
                if dates:
                    self._date_cache[title] = dates[-1]
                    return dates[-1]
            except (json.JSONDecodeError, KeyError):
                pass
        # Fallback: known-good date that covers all current CFR titles
        fallback = "2026-01-28"
        self._date_cache[title] = fallback
        return fallback

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _polite_sleep(self) -> None:
        """Sleep as needed to maintain POLITE_DELAY between API calls."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < POLITE_DELAY:
            time.sleep(POLITE_DELAY - elapsed)
        self._last_request_time = time.monotonic()

    def _get(self, url: str, accept: str = "*/*") -> Optional[bytes]:
        """Polite fetch with retry."""
        self._polite_sleep()
        return _fetch_with_retry(url, accept)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_structure(self, title: int) -> dict:
        """
        Fetch the eCFR part/section structure for *title*.

        Returns the parsed JSON dict from
            GET /api/versioner/v1/structure/{date}/title-{N}.json
        or an empty dict on failure.
        """
        date = self._resolve_date(title)
        url = ECFR_STRUCTURE_URL.format(date=date, title=title)
        print(f"  Fetching structure: {url}", file=sys.stderr)
        raw = self._get(url, accept="application/json")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"  [WARN] JSON parse error on structure {url}: {exc}", file=sys.stderr)
            return {}

    def fetch_part(
        self,
        title: int,
        part: int | str,
        subpart: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch the full XML for *title* / *part* (optionally *subpart*) and
        parse it into a list of section dicts.

        Each dict has keys:
            section_id          e.g. "164.308"
            title               section heading text
            text                full section text (truncated at 2000 chars)
            paragraph_hierarchy list of paragraph labels within the section

        Returns empty list on fetch or parse failure.
        """
        date = self._resolve_date(title)
        url = ECFR_FULL_URL.format(date=date, title=title)
        params = [f"part={part}"]
        if subpart:
            params.append(f"subpart={subpart}")
        url = url + "?" + "&".join(params)

        print(f"  Fetching part XML: {url}", file=sys.stderr)
        raw = self._get(url, accept="application/xml, text/xml")
        if not raw:
            return []

        # Strip namespace declarations so ElementTree can parse cleanly
        xml_text = raw.decode("utf-8", errors="replace")
        xml_text = _ECFR_NS_PATTERN.sub("", xml_text)

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            print(f"  [WARN] XML parse error: {exc}", file=sys.stderr)
            return []

        return self._extract_sections(root, title=title, part=part)

    def extract_requirements(self, sections: list[dict]) -> list[dict]:
        """
        Filter *sections* down to those that look like regulatory requirements
        and add a 'keywords' list (matched keyword phrases).

        A section is considered a requirement if it has non-trivial text
        (≥ 40 chars) and contains at least one imperative-style phrase.

        Returns list of dicts — same structure as fetch_part() output but
        with an added 'keywords' field.
        """
        requirements: list[dict] = []
        for sec in sections:
            text = sec.get("text", "")
            title = sec.get("title", "")
            combined = (title + " " + text).lower()

            if len(text) < 40:
                continue

            # Collect matched keyword phrases
            keywords: list[str] = []
            for pattern, _family in KEYWORD_FAMILY_MAP:
                m = re.search(pattern, combined, re.IGNORECASE)
                if m and m.group(0) not in keywords:
                    keywords.append(m.group(0).strip())

            # Include the section even with no keyword matches — it may be
            # useful for manual review.  Callers can filter on keywords if needed.
            req = dict(sec)
            req["keywords"] = keywords
            requirements.append(req)

        return requirements

    def map_to_nist_families(self, requirement: dict) -> list[str]:
        """
        Apply keyword heuristics to *requirement* and return the list of
        NIST 800-53 family codes (e.g. ["AC", "IA"]) that the text maps to.

        Never fabricates mappings — returns [] if nothing matches.
        """
        text = (
            requirement.get("title", "")
            + " "
            + requirement.get("text", "")
            + " "
            + " ".join(requirement.get("keywords", []))
        )
        families: set[str] = set()
        for pattern, family in KEYWORD_FAMILY_MAP:
            if re.search(pattern, text, re.IGNORECASE):
                families.add(family)
        # Return in canonical order
        return [f for f in ALL_NIST_FAMILIES if f in families]

    def load_cfr_part(
        self,
        title: int,
        part: int | str,
        subpart: Optional[str] = None,
        dry_run: bool = False,
    ) -> dict:
        """
        Full pipeline: fetch → extract requirements → map to NIST families.

        Returns a result dict with keys:
            title, part, subpart, fetched_at, section_count,
            requirement_count, sections, human_review_required
        On dry_run=True, prints a summary and returns without writing.
        Writes output to canonical-sources/cfr/{title}-cfr-{part}.json.
        """
        print(
            f"\n[eCFRLoader] title={title} part={part}"
            + (f" subpart={subpart}" if subpart else ""),
            file=sys.stderr,
        )

        sections = self.fetch_part(title, part, subpart)
        print(f"  → {len(sections)} sections fetched", file=sys.stderr)

        requirements = self.extract_requirements(sections)
        print(f"  → {len(requirements)} requirements extracted", file=sys.stderr)

        # Annotate each requirement with its NIST family mappings
        for req in requirements:
            req["nist_families"] = self.map_to_nist_families(req)

        # Build framework_id and cfr_part for build_db.py consumer
        part_str = str(part)
        framework_id = f"{title}-cfr-{part_str}"
        cfr_part = f"{title} CFR {part_str}"

        result: dict = {
            "schema_version": "1.0.0",
            "_source": "eCFR REST API v1",
            "_loader": "ecfr_loader.py",
            "_framework_id": framework_id,
            "_cfr_part": cfr_part,
            "_as_of_date": self._resolve_date(title),
            "human_review_required": True,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "title": title,
            "part": part_str,
            "subpart": subpart,
            "cfr_citation": _build_citation(title, part, subpart),
            "section_count": len(sections),
            "requirement_count": len(requirements),
            "sections": requirements,
            "requirements": requirements,  # alias used by build_db.py load_cfr_data()
        }

        if dry_run:
            _print_dry_run_summary(result)
            return result

        _write_output(result, title, part)
        return result

    # ------------------------------------------------------------------
    # Private XML helpers
    # ------------------------------------------------------------------

    def _extract_sections(
        self,
        root: ET.Element,
        title: int,
        part: int | str,
    ) -> list[dict]:
        """
        Walk the parsed XML tree looking for SECTION elements (or equivalent)
        and build a structured list.
        """
        sections: list[dict] = []

        # eCFR XML uses <SECTION> elements under <PART> → <SUBPART> (or directly)
        # Tags may also appear as <section>, etc.  We match case-insensitively.
        for elem in root.iter():
            local = _strip_ns(elem.tag).upper()
            if local != "SECTION":
                continue

            section_id = _extract_section_id(elem, title, part)
            heading = _extract_heading(elem)
            text = _elem_text_recursive(elem, max_chars=2000)
            para_hier = _build_paragraph_hierarchy(elem)

            sections.append(
                {
                    "section_id": section_id,
                    "title": heading,
                    "text": text,
                    "paragraph_hierarchy": para_hier,
                }
            )

        # Fallback: if no SECTION tags found, try DIV5 / DIV8 (eCFR v2 structure)
        if not sections:
            for elem in root.iter():
                local = _strip_ns(elem.tag).upper()
                if local not in ("DIV5", "DIV8"):
                    continue
                section_id = elem.get("N", "") or _extract_section_id(elem, title, part)
                heading = elem.get("HEAD", "") or _extract_heading(elem)
                text = _elem_text_recursive(elem, max_chars=2000)
                para_hier = _build_paragraph_hierarchy(elem)
                sections.append(
                    {
                        "section_id": section_id,
                        "title": heading,
                        "text": text,
                        "paragraph_hierarchy": para_hier,
                    }
                )

        return sections


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _build_citation(title: int, part: int | str, subpart: Optional[str]) -> str:
    base = f"{title} CFR {part}"
    if subpart:
        base += f" Subpart {subpart}"
    return base


def _extract_section_id(elem: ET.Element, title: int, part: int | str) -> str:
    """
    Try to extract the section identifier from SECTNO child element or
    the N attribute, falling back to a synthetic ID.
    """
    # Attribute first (eCFR div-style)
    n_attr = elem.get("N", "").strip()
    if n_attr:
        return n_attr

    for child in elem:
        local = _strip_ns(child.tag).upper()
        if local == "SECTNO":
            text = (child.text or "").strip()
            # Strip leading § and whitespace
            text = re.sub(r"^§\s*", "", text)
            if text:
                return text

    return f"{title}.{part}.unknown"


def _extract_heading(elem: ET.Element) -> str:
    """Extract section heading from SUBJECT or HD child element."""
    for child in elem:
        local = _strip_ns(child.tag).upper()
        if local in ("SUBJECT", "HD"):
            return (child.text or "").strip()
    return ""


def _print_dry_run_summary(result: dict) -> None:
    citation = result["cfr_citation"]
    print(f"\n[DRY-RUN] {citation}")
    print(f"  Sections fetched   : {result['section_count']}")
    print(f"  Requirements found : {result['requirement_count']}")
    print(f"  human_review_required: {result['human_review_required']}")
    print()
    # Family breakdown
    family_counts: dict[str, int] = {}
    for sec in result["sections"]:
        for fam in sec.get("nist_families", []):
            family_counts[fam] = family_counts.get(fam, 0) + 1
    if family_counts:
        print("  NIST family mapping counts (heuristic, unreviewed):")
        for fam in ALL_NIST_FAMILIES:
            if fam in family_counts:
                print(f"    {fam}: {family_counts[fam]}")
    else:
        print("  No NIST family mappings found (no keyword matches).")


def _write_output(result: dict, title: int, part: int | str) -> None:
    """Write result dict as JSON to canonical-sources/cfr/{title}-cfr-{part}.json."""
    CFR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CFR_OUTPUT_DIR / f"{title}-cfr-{part}.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {result['requirement_count']} requirements → {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "eCFR loader: pull CFR sections via REST API and map to NIST 800-53 families."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 ecfr_loader.py --title 45 --part 164 --subpart C --dry-run
  python3 ecfr_loader.py --title 16 --part 314 --format json
  python3 ecfr_loader.py --title 21 --part 11 --dry-run --format summary
  python3 ecfr_loader.py --title 10 --part 73 --dry-run

Known CFR parts: 45/164 (HIPAA), 16/314 (GLBA), 21/11 (FDA ER),
                 21/820 (FDA QSR), 10/73 (NRC), 42/2 (SAMHSA),
                 47/64 (FCC), 17/229 (SEC)
""",
    )
    parser.add_argument(
        "--title", type=int, required=True, metavar="N",
        help="CFR title number (e.g. 45)",
    )
    parser.add_argument(
        "--part", required=True, metavar="P",
        help="CFR part number (e.g. 164)",
    )
    parser.add_argument(
        "--subpart", metavar="S", default=None,
        help="CFR subpart letter (e.g. C)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print section count and summary; do not write output file",
    )
    parser.add_argument(
        "--format", choices=["summary", "json"], default="summary", dest="fmt",
        help="Output format when --dry-run is set (default: summary)",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # Normalise part: keep as string so "73" stays "73" for filenames
    part_str = args.part.strip()

    loader = eCFRLoader()
    result = loader.load_cfr_part(
        title=args.title,
        part=part_str,
        subpart=args.subpart,
        dry_run=args.dry_run,
    )

    if args.dry_run and args.fmt == "json":
        # Print full JSON result to stdout
        print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
