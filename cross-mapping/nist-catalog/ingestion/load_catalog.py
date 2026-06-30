"""
NIST 800-53 catalog loader.

Reads the r5.1.1 catalog (preferred) or r5.0 fallback.
Each row in the Excel is one control or control enhancement.
Enhancements (AC-2(1), AC-2(2)…) are their own rows — this loader groups
them under their base control.

Returns: dict[control_id → {id, family, title, text, discussion, related,
                              baselines, enhancements: [...]}]
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from config import col, source_path, header_row, sheet_name

# Canonical sources to try in preference order.
# r5.0 catalog is preferred because it uses standard ID format (AC-1, AC-2, AC-2(1)).
# r5.1.1 uses padded IDs (AC-01, AC-02(01)) and has blank rows — avoid as primary.
_CATALOG_SOURCES = ["nist-800-53-r5-catalog", "nist-800-53-r5-1-1"]
_BASELINE_SOURCES = ["nist-800-53b-baselines"]

_ENHANCEMENT_RE = re.compile(r"^([A-Z]{2,3}-\d+(?:\.\d+)?)\((\d+)\)$")
_BASE_RE = re.compile(r"^([A-Z]{2,3}-\d+(?:\.\d+)?)$")


def _family_from_id(ctrl_id: str) -> str:
    m = re.match(r"^([A-Z]{2,3})", ctrl_id)
    return m.group(1) if m else ""


def _is_enhancement(ctrl_id: str) -> bool:
    return bool(_ENHANCEMENT_RE.match(ctrl_id))


def _base_id(ctrl_id: str) -> str:
    m = _ENHANCEMENT_RE.match(ctrl_id)
    return m.group(1) if m else ctrl_id


def _read_catalog_df(source_id: str) -> Optional[pd.DataFrame]:
    path = source_path(source_id)
    if not path.exists():
        return None
    hr = header_row(source_id)
    sn = sheet_name(source_id)
    skiprows = list(range(hr)) if hr else None
    df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows)
    # Normalize column names (strip extra whitespace)
    df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]
    return df


def _baseline_flags(row: pd.Series, source_id: str) -> dict:
    """Extract baseline inclusion flags from a catalog row that includes baselines."""
    flags = {}
    for flag_role, key in [
        ("privacy_baseline", "privacy"),
        ("baseline_low", "low"),
        ("baseline_moderate", "moderate"),
        ("baseline_high", "high"),
    ]:
        try:
            col_name = col(source_id, flag_role)
            val = row.get(col_name, "")
            flags[key] = bool(str(val).strip().lower() in ("x", "x ", "x"))
        except KeyError:
            flags[key] = None
    return flags


@lru_cache(maxsize=1)
def _load_baseline_index() -> Dict[str, dict]:
    """Load 800-53B baselines into a dict[ctrl_id → baseline_flags]."""
    for src_id in _BASELINE_SOURCES:
        path = source_path(src_id)
        if not path.exists():
            continue
        hr = header_row(src_id)
        sn = sheet_name(src_id)
        skiprows = list(range(hr)) if hr else None
        df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows, header=0)
        df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]
        id_col_name = col(src_id, "id")
        result = {}
        for _, row in df.iterrows():
            ctrl_id = str(row.get(id_col_name, "")).strip()
            if not ctrl_id or ctrl_id == "nan":
                continue
            result[ctrl_id] = _baseline_flags(row, src_id)
        return result
    return {}


def load_catalog(family_filter: Optional[str] = None) -> Dict[str, dict]:
    """
    Load the NIST 800-53 catalog.

    Parameters
    ----------
    family_filter : str, optional
        If given (e.g. 'AC'), only load controls from that family.

    Returns
    -------
    dict[control_id → control_record]
    """
    df = None
    used_source = None
    for src_id in _CATALOG_SOURCES:
        df = _read_catalog_df(src_id)
        if df is not None:
            used_source = src_id
            break

    if df is None:
        raise FileNotFoundError(
            "No NIST 800-53 catalog file found. Expected one of:\n"
            + "\n".join(f"  {source_path(s)}" for s in _CATALOG_SOURCES)
        )

    id_col   = col(used_source, "id")
    name_col = col(used_source, "title")
    text_col = col(used_source, "text")

    # Optional columns (not all catalog files have them)
    def _opt_col(role):
        try:
            return col(used_source, role)
        except KeyError:
            return None

    disc_col    = _opt_col("discussion")
    related_col = _opt_col("related_controls")
    family_col  = _opt_col("family")

    # Pre-load baseline index (lazy, cached)
    baseline_index = _load_baseline_index()

    controls: Dict[str, dict] = {}

    for _, row in df.iterrows():
        ctrl_id = str(row.get(id_col, "")).strip()
        if not ctrl_id or ctrl_id == "nan":
            continue

        family = (str(row.get(family_col, "")).strip()
                  if family_col and pd.notna(row.get(family_col))
                  else _family_from_id(ctrl_id))

        if family_filter and family != family_filter:
            continue

        title      = str(row.get(name_col, "")).strip()
        text       = str(row.get(text_col, "")).strip() if text_col else ""
        discussion = (str(row.get(disc_col, "")).strip()
                      if disc_col and pd.notna(row.get(disc_col)) else "")
        related    = (str(row.get(related_col, "")).strip()
                      if related_col and pd.notna(row.get(related_col)) else "")

        # Join baselines from dedicated baseline source; fall back to inline column
        baselines = (baseline_index.get(ctrl_id)
                     or _baseline_flags(row, used_source))

        is_enh = _is_enhancement(ctrl_id)
        base = _base_id(ctrl_id)

        record = {
            "id": ctrl_id,
            "family": family,
            "title": title,
            "text": text,
            "discussion": discussion,
            "related_controls": related,
            "baselines": baselines,
        }

        if is_enh:
            # Attach to parent; create parent stub if not yet seen
            if base not in controls:
                controls[base] = {
                    "id": base,
                    "family": family,
                    "title": "",
                    "text": "",
                    "discussion": "",
                    "related_controls": "",
                    "baselines": {},
                    "enhancements": [],
                }
            controls[base].setdefault("enhancements", []).append(record)
        else:
            if ctrl_id in controls:
                # Stub already exists; merge in the real data
                controls[ctrl_id].update(record)
                controls[ctrl_id].setdefault("enhancements", [])
            else:
                record["enhancements"] = []
                controls[ctrl_id] = record

    return controls


def load_catalog_df(family_filter: Optional[str] = None) -> pd.DataFrame:
    """Return the raw catalog as a flat DataFrame (no grouping by base control)."""
    df = None
    for src_id in _CATALOG_SOURCES:
        df = _read_catalog_df(src_id)
        if df is not None:
            used_source = src_id
            break
    if df is None:
        raise FileNotFoundError("No NIST 800-53 catalog file found.")

    id_col = col(used_source, "id")
    if family_filter:
        mask = df[id_col].astype(str).str.match(rf"^{family_filter}")
        df = df[mask].copy()
    return df
