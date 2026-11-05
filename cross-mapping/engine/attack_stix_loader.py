#!/usr/bin/env python3
"""
MITRE ATT&CK Enterprise STIX 2.1 Loader

Loads Enterprise ATT&CK from MITRE's TAXII 2.1 server and maps each technique to NIST SP 800-53
Rev. 5 controls with the issuer mapping: MITRE CTID Mappings Explorer (NIST 800-53 rev5 <-> ATT&CK).

Sources (phase 51):
  ATT&CK data:  https://attack-taxii.mitre.org/api/v21/ (Enterprise collection, paged)
  800-53 map:   https://ctid.mitre.org/mappings/ (nist_800_53 rev5, ATT&CK 16.1 enterprise JSON)

Only direct CTID mappings are written. A technique CTID does not map stays blank (no parent
inheritance, no keyword guess — CLAUDE.md: leave uncertain fields blank). A technique CTID mapped
under a different (16.1) name carries `nist_mapping_note` for human review. NIST's v13 spreadsheet
(the former source) returns 404 since at least 2026-07, which is why v19.1 shipped keyword guesses.

Output: canonical-sources/mitre-attack-techniques.json

Usage:
  python3 attack_stix_loader.py               # full pipeline
  python3 attack_stix_loader.py --dry-run     # parse only, no file write
  python3 attack_stix_loader.py --format json # emit pretty-printed JSON to stdout
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fetchkit  # governed fetch: host_policies.json caps, pacing, breaker, ledger (phase 51)

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_CANONICAL_DIR = _REPO_ROOT / "canonical-sources"
_OUTPUT_PATH = _CANONICAL_DIR / "mitre-attack-techniques.json"

TAXII_ROOT = "https://attack-taxii.mitre.org/api/v21/"
ENTERPRISE_COLLECTION = "x-mitre-collection--1f5f1533-f617-4ca8-9ab4-6a02367fa019"
TAXII_OBJECTS = f"{TAXII_ROOT}collections/{ENTERPRISE_COLLECTION}/objects/"
CTID_MAPPING_URL = ("https://ctid.mitre.org/mappings/data/nist_800_53/attack-16.1/nist_800_53-rev5/"
                    "enterprise/nist_800_53-rev5_attack-16.1-enterprise_json.json")
_TAXII_HDRS = {"Accept": "application/taxii+json;version=2.1",
               "User-Agent": "dbz-grc-attack-loader/1.0 (GRC cross-mapping backend)"}


def _fetch_url(url: str, max_retries: int = 3, initial_delay: float = 2.0, timeout: int = 60) -> bytes:
    try:
        return fetchkit.fetch(url, headers={"User-Agent": "dbz-grc-attack-loader/1.0 (GRC cross-mapping backend)"},
                              timeout=timeout, retries=max_retries, retry_on=(429, 503),
                              backoff=initial_delay).body
    except urllib.error.HTTPError as exc:
        if exc.code in (429, 503):
            raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts") from exc
        raise
    except (fetchkit.PolicyRefused, fetchkit.HostCooldown):
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts") from exc


# ── NIST XLSX parsing ─────────────────────────────────────────────────────────

# ── keyword fallback ──────────────────────────────────────────────────────────

# ── main class ────────────────────────────────────────────────────────────────

def taxii_objects(obj_type: str, page: int = 100) -> list:
    """Every object of one STIX type in MITRE's Enterprise ATT&CK TAXII collection, paged. An
    unpaged query times out at MITRE's gateway (502, measured 2026-11-05); a 502 is retried."""
    out, nxt = [], None
    while True:
        url = f"{TAXII_OBJECTS}?match%5Btype%5D={obj_type}&limit={page}" + (f"&next={nxt}" if nxt else "")
        d = json.loads(fetchkit.fetch(url, headers=_TAXII_HDRS, timeout=180, retries=3, backoff=15.0).body)
        out += d.get("objects", [])
        nxt = d.get("next") if d.get("more") else None
        if not nxt:
            return out


def _ver(v) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "")))


def remote_attack_version() -> str:
    """Newest x_mitre_version of the Enterprise collection object on MITRE's TAXII server."""
    return max((o.get("x_mitre_version") or "" for o in taxii_objects("x-mitre-collection")), key=_ver, default="")


def _norm_ctrl(c: str):
    m = re.fullmatch(r"([A-Z]{2})-0*(\d+)(?:\((0*)(\d+)\))?", c or "")
    return (f"{m.group(1)}-{int(m.group(2))}" + (f"({int(m.group(4))})" if m.group(4) else "")) if m else None


