#!/usr/bin/env python3
"""
pdf_structure_extractor.py
Structured text extraction from NIST/FIPS PDF publications.

Extracts section headings + text blocks from PDF files and maps them to
NIST 800-53 control families via keyword heuristics. Used for publications
that lack machine-readable OSCAL or CPRT format (FIPS 199, FIPS 200,
SP 800-57 parts, etc.).

Uses pdfplumber when available; falls back to a line-oriented heuristic
extractor when pdfplumber is not installed.

Output per PDF: canonical-sources/fips/{pub_id}-structured.json
  {
    "_source": "pdf_structure_extractor.py",
    "_pdf_path": "...",
    "_pub_id": "fips-199",
    "_extracted_at": "...",
    "sections": [
      {
        "section_id": "fips-199-sec-1",
        "page": 1,
        "title": "1. PURPOSE AND APPLICABILITY",
        "text": "...",
        "nist_families": ["RA", "CA"]
      }
    ]
  }

Usage:
    python3 pdf_structure_extractor.py --pdf path/to/fips199.pdf --pub-id fips-199
    python3 pdf_structure_extractor.py --pdf path/to/fips200.pdf --pub-id fips-200 --dry-run
    python3 pdf_structure_extractor.py --list-pending
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
FIPS_DIR = _REPO_ROOT / "canonical-sources" / "fips"

# NIST 800-53 control family keyword heuristics (same pattern as kev_loader.py)
_FAMILY_KEYWORDS: dict[str, list[str]] = {
    "AC": [
        "access control", "privilege", "authorization", "least privilege",
        "role-based", "discretionary", "mandatory access", "access enforcement",
    ],
    "AU": [
        "audit", "logging", "log record", "audit trail", "accountability",
        "event logging", "audit event",
    ],
    "CA": [
        "assessment", "authorization to operate", "ato", "security assessment",
        "continuous monitoring", "plan of action",
    ],
    "CM": [
        "configuration", "baseline configuration", "change control",
        "configuration management", "default settings", "hardening",
    ],
    "CP": [
        "contingency", "backup", "recovery", "continuity", "disaster recovery",
        "alternate site", "business continuity",
    ],
    "IA": [
        "identification", "authentication", "credential", "password",
        "authenticator", "multifactor", "identity proofing", "piv",
    ],
    "IR": [
        "incident", "incident response", "incident handling", "breach notification",
    ],
    "MA": [
        "maintenance", "preventive maintenance", "maintenance personnel",
    ],
    "MP": [
        "media", "media protection", "media sanitization", "removable media",
    ],
    "PE": [
        "physical", "physical access", "physical security", "facility",
        "environmental", "power", "fire protection",
    ],
    "PL": [
        "planning", "security plan", "rules of behavior", "concept of operations",
    ],
    "PM": [
        "program management", "risk management program", "information security program",
        "enterprise architecture",
    ],
    "PS": [
        "personnel", "screening", "termination", "transfer", "sanctions",
    ],
    "PT": [
        "personally identifiable information", "pii", "privacy",
        "consent", "data minimization",
    ],
    "RA": [
        "risk", "risk assessment", "vulnerability", "threat",
        "likelihood", "impact", "risk score", "categorization",
        "fips 199", "fips 200",
    ],
    "SA": [
        "acquisition", "supply chain", "developer", "system development",
        "software", "external service", "third-party",
    ],
    "SC": [
        "system and communications", "cryptography", "encryption", "tls", "ssl",
        "network", "boundary", "session", "fips-validated", "fips 140",
        "key management", "key establishment",
    ],
    "SI": [
        "system integrity", "malicious code", "spam", "information input",
        "error handling", "memory protection", "software integrity",
        "flaw remediation", "security alerts",
    ],
    "SR": [
        "supply chain risk", "provenance", "component authenticity",
        "supplier", "acquisition strategy",
    ],
}


def _map_to_nist_families(text: str) -> list[str]:
    """Keyword heuristic: map section text to NIST 800-53 control families."""
    text_lower = text.lower()
    matched: set[str] = set()
    for family, kws in _FAMILY_KEYWORDS.items():
        for kw in kws:
            if kw in text_lower:
                matched.add(family)
                break
    return sorted(matched)


_HEADING_RE = re.compile(
    r"^(\d+(\.\d+)*\.?\s+[A-Z][A-Z\s\-\/]{4,}|APPENDIX\s+[A-Z][\.\s].*|SECTION\s+\d+)",
    re.MULTILINE,
)


def _extract_sections_pdfplumber(pdf_path: Path) -> list[dict]:
    """Extract sections using pdfplumber (preferred)."""
    import pdfplumber  # type: ignore

    sections: list[dict] = []
    current_title = "PREAMBLE"
    current_text: list[str] = []
    current_page = 1
    section_idx = 0

    def _flush(title: str, page: int, lines: list[str]) -> None:
        nonlocal section_idx
        text = " ".join(lines).strip()
        if not text:
            return
        section_idx += 1
        sections.append({
            "section_id": f"sec-{section_idx:04d}",
            "page": page,
            "title": title,
            "text": text[:2000],
            "nist_families": _map_to_nist_families(title + " " + text),
        })

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if _HEADING_RE.match(line) and len(line) < 120:
                    _flush(current_title, current_page, current_text)
                    current_title = line
                    current_text = []
                    current_page = page_num
                else:
                    current_text.append(line)

    _flush(current_title, current_page, current_text)
    return sections


def _extract_sections_heuristic(pdf_path: Path) -> list[dict]:
    """
    Fallback: line-oriented heuristic extractor when pdfplumber is unavailable.
    Reads the PDF as bytes and extracts text-like sequences using regex.
    Very approximate — intended for smoke-testing without full PDF parsing.
    """
    raw = pdf_path.read_bytes()
    # Extract ASCII text blobs from PDF binary
    text_chunks = re.findall(rb"\(([^\)]{10,300})\)", raw)
    lines: list[str] = []
    for chunk in text_chunks:
        try:
            decoded = chunk.decode("latin-1", errors="ignore")
            # Skip lines that look like binary noise
            if decoded.count("\\") > 5 or decoded.count("\x00") > 3:
                continue
            lines.append(decoded.strip())
        except Exception:
            continue

    if not lines:
        return [{
            "section_id": "sec-0001",
            "page": 1,
            "title": "FULL DOCUMENT",
            "text": "(Could not extract text — PDF may be image-based or encrypted)",
            "nist_families": [],
        }]

    sections: list[dict] = []
    current_title = "PREAMBLE"
    current_text: list[str] = []
    section_idx = 0

    def _flush(title: str, text_lines: list[str]) -> None:
        nonlocal section_idx
        text = " ".join(text_lines).strip()
        if not text:
            return
        section_idx += 1
        sections.append({
            "section_id": f"sec-{section_idx:04d}",
            "page": 1,
            "title": title,
            "text": text[:2000],
            "nist_families": _map_to_nist_families(title + " " + text),
        })

    for line in lines:
        if _HEADING_RE.match(line) and len(line) < 120:
            _flush(current_title, current_text)
            current_title = line
            current_text = []
        else:
            current_text.append(line)

    _flush(current_title, current_text)
    return sections


def extract_sections(pdf_path: Path) -> list[dict]:
    """Extract sections from PDF using best available method."""
    try:
        import pdfplumber  # noqa: F401
        print(f"  [~] Using pdfplumber for {pdf_path.name}", file=sys.stderr)
        return _extract_sections_pdfplumber(pdf_path)
    except ImportError:
        print(
            "  [!] pdfplumber not installed — using heuristic fallback "
            "(install via: pip install pdfplumber)",
            file=sys.stderr,
        )
        return _extract_sections_heuristic(pdf_path)


def write_structured_output(
    sections: list[dict],
    pub_id: str,
    pdf_path: Path,
    output_path: Path,
) -> None:
    """Write extracted sections to canonical-sources/fips/{pub_id}-structured.json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "_source": "pdf_structure_extractor.py",
        "_pdf_path": str(pdf_path),
        "_pub_id": pub_id,
        "_extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_section_count": len(sections),
        "sections": sections,
    }
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[+] {len(sections)} sections → {output_path.name}", file=sys.stderr)


