#!/usr/bin/env python3
"""
OSCAL Control-Level Diff Traverser.

The deepest prong of the framework "news feed": instead of only watching whether
a *file* changed (framework_crawler.py) or whether a *landing page* moved
(framework_monitor.py), this traverser fetches NIST's machine-readable OSCAL
catalog and compares it CONTROL-BY-CONTROL against our generated catalog.

It answers: "Has NIST added, withdrawn, or renamed any control since we last
built?" — the question that actually drives a catalog rebuild.

Source: usnistgov/oscal-content (the authoritative OSCAL release of 800-53).
We confirmed this GitHub raw URL is reachable; the file is ~10MB so the fetch
uses HTTP Range windows with per-window retry to survive proxy truncation.

Usage:
    python3 oscal_diff.py                         # diff live OSCAL vs our catalog
    python3 oscal_diff.py --our cross-mapping/nist-catalog/output/NIST_800_53_FULL_ALL_FAMILIES.json
    python3 oscal_diff.py --oscal-cache /tmp/oscal.json   # use a cached OSCAL file
    python3 oscal_diff.py --report out.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent

DEFAULT_CHANGELOG = _REPO_ROOT / "canonical-sources" / "framework_changelog.json"

DEFAULT_OSCAL_URL = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/main/"
    "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"
)
DEFAULT_OUR_CATALOG = (
    _REPO_ROOT / "cross-mapping" / "nist-catalog" / "output"
    / "NIST_800_53_FULL_ALL_FAMILIES.json"
)
DEFAULT_REPORT = _HERE.parent / "output" / "oscal_diff_report.json"

UA = "dbz-grc-oscal-traverser/1.0 (+github.com/flywifi/dbz)"
WINDOW = 512 * 1024  # 512KB Range windows (proxy truncates larger streams)


# ── Robust large-file fetch (Range windows + retry) ─────────────────────────────

def fetch_large_json(url: str, timeout: float = 60.0, max_retries: int = 4) -> dict:
    """
    Fetch a large JSON file using HTTP Range windows, retrying each window.
    Works around proxies that truncate long single-stream responses.
    """
    # Probe total size + range support
    probe = urllib.request.Request(
        url, headers={"User-Agent": UA, "Range": "bytes=0-0"})
    with urllib.request.urlopen(probe, timeout=timeout) as r:
        cr = r.headers.get("Content-Range", "")
        supports_range = r.status == 206 and "/" in cr
        total = int(cr.split("/")[-1]) if supports_range else 0

    if not supports_range or total == 0:
        # Fall back to a plain streamed read
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    buf = bytearray()
    start = 0
    while start < total:
        end = min(start + WINDOW - 1, total - 1)
        want = end - start + 1
        last_err = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": UA, "Range": f"bytes={start}-{end}"})
                # Loop-read until the window is fully drained (single read() can short-return)
                chunk = bytearray()
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    while len(chunk) < want:
                        b = r.read(want - len(chunk))
                        if not b:
                            break
                        chunk.extend(b)
                if len(chunk) == want:
                    buf.extend(chunk)
                    break
                last_err = f"short window {len(chunk)}/{want}"
            except Exception as e:
                last_err = repr(e)
        else:
            raise RuntimeError(f"Range window {start}-{end} failed after "
                               f"{max_retries} retries: {last_err}")
        start = end + 1

    return json.loads(bytes(buf))


# ── ID normalization (OSCAL lowercase dotted → our canonical) ───────────────────

def oscal_id_to_canonical(oscal_id: str) -> str:
    """
    Convert an OSCAL control id to our canonical form.

      ac-1     → AC-1
      ac-2.1   → AC-2(1)
      ac-2.13  → AC-2(13)
      pm-31    → PM-31
    """
    oscal_id = oscal_id.strip().lower()
    m = re.match(r"^([a-z]{2,3})-(\d+)(?:\.(\d+))?$", oscal_id)
    if not m:
        return oscal_id.upper()
    fam, num, enh = m.group(1), m.group(2), m.group(3)
    base = f"{fam.upper()}-{int(num)}"
    return f"{base}({int(enh)})" if enh else base


# ── Traverse the OSCAL catalog ──────────────────────────────────────────────────

def traverse_oscal(catalog_doc: dict) -> Tuple[Dict[str, str], dict]:
    """
    Walk groups → controls → nested controls (enhancements).
    Returns (controls, meta):
      controls : dict[canonical_id → title]
      meta     : {version, last_modified, oscal_version, group_count}
    """
    catalog = catalog_doc.get("catalog", catalog_doc)
    md = catalog.get("metadata", {})
    meta = {
        "version": md.get("version", ""),
        "last_modified": md.get("last-modified", ""),
        "oscal_version": md.get("oscal-version", ""),
        "title": md.get("title", ""),
    }

    controls: Dict[str, str] = {}

    def _walk(ctrl_list):
        for c in ctrl_list or []:
            cid = c.get("id", "")
            if cid:
                controls[oscal_id_to_canonical(cid)] = c.get("title", "")
            # Enhancements are nested under "controls"
            if c.get("controls"):
                _walk(c["controls"])

    for group in catalog.get("groups", []):
        _walk(group.get("controls", []))
        # Some groups nest sub-groups
        for sub in group.get("groups", []):
            _walk(sub.get("controls", []))

    meta["group_count"] = len(catalog.get("groups", []))
    return controls, meta


# ── Load our generated catalog ──────────────────────────────────────────────────

def load_our_controls(path: Path) -> Dict[str, str]:
    """
    Flatten our generated catalog (base controls + enhancements) into
    dict[canonical_id → title].
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    out: Dict[str, str] = {}

    def _ingest(record: dict):
        cid = record.get("id", "")
        if cid:
            out[cid] = record.get("title", "")
        for enh in record.get("enhancements", []):
            eid = enh.get("id", "")
            if eid:
                out[eid] = enh.get("title", "")

    # Nested {family → {ctrl_id → record}} or flat {ctrl_id → record}
    is_nested = all(re.match(r"^[A-Z]{2,3}$", k) for k in list(data.keys())[:10])
    if is_nested:
        for fam_controls in data.values():
            for record in fam_controls.values():
                _ingest(record)
    else:
        for record in data.values():
            _ingest(record)

    return out