class ATTACKLoader:
    """
    Loads MITRE ATT&CK Enterprise STIX 2.1 bundle and maps techniques to
    NIST SP 800-53 Rev. 5 controls.
    """

    def __init__(self) -> None:
        self._bundle: Optional[Dict[str, Any]] = None
        self._nist_mapping: Optional[Dict[str, List[str]]] = None
        self._used_fallback: bool = False
        self._mapping_meta: Dict[str, Any] = {}
        self._ctid_names: Dict[str, str] = {}
        self._attack_version_seen: str = ""

    # ── public API ─────────────────────────────────────────────────────────

    def fetch_bundle(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Enterprise ATT&CK as a STIX bundle. Default: MITRE's TAXII server (attack-patterns plus the
        collection object). --stix-url keeps the single-file path for an explicit override."""
        if url:
            bundle = json.loads(_fetch_url(url).decode("utf-8"))
        else:
            print(f"  Fetching Enterprise ATT&CK from MITRE TAXII: {TAXII_OBJECTS}")
            bundle = {"type": "bundle", "objects": taxii_objects("attack-pattern") + taxii_objects("x-mitre-collection")}
        self._bundle = bundle
        return bundle

    def load_ctid_mapping(self, url: Optional[str] = None) -> Dict[str, List[str]]:
        """CTID Mappings Explorer: NIST 800-53 rev5 <-> ATT&CK, 'mitigates' rows only, control ids
        normalised to the catalog form (AC-02 -> AC-2). Keeps CTID's technique names for the rename
        note. Raises on failure: no mapping means no ingest."""
        doc = json.loads(fetchkit.fetch(url or CTID_MAPPING_URL, headers={"Accept": "application/json"}, timeout=90).body)
        mapping: Dict[str, set] = {}
        for m in doc.get("mapping_objects", []):
            c = _norm_ctrl(m.get("capability_id") or "")
            if m.get("mapping_type") == "mitigates" and c and m.get("attack_object_id"):
                mapping.setdefault(m["attack_object_id"], set()).add(c)
                self._ctid_names.setdefault(m["attack_object_id"], m.get("attack_object_name", ""))
        md = doc.get("metadata", {})
        self._mapping_meta = {"source": "CTID Mappings Explorer", "url": url or CTID_MAPPING_URL,
                              "framework": f"{md.get('mapping_framework')} {md.get('mapping_framework_version')}",
                              "mapping_attack_version": md.get("attack_version"), "last_update": md.get("last_update"),
                              "rows": sum(len(v) for v in mapping.values()), "techniques": len(mapping)}
        self._nist_mapping = {k: sorted(v, key=lambda c: (c.split("-")[0], _ver(c))) for k, v in mapping.items()}
        return self._nist_mapping

    def extract_techniques(self, bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract ATT&CK techniques from the STIX bundle.

        Processes 'attack-pattern' objects. For each technique extracts:
          technique_id, name, tactic, sub_technique_of, description_snippet,
          platform, is_subtechnique

        Returns list of technique dicts (nist_controls not yet populated).
        """
        objects = bundle.get("objects", [])

        # Build tactic lookup: phase_name → readable tactic name
        # (attack-pattern x_mitre_phases carries tactic slugs)
        # We'll also collect mitigation→technique relationships.

        # Collect external_id → ATT&CK ID for attack-patterns
        techniques: List[Dict[str, Any]] = []

        for obj in objects:
            if obj.get("type") != "attack-pattern":
                continue
            if obj.get("x_mitre_deprecated", False) or obj.get("revoked", False):
                continue

            # External references: ATT&CK ID is in the first mitre.attack ref
            ext_refs = obj.get("external_references", [])
            technique_id = ""
            for ref in ext_refs:
                if ref.get("source_name") in ("mitre-attack", "mitre-mobile-attack"):
                    technique_id = ref.get("external_id", "")
                    break

            if not technique_id:
                continue

            # Tactics come from kill_chain_phases
            tactics = []
            for kcp in obj.get("kill_chain_phases", []):
                if kcp.get("kill_chain_name") == "mitre-attack":
                    phase = kcp.get("phase_name", "")
                    if phase:
                        tactics.append(phase.replace("-", " ").title())

            # Sub-technique detection
            is_subtechnique = obj.get("x_mitre_is_subtechnique", False)
            sub_technique_of = ""
            if is_subtechnique and "." in technique_id:
                sub_technique_of = technique_id.rsplit(".", 1)[0]

            # Description snippet — first 300 chars of description
            description = obj.get("description", "")
            snippet = description[:300].strip()
            if len(description) > 300:
                snippet += "…"

            # Platforms
            platforms = obj.get("x_mitre_platforms", [])

            techniques.append(
                {
                    "technique_id":     technique_id,
                    "name":             obj.get("name", ""),
                    "tactic":           tactics,   # list of tactic names
                    "sub_technique_of": sub_technique_of,
                    "is_subtechnique":  is_subtechnique,
                    "description_snippet": snippet,
                    "platform":         platforms,
                    "nist_controls":    [],   # populated in map_techniques
                    "stix_id":          obj.get("id", ""),
                }
            )

        # Sort: parents before children
        techniques.sort(key=lambda t: t["technique_id"])
        return techniques

    def map_techniques(self, techniques: List[Dict[str, Any]], nist_mapping: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Direct issuer mappings only. A technique CTID does not map stays blank — no parent
        inheritance, no keyword guess (CLAUDE.md: leave uncertain fields blank). A mapped technique
        whose name changed since CTID's ATT&CK version carries nist_mapping_note."""
        for t in techniques:
            t["nist_controls"] = list(nist_mapping.get(t["technique_id"], []))
            old = self._ctid_names.get(t["technique_id"])
            if t["nist_controls"] and old and old.strip().lower() != t["name"].strip().lower():
                t["nist_mapping_note"] = (f"CTID mapped this id under its ATT&CK {self._mapping_meta.get('mapping_attack_version')} "
                                          f"name {old!r}; the v{self._attack_version_seen or '?'} name differs — review")
        self._used_fallback = False
        return techniques

    def run(self, dry_run: bool = False, stix_url: Optional[str] = None) -> Dict[str, Any]:
        """Full pipeline: fetch (TAXII) -> CTID mapping -> extract -> map -> optionally save."""
        print("=== ATT&CK STIX Loader ===")
        bundle = self.fetch_bundle(url=stix_url)
        colls = [o for o in bundle.get("objects", []) if o.get("type") == "x-mitre-collection"]
        newest = max(colls, key=lambda o: _ver(o.get("x_mitre_version")), default={})
        self._attack_version_seen = newest.get("x_mitre_version", "")
        mapping = self.load_ctid_mapping()
        techniques = self.map_techniques(self.extract_techniques(bundle), mapping)
        subtechs = sum(1 for t in techniques if t["is_subtechnique"])
        mapped = sum(1 for t in techniques if t["nist_controls"])
        result: Dict[str, Any] = {
            "_stix_bundle_modified": newest.get("modified", ""),
            "_attack_version": self._attack_version_seen,
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_stix_url": stix_url or TAXII_OBJECTS,
                "nist_mapping_source": self._mapping_meta,
                "total_techniques": len(techniques), "total_mapped": mapped, "total_subtechniques": subtechs,
                "total_unmapped_left_blank": len(techniques) - mapped,
                "total_mapping_notes": sum(1 for t in techniques if t.get("nist_mapping_note")),
                "used_fallback": False, "human_review_required": True,
            },
            "techniques": techniques,
        }
        print(f"  {len(techniques)} techniques ({subtechs} sub) | {mapped} with CTID controls, "
              f"{len(techniques) - mapped} left blank | ATT&CK {result['_attack_version']}")
        if dry_run:
            print("  [dry-run] Skipping file write.")
        else:
            _CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
            _OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"  Saved → {_OUTPUT_PATH}")
        return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Load MITRE ATT&CK Enterprise STIX 2.1 and map to NIST 800-53 controls."
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and map without writing output file",
    )
    p.add_argument(
        "--format",
        choices=["json", "summary"],
        default="summary",
        help="Output format for stdout (default: summary)",
    )
    p.add_argument(
        "--stix-url",
        default=None,
        help="Override the source with one STIX bundle URL (default: MITRE TAXII server)",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()
    loader = ATTACKLoader()
    result = loader.run(dry_run=args.dry_run, stix_url=args.stix_url)

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        meta = result["metadata"]
        print(
            f"\nSummary: {meta['total_techniques']} techniques loaded, "
            f"{meta['total_mapped']} mapped to 800-53 controls, "
            f"{meta['total_subtechniques']} sub-techniques"
        )
        print(f"  {meta['total_unmapped_left_blank']} left blank (no CTID mapping); "
              f"{meta.get('total_mapping_notes', 0)} carry a rename note for review")


if __name__ == "__main__":
    fetchkit.run_cli(main, "attack_stix_loader")
