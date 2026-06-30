"""
Cross-framework crosswalk loaders.

Each loader returns a dict[nist_id → list[mapping_record]].
Multiple mapping records per NIST control are preserved (one-to-many OK).
"""

import re
from functools import lru_cache
from typing import Dict, List

import pandas as pd

from config import col, source_path, header_row, sheet_name, get_source


# ── ID normalization ──────────────────────────────────────────────────────────

_NIST_CORE_RE = re.compile(
    r"^([A-Z]{2,3})-0*(\d+)(?:\.\d+)?(?:\(0*(\d+)\))?"
)


def _normalize_nist_id(raw: str) -> str:
    """
    Convert padded or part-qualified NIST IDs to canonical form.

    AC-02       → AC-2
    AC-02(12)   → AC-2(12)
    AC-17(01)   → AC-17(1)
    AC-2c       → AC-2   (strip part suffix)
    AC-2(3)a    → AC-2(3)
    CA-1a1b     → CA-1
    """
    m = _NIST_CORE_RE.match(raw.strip())
    if not m:
        return raw.strip()
    family, num, enh = m.group(1), m.group(2), m.group(3)
    return f"{family}-{int(num)}({int(enh)})" if enh else f"{family}-{int(num)}"


# ── ISO 27001 (STRM OLIR) ─────────────────────────────────────────────────────

def _iso_sheet_names() -> List[str]:
    src = "nist-800-53r5-to-iso-27001-olir"
    path = source_path(src)
    xl = pd.ExcelFile(path)
    return [s for s in xl.sheet_names if "Relationship" in s or s in (
        "AC", "AT", "AU", "CA", "CM", "CP", "IA", "IR", "MA", "MP",
        "PE", "PL", "PM", "PS", "PT", "RA", "SA", "SC", "SI", "SR",
    )]


@lru_cache(maxsize=1)
def load_iso_27001_mapping() -> Dict[str, List[dict]]:
    """
    Load NIST 800-53 r5 → ISO 27001:2022 STRM mapping.
    All per-family sheets are merged.

    Returns dict[nist_id → list of {iso_id, relationship_type, strength, fulfilled_by}]
    """
    src = "nist-800-53r5-to-iso-27001-olir"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"ISO OLIR file not found: {path}")

    nist_col  = col(src, "nist_id")
    iso_col   = col(src, "iso_id")
    rel_col   = col(src, "relationship_type")
    str_col   = col(src, "strength")

    def _opt(role):
        try:
            return col(src, role)
        except KeyError:
            return None

    fulfilled_col = _opt("fulfilled_by")

    result: Dict[str, List[dict]] = {}
    xl = pd.ExcelFile(path)
    sheets = _iso_sheet_names()

    for sn in sheets:
        df = pd.read_excel(xl, sheet_name=sn)
        df.columns = [c.strip().replace("\n", " ") if isinstance(c, str) else c
                      for c in df.columns]

        # Match columns by stripping newlines from both sides
        def _get(row, raw_col):
            for c in df.columns:
                if isinstance(c, str) and raw_col.replace("\n", " ") in c.replace("\n", " "):
                    return str(row.get(c, "")).strip()
            return ""

        for _, row in df.iterrows():
            raw_nist = _get(row, nist_col)
            iso_id   = _get(row, iso_col)
            if not raw_nist or raw_nist == "nan" or not iso_id or iso_id == "nan":
                continue

            # Normalize padded IDs (AC-02 → AC-2, AC-17(01) → AC-17(1))
            nist_id = _normalize_nist_id(raw_nist)

            rel  = _get(row, rel_col)
            strength = _get(row, str_col) if str_col else ""
            fulfilled = (_get(row, fulfilled_col) if fulfilled_col else "")

            # Coerce "nan" strings to empty
            def _clean(v): return "" if v in ("nan", "NaN", "None") else v

            record = {
                "iso_id": iso_id,
                "relationship_type": _clean(rel),
                "strength": _clean(strength),
                "fulfilled_by": _clean(fulfilled),
                "source_sheet": sn,
            }
            result.setdefault(nist_id, []).append(record)

    return result