def list_pending() -> None:
    """Print FIPS/SP 800-series PDFs known to need extraction."""
    pending = [
        ("fips-199", "FIPS 199 — Information Security Categorization"),
        ("fips-200", "FIPS 200 — Minimum Security Requirements"),
        ("fips-197", "FIPS 197 — Advanced Encryption Standard (AES)"),
        ("fips-198-1", "FIPS 198-1 — HMAC"),
        ("fips-201-3", "FIPS 201-3 — PIV Credentials"),
        ("nist-sp-800-37-r2", "SP 800-37 Rev 2 — Risk Management Framework"),
        ("nist-sp-800-57-pt1-r5", "SP 800-57 Pt 1 Rev 5 — Key Management"),
        ("nist-sp-800-160-vol2-r1", "SP 800-160 Vol 2 Rev 1 — Cyber Resiliency"),
    ]
    print("\n[PDF Structure Extractor — Pending Publications]")
    for pub_id, title in pending:
        out = FIPS_DIR / f"{pub_id}-structured.json"
        status = "[DONE] " if out.exists() else "[PENDING]"
        print(f"  {status} {pub_id}: {title}")
    print("\n  Usage: python3 pdf_structure_extractor.py --pdf <path> --pub-id <id>")


def run(
    pdf_path: Path,
    pub_id: str,
    dry_run: bool = False,
) -> dict:
    print(f"[pdf_structure_extractor] Processing: {pdf_path.name}", file=sys.stderr)

    if not pdf_path.exists():
        print(f"  [!] File not found: {pdf_path}", file=sys.stderr)
        return {}

    sections = extract_sections(pdf_path)

    # Family distribution summary
    family_counts: dict[str, int] = {}
    for s in sections:
        for f in s.get("nist_families", []):
            family_counts[f] = family_counts.get(f, 0) + 1

    print(f"  [+] {len(sections)} sections extracted", file=sys.stderr)
    if family_counts:
        top = sorted(family_counts.items(), key=lambda x: -x[1])[:5]
        print(f"  [+] Top NIST families: {', '.join(f'{k}({v})' for k,v in top)}", file=sys.stderr)

    if dry_run:
        print("\n[DRY-RUN] Would write structured output — not writing.")
        for s in sections[:3]:
            print(f"  {s['section_id']}: {s['title'][:60]} → {s['nist_families']}")
        return {"sections": sections, "pub_id": pub_id, "_dry_run": True}

    output_path = FIPS_DIR / f"{pub_id}-structured.json"
    write_structured_output(sections, pub_id, pdf_path, output_path)
    return {"sections": sections, "pub_id": pub_id, "output_path": str(output_path)}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract structured sections from NIST/FIPS PDF publications."
    )
    p.add_argument("--pdf", type=Path, default=None,
                   help="Path to input PDF file.")
    p.add_argument("--pub-id", default=None,
                   help="Publication ID for output filename (e.g. fips-199).")
    p.add_argument("--dry-run", action="store_true",
                   help="Extract and print summary; do not write output.")
    p.add_argument("--list-pending", action="store_true",
                   help="List publications awaiting extraction.")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.list_pending:
        list_pending()
        return
    if not args.pdf:
        print("Error: --pdf required (or use --list-pending)", file=sys.stderr)
        sys.exit(1)
    pub_id = args.pub_id or args.pdf.stem
    run(Path(args.pdf), pub_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
