#!/usr/bin/env python3
"""
olir_crawler.py
NIST CPRT OLIR (Online Informative Reference) auto-downloader.

Polls the NIST CPRT OLIR catalog for new crosswalk publications not yet
present in canonical-sources/. Downloads new OLIRs as XLSX or CSV and
updates source_manifest.json.

OLIRs follow the STRM (Set Theory Relationship Mapping) format used in
nist-800-53r5-to-iso-27001-olir and nist-csf2-concept-crosswalk — the
same format already parsed by load_crosswalks.py.

Usage:
    python3 olir_crawler.py --dry-run
    python3 olir_crawler.py --auto-download
    python3 olir_crawler.py --list-known
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
CANONICAL_DIR = _REPO_ROOT / "canonical-sources"
SOURCE_MANIFEST_PATH = CANONICAL_DIR / "source_manifest.json"
FEED_REGISTRY_PATH = CANONICAL_DIR / "feed_registry.json"
OLIRS_DIR = CANONICAL_DIR / "olirs"

CPRT_OLIR_API = "https://csrc.nist.gov/api/olir/finalized"
TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_BASE = 2.0
USER_AGENT = "dbz-olir-crawler/1.0 (GRC OLIR auto-download; polite client)"

# Known OLIRs already ingested — skip re-download
KNOWN_OLIR_KEYS = {
    "nist-800-53r5-to-iso-27001-olir",
    "nist-csf2-concept-crosswalk",
    "cmmc-800-171-53-crosswalk",
}


def _fetch(url: str) -> bytes | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urlopen(req, timeout=TIMEOUT) as resp:
                data = b""
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    data += chunk
                return data
        except HTTPError as e:
            print(f"  [!] HTTP {e.code} attempt {attempt}: {url}", file=sys.stderr)
            if e.code in (429, 503):
                time.sleep(BACKOFF_BASE ** attempt)
            else:
                return None
        except URLError as e:
            print(f"  [!] URL error attempt {attempt}: {e.reason}", file=sys.stderr)
            time.sleep(BACKOFF_BASE ** attempt)
        except Exception as e:
            print(f"  [!] Error attempt {attempt}: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE ** attempt)
    return None


def _fetch_json(url: str) -> dict | list | None:
    raw = _fetch(url)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [!] JSON parse error: {e}", file=sys.stderr)
        return None


def _load_source_manifest() -> dict:
    if not SOURCE_MANIFEST_PATH.exists():
        return {"sources": [], "er_crosswalk_csvs": []}
    return json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))


def _save_source_manifest(manifest: dict) -> None:
    SOURCE_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _manifest_entries(manifest: dict) -> list[dict]:
    """Return flat list of all source entries from manifest."""
    result: list[dict] = []
    for key in ("sources", "er_crosswalk_csvs"):
        val = manifest.get(key, [])
        if isinstance(val, list):
            result.extend(e for e in val if isinstance(e, dict))
    return result


def fetch_olir_catalog() -> list[dict]:
    """Fetch the NIST CPRT OLIR catalog and return structured OLIR list."""
    print(f"  [~] Fetching OLIR catalog from {CPRT_OLIR_API}", file=sys.stderr)
    data = _fetch_json(CPRT_OLIR_API)
    if data is None:
        return []

    items = data if isinstance(data, list) else data.get("oLIRs", data.get("items", []))
    olirs: list[dict] = []
    for item in items:
        olir_id = item.get("id") or item.get("olirId", "")
        focal = item.get("focalDocument") or item.get("focal_document", "")
        reference = item.get("referenceDocument") or item.get("reference_document", "")
        version = item.get("version") or item.get("focalDocumentVersion", "")
        download_url = item.get("downloadUrl") or item.get("download_url", "")
        published = item.get("published") or item.get("publishedDate", "")
        olirs.append({
            "olir_id": olir_id,
            "focal_document": focal,
            "reference_document": reference,
            "version": version,
            "download_url": download_url,
            "published": published,
        })

    print(f"  [+] {len(olirs)} OLIRs in catalog", file=sys.stderr)
    return olirs


def _derive_manifest_key(olir: dict) -> str:
    """Generate a source_manifest key from an OLIR entry."""
    focal = olir.get("focal_document", "").lower().replace(" ", "-").replace(".", "")
    ref = olir.get("reference_document", "").lower().replace(" ", "-").replace(".", "").replace("/", "-")
    return f"olir-{focal[:20]}-to-{ref[:20]}".replace("--", "-")


def _derive_filename(olir: dict) -> str:
    """Derive a canonical filename for the downloaded OLIR."""
    key = _derive_manifest_key(olir)
    dl_url = olir.get("download_url", "")
    if dl_url.endswith(".xlsx"):
        return f"{key}.xlsx"
    if dl_url.endswith(".csv"):
        return f"{key}.csv"
    return f"{key}.xlsx"


def download_new_olirs(
    olirs: list[dict],
    dry_run: bool = False,
) -> list[dict]:
    """
    Download OLIRs not yet present in canonical-sources/olirs/.
    Returns list of newly-downloaded OLIR metadata for source_manifest updates.
    """
    OLIRS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_source_manifest()
    manifest_keys = {e.get("key", "") for e in _manifest_entries(manifest)}

    new_entries: list[dict] = []
    for olir in olirs:
        key = _derive_manifest_key(olir)
        if key in manifest_keys or key in KNOWN_OLIR_KEYS:
            print(f"  [skip] Already in manifest: {key}", file=sys.stderr)
            continue

        filename = _derive_filename(olir)
        target_path = OLIRS_DIR / filename
        if target_path.exists():
            print(f"  [skip] File already present: {filename}", file=sys.stderr)
            continue

        dl_url = olir.get("download_url", "")
        if not dl_url:
            print(f"  [!] No download URL for {key}", file=sys.stderr)
            continue

        print(f"  [~] Downloading OLIR: {key}", file=sys.stderr)
        print(f"       URL: {dl_url}", file=sys.stderr)

        if dry_run:
            print(f"  [DRY-RUN] Would download → olirs/{filename}", file=sys.stderr)
            new_entries.append({
                "key": key,
                "filename": f"olirs/{filename}",
                "role": "olir_crosswalk",
                "framework": f"OLIR: {olir['focal_document']} → {olir['reference_document']}",
                "version": olir.get("version", "unknown"),
                "url": dl_url,
                "format": "xlsx" if filename.endswith(".xlsx") else "csv",
                "loader": "load_crosswalks.py",
                "refresh": "on_new_olir",
                "olir_id": olir.get("olir_id", ""),
                "published": olir.get("published", ""),
                "_dry_run": True,
            })
            continue

        raw = _fetch(dl_url)
        if raw is None:
            print(f"  [!] Download failed for {key}", file=sys.stderr)
            continue

        target_path.write_bytes(raw)
        print(f"  [+] Saved: olirs/{filename} ({len(raw):,} bytes)", file=sys.stderr)

        manifest_entry = {
            "key": key,
            "filename": f"olirs/{filename}",
            "role": "olir_crosswalk",
            "framework": f"OLIR: {olir['focal_document']} → {olir['reference_document']}",
            "version": olir.get("version", "unknown"),
            "url": dl_url,
            "format": "xlsx" if filename.endswith(".xlsx") else "csv",
            "loader": "load_crosswalks.py",
            "refresh": "on_new_olir",
            "olir_id": olir.get("olir_id", ""),
            "published": olir.get("published", ""),
        }
        new_entries.append(manifest_entry)
        manifest.setdefault("sources", []).append(manifest_entry)
        time.sleep(1.0)

    if new_entries and not dry_run:
        _save_source_manifest(manifest)
        print(
            f"[+] source_manifest.json updated with {len(new_entries)} new OLIR entries",
            file=sys.stderr,
        )

    return new_entries


def list_known_olirs() -> None:
    """Print all known OLIR entries from source_manifest."""
    manifest = _load_source_manifest()
    olir_entries = [e for e in _manifest_entries(manifest) if e.get("role") == "olir_crosswalk"]
    print(f"\n[Known OLIRs in source_manifest] ({len(olir_entries)} entries)")
    for e in olir_entries:
        print(f"  {e['key']}: {e.get('framework', '?')} (v{e.get('version', '?')})")
    if not olir_entries:
        print("  (none yet — run --auto-download to populate)")


def run(dry_run: bool = False, auto_download: bool = False) -> list[dict]:
    olirs = fetch_olir_catalog()
    if not olirs:
        print("[!] No OLIRs fetched — check network or CPRT API.", file=sys.stderr)
        return []

    if dry_run or auto_download:
        new = download_new_olirs(olirs, dry_run=dry_run)
        print(f"\n[olir_crawler] {'DRY-RUN: ' if dry_run else ''}{len(new)} new OLIRs processed")
        for e in new:
            flag = " [DRY-RUN]" if e.get("_dry_run") else ""
            print(f"  {flag} {e['key']}: {e['framework']}")
        return new

    print(f"\n[olir_crawler] {len(olirs)} OLIRs in CPRT catalog (use --auto-download to sync)")
    for olir in olirs[:10]:
        print(f"  {olir['olir_id']}: {olir['focal_document']} → {olir['reference_document']}")
    if len(olirs) > 10:
        print(f"  ... and {len(olirs) - 10} more")
    return []


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Crawl NIST CPRT OLIR catalog and download new OLIRs.")
    p.add_argument("--dry-run", action="store_true",
                   help="List what would be downloaded; do not write files.")
    p.add_argument("--auto-download", action="store_true",
                   help="Download new OLIRs and update source_manifest.json.")
    p.add_argument("--list-known", action="store_true",
                   help="List OLIRs already in source_manifest.json.")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.list_known:
        list_known_olirs()
        return
    run(dry_run=args.dry_run, auto_download=args.auto_download)


if __name__ == "__main__":
    main()