# ── CMMC / 800-171 ────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_cmmc_mapping() -> Dict[str, List[dict]]:
    """
    Load NIST 800-53 r5 → CMMC / 800-171 crosswalk.

    Returns dict[nist_id → list of {cmmc_practice, nist_171a_objective, relationship_strength}]
    """
    src = "cmmc-800-171-53-crosswalk"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"CMMC crosswalk not found: {path}")

    sn  = sheet_name(src)
    hr  = header_row(src)
    skiprows = list(range(hr)) if hr else None
    df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows)
    df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]

    nist_col   = col(src, "nist_53r5_id")
    cmmc_col   = col(src, "cmmc_practice")
    obj_col    = col(src, "nist_171a_objective")
    str_col    = col(src, "relationship_strength")

    result: Dict[str, List[dict]] = {}
    for _, row in df.iterrows():
        # The NIST column has embedded newlines — normalise
        raw = str(row.get(nist_col, "")).strip()
        if not raw or raw == "nan":
            continue
        nist_ids = [x.strip() for x in raw.split(",") if x.strip()]
        if not nist_ids:
            continue

        record = {
            "cmmc_practice": str(row.get(cmmc_col, "")).strip(),
            "nist_171a_objective": str(row.get(obj_col, "")).strip(),
            "relationship_strength": str(row.get(str_col, "")).strip(),
        }
        for nist_id in nist_ids:
            result.setdefault(nist_id, []).append(record)

    return result


# ── HITRUST ────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_hitrust_mapping() -> Dict[str, List[str]]:
    """
    Load HITRUST CSF v11.4.0 → NIST 800-53 r5 mapping (inverted from the cross-reference).

    The cross-reference sheet is HITRUST-centric (HITRUST ID is col 0, NIST is one of 64 cols).
    This inverts it to nist_id → list[hitrust_id].

    Returns dict[nist_id → list[hitrust_id]]
    """
    src = "hitrust-csf-cross-reference"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"HITRUST cross-reference not found: {path}")

    sn = sheet_name(src)
    hr = header_row(src)
    skiprows = list(range(hr)) if hr else None
    df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows)
    df.columns = [c.strip() if isinstance(c, str) else c for c in df.columns]

    hitrust_col = col(src, "hitrust_id")

    # Prefer r5 column; fall back to any NIST 800-53 column
    nist_col = None
    for candidate in ["NIST SP 800-53 r5", "NIST SP 800-53 R5"]:
        if candidate in df.columns:
            nist_col = candidate
            break
    if nist_col is None:
        for c in df.columns:
            if isinstance(c, str) and "NIST" in c.upper() and "800-53" in c and "r5" in c.lower():
                nist_col = c
                break
    if nist_col is None:
        for c in df.columns:
            if isinstance(c, str) and "NIST" in c.upper() and "800-53" in c:
                nist_col = c
                break
    if nist_col is None:
        raise RuntimeError(f"Cannot find NIST 800-53 r5 column in {path.name}. "
                           f"Available columns: {list(df.columns[:10])}")

    result: Dict[str, List[str]] = {}
    for _, row in df.iterrows():
        hitrust_id = str(row.get(hitrust_col, "")).strip()
        nist_raw   = str(row.get(nist_col, "")).strip()
        if not hitrust_id or hitrust_id == "nan" or not nist_raw or nist_raw == "nan":
            continue
        # Cells have newline-separated IDs; each may have a part suffix (AC-2c, AC-17(4)a)
        raw_ids = [x.strip() for x in re.split(r"[\n;,]+", nist_raw) if x.strip()]
        for raw_id in raw_ids:
            nist_id = _normalize_nist_id(raw_id)
            if nist_id:
                bucket = result.setdefault(nist_id, [])
                if hitrust_id not in bucket:
                    bucket.append(hitrust_id)

    return result
