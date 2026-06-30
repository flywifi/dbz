"""
DISA CCI loader with r4→r5 bridge.

Step 1: Load DISA CCI List → dict[cci_id → list[r4_control_ref]]
Step 2: Load NIST r4→r5 bridge → dict[r4_id → r5_id]
Step 3: Compose to get dict[cci_id → list[r5_control_id]] (clean r5 IDs)

The CCI list maps each CCI to one or more NIST 800-53 r4 control IDs.
The bridge workbook maps r4 IDs → r5 IDs.
"""

import re
from functools import lru_cache
from typing import Dict, List, Set

import pandas as pd

from config import col, source_path, header_row, sheet_name


_CTRL_PARSE_RE = re.compile(r"([A-Z]{2,3}-\d+(?:\.\d+)?(?:\(\d+\))?)")


def _parse_nist_refs(text: str) -> List[str]:
    """Extract NIST control IDs from text like 'AC-1 a', 'AC-2(1)', 'PM-5.1'."""
    if not isinstance(text, str):
        return []
    return _CTRL_PARSE_RE.findall(text.upper())


@lru_cache(maxsize=1)
def load_cci_to_r4() -> Dict[str, List[str]]:
    """
    Load DISA CCI list.
    Returns dict[cci_id → sorted list of NIST r4 control IDs].
    """
    src = "disa-cci-list"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"CCI list not found: {path}")

    hr = header_row(src)
    sn = sheet_name(src)
    skiprows = list(range(hr)) if hr else None
    df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows)
    df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]

    cci_col  = col(src, "cci_id")
    ref_col  = col(src, "nist_r4_ref")

    cci_map: Dict[str, Set[str]] = {}
    for _, row in df.iterrows():
        cci = str(row.get(cci_col, "")).strip()
        ref = str(row.get(ref_col, "")).strip()
        if not cci or cci == "nan":
            continue
        refs = _parse_nist_refs(ref)
        if cci not in cci_map:
            cci_map[cci] = set()
        cci_map[cci].update(refs)

    return {k: sorted(v) for k, v in cci_map.items()}


@lru_cache(maxsize=1)
def load_r4_to_r5_bridge() -> Dict[str, str]:
    """
    Load the r4→r5 comparison workbook.
    Returns dict[r4_control_id → r5_control_id].

    The workbook row structure (after skipping row 0):
      col 0 = control ID (same ID in r5, or withdrawn/merged note)
    This is a one-to-one mapping (same IDs mostly, with some additions/withdrawals).
    """
    src = "nist-r4-to-r5-bridge"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"r4→r5 bridge not found: {path}")

    hr = header_row(src)  # = 1
    sn = sheet_name(src)
    skiprows = list(range(hr)) if hr else None
    df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows)
    df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]

    # After skipping row 0, row 1 becomes headers: ID, TITLE, Privacy, L, M, H, ...
    id_col = col(src, "r5_id")  # = "ID"

    # Build r4→r5 map: for most controls the ID is unchanged;
    # the bridge shows what the r5 ID is (same or updated).
    # Since this is primarily a comparison workbook, the IDs listed are r5 IDs.
    # For CCI bridging: r4 IDs that match are retained as-is; withdrawn ones are dropped.
    bridge: Dict[str, str] = {}
    for _, row in df.iterrows():
        r5_id = str(row.get(id_col, "")).strip()
        if not r5_id or r5_id == "nan":
            continue
        ids_in_cell = _parse_nist_refs(r5_id)
        for ctrl_id in ids_in_cell:
            # r4 and r5 IDs are the same for most controls;
            # this provides an existence check that the r5 catalog has this ID
            bridge[ctrl_id] = ctrl_id

    return bridge


def load_cci_to_r5() -> Dict[str, List[str]]:
    """
    Compose CCI→r4 and r4→r5 bridge.
    Returns dict[cci_id → sorted list of NIST 800-53 r5 control IDs].

    CCIs that only map to r4 controls withdrawn in r5 are dropped.
    """
    cci_r4 = load_cci_to_r4()
    r4_r5  = load_r4_to_r5_bridge()

    result: Dict[str, Set[str]] = {}
    for cci, r4_ids in cci_r4.items():
        r5_ids = set()
        for r4_id in r4_ids:
            r5_id = r4_r5.get(r4_id)
            if r5_id:
                r5_ids.add(r5_id)
        if r5_ids:
            result[cci] = r5_ids

    return {k: sorted(v) for k, v in result.items()}


def build_nist_to_cci_index() -> Dict[str, List[str]]:
    """
    Invert the CCI→r5 map to get dict[r5_control_id → sorted list of CCI IDs].
    Useful for annotating each NIST control with its mapped CCIs.
    """
    cci_r5 = load_cci_to_r5()
    index: Dict[str, Set[str]] = {}
    for cci, r5_ids in cci_r5.items():
        for r5_id in r5_ids:
            index.setdefault(r5_id, set()).add(cci)
    return {k: sorted(v) for k, v in index.items()}