# ── Diff ─────────────────────────────────────────────────────────────────────────

def diff_catalogs(oscal: Dict[str, str], ours: Dict[str, str]) -> dict:
    """
    Compare the authoritative OSCAL control set against ours.

    Returns a structured diff:
      added_upstream   : in OSCAL, not in ours (we're behind — likely new controls)
      missing_upstream : in ours, not in OSCAL (stale/withdrawn or ID drift)
      title_changed    : same id, different title (rename / wording change)
    """
    oscal_ids = set(oscal)
    our_ids = set(ours)

    added_upstream = sorted(oscal_ids - our_ids)
    missing_upstream = sorted(our_ids - oscal_ids)

    def _norm_title(t: str) -> str:
        # Enhancement titles differ in format: OSCAL stores just the child name
        # ("Pattern-hiding Displays") while we store the full path
        # ("Device Lock | Pattern-hiding Displays"). Compare the child portion only.
        t = (t or "").strip()
        if "|" in t:
            t = t.rsplit("|", 1)[-1].strip()
        return t.lower()

    title_changed = []
    for cid in sorted(oscal_ids & our_ids):
        ot = (oscal[cid] or "").strip()
        rt = (ours[cid] or "").strip()
        if ot and rt and _norm_title(ot) != _norm_title(rt):
            title_changed.append({"id": cid, "oscal_title": ot, "our_title": rt})

    return {
        "added_upstream": added_upstream,
        "missing_upstream": missing_upstream,
        "title_changed": title_changed,
        "counts": {
            "oscal_total": len(oscal_ids),
            "our_total": len(our_ids),
            "added_upstream": len(added_upstream),
            "missing_upstream": len(missing_upstream),
            "title_changed": len(title_changed),
            "in_sync": len(oscal_ids & our_ids) - len(title_changed),
        },
    }


# ── Changelog writer ─────────────────────────────────────────────────────────────

