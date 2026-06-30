#!/usr/bin/env python3
"""
MITRE ATT&CK Enterprise STIX 2.1 Loader

Parses the MITRE ATT&CK Enterprise STIX 2.1 bundle from GitHub and enriches
each technique with NIST SP 800-53 Rev. 5 control mappings using NIST's
official ATT&CK↔800-53 mapping spreadsheet.

Primary source:
  STIX bundle:   https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json
  NIST mapping:  https://www.nist.gov/system/files/documents/2023/09/12/SP800-53_ATT%26CK_v13_v1.xlsx

Fallback: keyword-based heuristic when the XLSX is not available.

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
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_CANONICAL_DIR = _REPO_ROOT / "canonical-sources"
_OUTPUT_PATH = _CANONICAL_DIR / "mitre-attack-techniques.json"

STIX_URL = (
    "https://raw.githubusercontent.com/mitre/cti/master/"
    "enterprise-attack/enterprise-attack.json"
)
NIST_XLSX_URL = (
    "https://www.nist.gov/system/files/documents/2023/09/12/"
    "SP800-53_ATT%26CK_v13_v1.xlsx"
)

# ── keyword heuristic fallback ────────────────────────────────────────────────
# Maps ATT&CK technique-name keywords → NIST 800-53 control families.
# Used when the NIST XLSX cannot be fetched.
_KEYWORD_HEURISTIC: List[Tuple[List[str], List[str]]] = [
    (["credential", "password", "bruteforce", "brute force", "phishing",
      "token", "authentication", "kerberos", "ntlm", "ldap"],             ["IA-5", "IA-2", "AC-7"]),
    (["privilege", "escalation", "sudo", "admin", "root", "uac bypass"],   ["AC-6", "AC-3"]),
    (["persistence", "registry", "startup", "scheduled task", "cron",
      "bootkit", "rootkit", "service"],                                     ["CM-7", "SI-7", "AU-12"]),
    (["lateral movement", "pass the hash", "remote service",
      "smb", "rdp", "wmi", "psexec"],                                       ["SC-7", "AC-17", "AU-12"]),
    (["exfiltration", "data transfer", "upload", "exfil"],                  ["SC-8", "SC-28", "AC-4"]),
    (["command and control", "c2", "dns", "http", "https", "beaconing",
      "proxy", "protocol tunnel"],                                           ["SC-7", "SI-4", "AU-12"]),
    (["discovery", "enumeration", "scan", "reconnaissance"],                ["CM-8", "SI-4", "CA-7"]),
    (["defense evasion", "obfuscation", "timestomp", "log clear",
      "indicator removal"],                                                  ["AU-9", "AU-12", "SI-7"]),
    (["collection", "screen capture", "keylog", "clipboard"],               ["AC-4", "SC-28", "AU-12"]),
    (["impact", "ransomware", "wiper", "denial of service", "dos",
      "resource hijacking", "defacement"],                                   ["CP-10", "SI-3", "SC-5"]),
    (["execution", "script", "powershell", "python", "shell", "macro"],     ["CM-7", "SI-3", "AU-12"]),
    (["supply chain", "trusted relationship", "third party"],               ["SA-12", "SR-3"]),
]


def _build_proxy_opener() -> urllib.request.OpenerDirector:
    """Return an opener that honours HTTPS_PROXY / HTTP_PROXY env vars."""
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    handlers: List[urllib.request.BaseHandler] = []
    if proxy_url:
        handlers.append(urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url}))
    return urllib.request.build_opener(*handlers)


def _fetch_url(
    url: str,
    max_retries: int = 3,
    initial_delay: float = 2.0,
    timeout: int = 60,
) -> bytes:
    """Fetch a URL with exponential back-off; returns raw bytes or raises."""
    opener = _build_proxy_opener()
    delay = initial_delay
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "dbz-grc-attack-loader/1.0 (GRC cross-mapping backend)"},
            )
            with opener.open(req, timeout=timeout) as resp:
                return resp.read()
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


# ── NIST XLSX parsing ─────────────────────────────────────────────────────────

def _parse_nist_xlsx(data: bytes) -> Dict[str, List[str]]:
    """
    Parse NIST ATT&CK↔800-53 XLSX using openpyxl.

    Expected columns: 'Technique ID', 'Technique Name', 'NIST SP 800-53 Rev. 5 Control'

    Returns dict: {technique_id: [control_id, ...]}
    """
    try:
        import openpyxl  # type: ignore
    except ImportError:
        raise ImportError("openpyxl is required to parse the NIST mapping XLSX")

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("XLSX is empty")

    # Locate header row
    header: Optional[List[str]] = None
    header_idx = 0
    for i, row in enumerate(rows):
        lower_cells = [str(c).lower() if c is not None else "" for c in row]
        if "technique id" in lower_cells:
            header = lower_cells
            header_idx = i
            break

    if header is None:
        raise ValueError("Could not find 'Technique ID' header in XLSX")

    col_tid   = next((i for i, h in enumerate(header) if "technique id" in h), None)
    col_ctrl  = next((i for i, h in enumerate(header) if "800-53" in h and "control" in h), None)

    if col_tid is None or col_ctrl is None:
        raise ValueError(f"Required columns not found in header: {header}")

    mapping: Dict[str, List[str]] = {}
    for row in rows[header_idx + 1:]:
        if not row or len(row) <= max(col_tid, col_ctrl):
            continue
        tid   = str(row[col_tid]).strip()  if row[col_tid]  is not None else ""
        ctrl  = str(row[col_ctrl]).strip() if row[col_ctrl] is not None else ""
        if not tid or not ctrl or tid.lower() in ("none", ""):
            continue
        # Control cell may contain multiple controls separated by commas or newlines
        controls = [c.strip() for c in ctrl.replace("\n", ",").split(",") if c.strip()]
        if tid not in mapping:
            mapping[tid] = []
        for c in controls:
            if c not in mapping[tid]:
                mapping[tid].append(c)

    wb.close()
    return mapping


# ── keyword fallback ──────────────────────────────────────────────────────────

def _keyword_map(technique_name: str, tactic) -> List[str]:
    """
    Keyword heuristic: returns a list of NIST control IDs based on technique
    name and tactic. Used when the NIST XLSX is unavailable.
    tactic may be a list or a string.
    """
    tactic_str = " ".join(tactic) if isinstance(tactic, list) else (tactic or "")
    needle = (technique_name + " " + tactic_str).lower()
    for keywords, controls in _KEYWORD_HEURISTIC:
        if any(kw in needle for kw in keywords):
            return controls
    # Default: SI family (general defensive integrity)
    return ["SI-3"]


# ── main class ────────────────────────────────────────────────────────────────

class ATTACKLoader:
    """
    Loads MITRE ATT&CK Enterprise STIX 2.1 bundle and maps techniques to
    NIST SP 800-53 Rev. 5 controls.
    """

    def __init__(self) -> None:
        self._bundle: Optional[Dict[str, Any]] = None
        self._nist_mapping: Optional[Dict[str, List[str]]] = None
        self._used_fallback: bool = False

    # ── public API ─────────────────────────────────────────────────────────

    def fetch_bundle(self, url: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch and parse the ATT&CK Enterprise STIX 2.1 JSON bundle.

        Returns the parsed bundle dict with 'objects' list.
        Raises RuntimeError on network failure after retries.
        """
        target = url or STIX_URL
        print(f"  Fetching STIX bundle from: {target}")
        raw = _fetch_url(target)
        bundle = json.loads(raw.decode("utf-8"))
        self._bundle = bundle
        return bundle

    def load_nist_mapping(self, xlsx_path: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Load the NIST ATT&CK↔800-53 mapping.

        Priority:
          1. xlsx_path if provided (local file)
          2. Download from NIST_XLSX_URL
          3. Return empty dict (keyword fallback will be used at map_techniques time)

        Returns {technique_id: [control_id, ...]}
        """
        # Local file override
        if xlsx_path:
            p = Path(xlsx_path)
            if p.exists():
                print(f"  Loading NIST mapping from local file: {p}")
                try:
                    mapping = _parse_nist_xlsx(p.read_bytes())
                    self._nist_mapping = mapping
                    return mapping
                except Exception as exc:
                    print(f"  [warn] Could not parse local XLSX: {exc}", file=sys.stderr)

        # Try downloading from NIST
        print(f"  Downloading NIST mapping from: {NIST_XLSX_URL}")
        try:
            raw = _fetch_url(NIST_XLSX_URL, timeout=90)
            mapping = _parse_nist_xlsx(raw)
            print(f"  NIST mapping loaded: {len(mapping)} techniques mapped")
            self._nist_mapping = mapping
            return mapping
        except ImportError:
            print(
                "  [warn] openpyxl not installed — cannot parse XLSX; will use keyword fallback.",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"  [warn] Could not load NIST XLSX ({exc}); will use keyword fallback.",
                file=sys.stderr,
            )

        self._nist_mapping = {}
        return {}

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

    def map_techniques(
        self,
        techniques: List[Dict[str, Any]],
        nist_mapping: Dict[str, List[str]],
    ) -> List[Dict[str, Any]]:
        """
        Enrich each technique with NIST 800-53 control IDs.

        Uses nist_mapping when available; falls back to keyword heuristic per
        technique name + tactic. Sets self._used_fallback if heuristic is used.
        """
        use_fallback = len(nist_mapping) == 0

        for t in techniques:
            tid = t["technique_id"]
            if not use_fallback and tid in nist_mapping:
                t["nist_controls"] = nist_mapping[tid]
            else:
                # For subtechniques try the parent mapping first
                parent = t.get("sub_technique_of", "")
                if not use_fallback and parent and parent in nist_mapping:
                    t["nist_controls"] = nist_mapping[parent]
                else:
                    # keyword fallback
                    t["nist_controls"] = _keyword_map(t["name"], t["tactic"])
                    self._used_fallback = True

        return techniques

    def run(self, dry_run: bool = False, stix_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Full pipeline: fetch → load mapping → extract → map → optionally save.

        Returns the result dict (also written to canonical-sources/ unless dry_run).
        """
        print("=== ATT&CK STIX Loader ===")

        # Step 1: Fetch STIX bundle
        bundle = self.fetch_bundle(url=stix_url)
        print(f"  STIX bundle: {len(bundle.get('objects', []))} objects total")

        # Step 2: Load NIST mapping
        nist_mapping = self.load_nist_mapping()

        # Step 3: Extract techniques
        print("  Extracting techniques...")
        techniques = self.extract_techniques(bundle)
        subtechs = sum(1 for t in techniques if t["is_subtechnique"])
        base     = len(techniques) - subtechs
        print(f"  Extracted: {base} techniques, {subtechs} sub-techniques")

        # Step 4: Map to NIST controls
        techniques = self.map_techniques(techniques, nist_mapping)
        mapped = sum(1 for t in techniques if t["nist_controls"])

        fallback_note = " (keyword heuristic fallback)" if self._used_fallback else ""
        print(
            f"\n  ✓ {len(techniques)} techniques loaded, "
            f"{mapped} mapped to 800-53 controls{fallback_note}, "
            f"{subtechs} sub-techniques"
        )

        # Extract bundle-level version anchor for incremental updates
        bundle_modified = bundle.get("modified") or bundle.get("spec_version") or ""
        attack_version = ""
        for obj in bundle.get("objects", []):
            if obj.get("type") == "x-mitre-collection":
                attack_version = obj.get("x_mitre_version", "")
                bundle_modified = bundle_modified or obj.get("modified", "")
                break

        # Build result envelope
        result: Dict[str, Any] = {
            "_stix_bundle_modified": bundle_modified,
            "_attack_version": attack_version,
            "metadata": {
                "generated_at":        datetime.now(timezone.utc).isoformat(),
                "source_stix_url":     stix_url or STIX_URL,
                "nist_mapping_source": "NIST SP800-53 ATT&CK v13 XLSX" if not self._used_fallback
                                        else "keyword heuristic fallback",
                "total_techniques":    len(techniques),
                "total_mapped":        mapped,
                "total_subtechniques": subtechs,
                "used_fallback":       self._used_fallback,
                "human_review_required": True,
            },
            "techniques": techniques,
        }

        if dry_run:
            print("  [dry-run] Skipping file write.")
        else:
            _CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
            _OUTPUT_PATH.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
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
        help="Override STIX bundle URL (default: mitre/cti GitHub raw)",
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
        if meta["used_fallback"]:
            print("  Note: keyword heuristic fallback used (NIST XLSX unavailable)")


if __name__ == "__main__":
    main()
