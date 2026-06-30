"""
OSCAL supplement loader.

Reads the cached OSCAL v5.2.0 full extract and provides controls that are
present in the upstream OSCAL catalog but missing from our spreadsheet-based
sources. This bridges the gap when NIST releases new controls (e.g. IA-13,
SA-24) that haven't yet appeared in our Excel/CSV sources.

Also provides title corrections for controls whose titles have drifted
from the authoritative OSCAL wording.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent
_OSCAL_EXTRACT = _REPO_ROOT / "canonical-sources" / "oscal_v5.2.0_full_extract.json"


def _oscal_id_to_canonical(oscal_id: str) -> str:
    oscal_id = oscal_id.strip().lower()
    m = re.match(r"^([a-z]{2,3})-(\d+)(?:\.(\d+))?$", oscal_id)
    if not m:
        return oscal_id.upper()
    fam, num, enh = m.group(1), m.group(2), m.group(3)
    base = f"{fam.upper()}-{int(num)}"
    return f"{base}({int(enh)})" if enh else base


def _family_from_id(ctrl_id: str) -> str:
    m = re.match(r"^([A-Z]{2,3})", ctrl_id)
    return m.group(1) if m else ""


def _is_enhancement(ctrl_id: str) -> bool:
    return bool(re.match(r"^[A-Z]{2,3}-\d+\(\d+\)$", ctrl_id))


def _base_id(ctrl_id: str) -> str:
    m = re.match(r"^([A-Z]{2,3}-\d+)\(\d+\)$", ctrl_id)
    return m.group(1) if m else ctrl_id


def _load_extract() -> dict:
    if not _OSCAL_EXTRACT.exists():
        return {}
    with open(_OSCAL_EXTRACT, encoding="utf-8") as f:
        return json.load(f)


def _oscal_to_record(oscal_id: str, data: dict) -> dict:
    canonical = _oscal_id_to_canonical(oscal_id)
    related_str = ", ".join(
        _oscal_id_to_canonical(r) for r in data.get("related_controls", [])
    )
    return {
        "id": canonical,
        "family": _family_from_id(canonical),
        "title": data.get("title", ""),
        "text": data.get("statement", ""),
        "discussion": data.get("discussion", ""),
        "related_controls": related_str,
        "baselines": {},
        "oscal_supplement": True,
    }


def load_supplement_controls(
    existing_ids: set,
) -> Dict[str, dict]:
    """
    Return controls from the OSCAL extract that are NOT in existing_ids,
    grouped by base control (same structure as load_catalog output).
    """
    extract = _load_extract()
    if not extract:
        return {}

    supplement: Dict[str, dict] = {}

    for oscal_id, data in extract.items():
        canonical = _oscal_id_to_canonical(oscal_id)
        if canonical in existing_ids:
            continue

        record = _oscal_to_record(oscal_id, data)
        is_enh = _is_enhancement(canonical)
        base = _base_id(canonical)

        if is_enh:
            if base not in supplement:
                if base in existing_ids:
                    supplement[base] = {
                        "id": base,
                        "family": _family_from_id(base),
                        "title": "",
                        "text": "",
                        "discussion": "",
                        "related_controls": "",
                        "baselines": {},
                        "enhancements": [],
                        "_existing_base": True,
                    }
                else:
                    base_oscal = extract.get(
                        next((k for k in extract if _oscal_id_to_canonical(k) == base), ""),
                        {},
                    )
                    base_record = _oscal_to_record(
                        next((k for k in extract if _oscal_id_to_canonical(k) == base), base),
                        base_oscal,
                    )
                    base_record["enhancements"] = []
                    base_record["oscal_supplement"] = True
                    supplement[base] = base_record
            supplement[base]["enhancements"].append(record)
        else:
            if canonical not in supplement:
                record["enhancements"] = []
                supplement[canonical] = record
            else:
                supplement[canonical].update(record)
                supplement[canonical].setdefault("enhancements", [])

    return supplement


def get_title_corrections(existing_controls: Dict[str, dict]) -> List[dict]:
    """
    Compare existing control titles against OSCAL and return corrections.
    Only flags changes where the OSCAL title differs from ours after
    normalizing the enhancement pipe-prefix format.
    """
    extract = _load_extract()
    if not extract:
        return []

    def _norm(t: str) -> str:
        t = (t or "").strip()
        if "|" in t:
            t = t.rsplit("|", 1)[-1].strip()
        return t.lower()

    corrections = []
    for oscal_id, data in extract.items():
        canonical = _oscal_id_to_canonical(oscal_id)
        oscal_title = (data.get("title") or "").strip()
        if not oscal_title:
            continue

        our_title = ""
        if canonical in existing_controls:
            our_title = existing_controls[canonical].get("title", "")
        else:
            for ctrl in existing_controls.values():
                for enh in ctrl.get("enhancements", []):
                    if enh.get("id") == canonical:
                        our_title = enh.get("title", "")
                        break
                if our_title:
                    break

        if our_title and _norm(oscal_title) != _norm(our_title):
            corrections.append({
                "id": canonical,
                "oscal_title": oscal_title,
                "our_title": our_title,
            })

    return corrections