def write_changelog_entry(
    diff: dict,
    oscal_meta: dict,
    changelog_path: Path,
) -> Optional[str]:
    """
    Append a new entry to framework_changelog.json when the diff has changes.
    Sets human_confirmed=False; a human must verify and set it to true.
    Returns the changelog_id of the new entry, or None if nothing was written.
    """
    counts = diff.get("counts", {})
    has_changes = (
        counts.get("added_upstream", 0) > 0
        or counts.get("missing_upstream", 0) > 0
        or counts.get("title_changed", 0) > 0
    )
    if not has_changes:
        print("[changelog] No control-level changes found — skipping changelog entry.")
        return None

    version_to = oscal_meta.get("version", "unknown")
    change_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_id = f"nist-800-53\x00{version_to}\x00{change_date}"
    changelog_id = hashlib.sha1(raw_id.encode()).hexdigest()[:16]

    controls_renamed = [
        {
            "id": t["id"],
            "old_title": t["our_title"],
            "new_title": t["oscal_title"],
        }
        for t in diff.get("title_changed", [])
    ]

    entry = {
        "changelog_id": changelog_id,
        "framework_id": "nist-800-53",
        "version_from": None,
        "version_to": version_to,
        "change_date": change_date,
        "source_manifest_keys_updated": [],
        "controls_added": diff.get("added_upstream", []),
        "controls_withdrawn": diff.get("missing_upstream", []),
        "controls_renamed": controls_renamed,
        "controls_modified": [],
        "announcement_ref": None,
        "human_confirmed": False,
        "notes": (
            f"Auto-generated by oscal_diff.py from OSCAL catalog "
            f"(version {version_to}, modified {oscal_meta.get('last_modified','?')}). "
            f"human_confirmed=False until verified on primary source."
        ),
    }

    existing: dict = {"schema_version": "1.0.0", "entries": []}
    if changelog_path.exists():
        try:
            existing = json.loads(changelog_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Could not read {changelog_path}: {e}", file=sys.stderr)

    # Deduplicate by changelog_id
    existing_ids = {e["changelog_id"] for e in existing.get("entries", [])}
    if changelog_id in existing_ids:
        print(f"[changelog] Entry {changelog_id} already exists — skipping duplicate.")
        return changelog_id

    existing.setdefault("entries", []).append(entry)
    if changelog_path == DEFAULT_CHANGELOG:
        # canonical registry — route through the single writer (tools/registry_io.py)
        sys.path.insert(0, str(_REPO_ROOT / "tools"))
        import registry_io
        registry_io.save("framework_changelog", existing)
    else:  # explicit non-canonical target (tests/scratch) keeps the same convention
        changelog_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(f"[changelog] Wrote entry {changelog_id} → {changelog_path}")
    print(f"           controls_added={len(entry['controls_added'])}, "
          f"controls_withdrawn={len(entry['controls_withdrawn'])}, "
          f"controls_renamed={len(entry['controls_renamed'])}")
    return changelog_id


# ── Orchestration ────────────────────────────────────────────────────────────────

def run_diff(
    oscal_url: str = DEFAULT_OSCAL_URL,
    our_catalog: Path = DEFAULT_OUR_CATALOG,
    oscal_cache: Optional[Path] = None,
    report_path: Path = DEFAULT_REPORT,
    dry_run: bool = False,
    write_changelog: bool = False,
    changelog_path: Path = DEFAULT_CHANGELOG,
) -> dict:
    if oscal_cache and Path(oscal_cache).exists():
        print(f"[*] Loading OSCAL from cache: {oscal_cache}")
        with open(oscal_cache, encoding="utf-8") as f:
            oscal_doc = json.load(f)
    else:
        print(f"[*] Fetching OSCAL catalog (~10MB, Range-windowed) …")
        oscal_doc = fetch_large_json(oscal_url)
        if oscal_cache:
            Path(oscal_cache).parent.mkdir(parents=True, exist_ok=True)
            with open(oscal_cache, "w", encoding="utf-8") as f:
                json.dump(oscal_doc, f)
            print(f"    cached → {oscal_cache}")

    oscal_controls, oscal_meta = traverse_oscal(oscal_doc)
    print(f"    OSCAL: {len(oscal_controls)} controls "
          f"(version {oscal_meta.get('version','?')}, "
          f"modified {oscal_meta.get('last_modified','?')})")

    if not our_catalog.exists():
        raise FileNotFoundError(
            f"Our catalog not found: {our_catalog}\nRun generate_controls.py first.")
    our_controls = load_our_controls(our_catalog)
    print(f"    Ours:  {len(our_controls)} controls")

    diff = diff_catalogs(oscal_controls, our_controls)

    report = {
        "_schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "oscal_source": oscal_url,
        "oscal_metadata": oscal_meta,
        "our_catalog": str(our_catalog),
        "diff": diff,
        "human_review_required": True,
    }

    c = diff["counts"]
    print(f"\n[*] Control-level diff:")
    print(f"    in sync         : {c['in_sync']}")
    print(f"    added upstream  : {c['added_upstream']}  (NIST has, we don't)")
    print(f"    missing upstream: {c['missing_upstream']}  (we have, NIST doesn't)")
    print(f"    title changed   : {c['title_changed']}")

    if diff["added_upstream"]:
        print(f"\n[!] Controls NIST has that we don't (first 20):")
        print("    " + ", ".join(diff["added_upstream"][:20]))
    if diff["title_changed"]:
        print(f"\n[!] Title changes (first 5):")
        for t in diff["title_changed"][:5]:
            print(f"    {t['id']}: {t['our_title']!r} → {t['oscal_title']!r}")

    if not dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n[✓] OSCAL diff report: {report_path}")

        if write_changelog:
            write_changelog_entry(diff, oscal_meta, changelog_path)

    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OSCAL control-level diff traverser")
    ap.add_argument("--oscal-url", default=DEFAULT_OSCAL_URL)
    ap.add_argument("--our", default=str(DEFAULT_OUR_CATALOG),
                    help="path to our generated full catalog JSON")
    ap.add_argument("--oscal-cache", default=None,
                    help="cache the fetched OSCAL JSON here (and reuse if present)")
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--write-changelog",
        action="store_true",
        help=(
            "Append an entry to framework_changelog.json when diff finds changes. "
            "Entry is written with human_confirmed=false."
        ),
    )
    ap.add_argument(
        "--changelog",
        default=str(DEFAULT_CHANGELOG),
        metavar="PATH",
        help="Path to framework_changelog.json (default: canonical-sources/framework_changelog.json)",
    )
    a = ap.parse_args(argv)

    run_diff(
        oscal_url=a.oscal_url,
        our_catalog=Path(a.our),
        oscal_cache=Path(a.oscal_cache) if a.oscal_cache else None,
        report_path=Path(a.report),
        dry_run=a.dry_run,
        write_changelog=a.write_changelog,
        changelog_path=Path(a.changelog),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
