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


# ── NIST CSF 2.0 (direct concept crosswalk) ─────────────────────────────────────

@lru_cache(maxsize=1)
def load_csf2_mapping() -> Dict[str, List[dict]]:
    """
    Load the official NIST CSF 2.0 → 800-53 r5 concept crosswalk (STRM) and
    invert it to NIST-anchored form.

    This is a DIRECT, authoritative mapping (NIST-published), distinct from the
    HITRUST-bridged "NIST CSF" mappings (which are transitive_via_hitrust).

    Returns dict[nist_id → list of {csf2_id, strength}]
    """
    src = "nist-csf2-concept-crosswalk"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"CSF 2.0 crosswalk not found: {path}")

    sn = sheet_name(src)
    hr = header_row(src)
    skiprows = list(range(hr)) if hr else None
    df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows)
    df.columns = [str(c).replace("\n", " ").strip() if isinstance(c, str) else c
                  for c in df.columns]

    csf_col = col(src, "csf2_id")
    nist_col = col(src, "nist_53r5_id")

    def _opt(role):
        try:
            return col(src, role)
        except KeyError:
            return None

    str_col = _opt("strength")

    # Resolve actual column names (manifest names may have had embedded newlines)
    def _resolve(target):
        for c in df.columns:
            if isinstance(c, str) and target.replace("\n", " ").strip().lower() in c.lower():
                return c
        return target

    csf_col = _resolve(csf_col)
    nist_col = _resolve(nist_col)
    str_col = _resolve(str_col) if str_col else None

    result: Dict[str, List[dict]] = {}
    for _, row in df.iterrows():
        csf_id = str(row.get(csf_col, "")).strip()
        nist_raw = str(row.get(nist_col, "")).strip()
        if not csf_id or csf_id == "nan" or not nist_raw or nist_raw == "nan":
            continue
        # CSF subcategory IDs look like GV.OC-01; skip function/category headers (GV, GV.OC)
        if not re.search(r"-\d", csf_id):
            continue
        strength = (str(row.get(str_col, "")).strip()
                    if str_col and pd.notna(row.get(str_col)) else "")
        strength = "" if strength == "nan" else strength

        nist_ids = {_normalize_nist_id(x) for x in re.split(r"[\n;,]+", nist_raw) if x.strip()}
        for nist_id in nist_ids:
            if not nist_id:
                continue
            bucket = result.setdefault(nist_id, [])
            if not any(r["csf2_id"] == csf_id for r in bucket):
                bucket.append({"csf2_id": csf_id, "strength": strength})

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


# ── International standards & legal regulations (via the HITRUST hub) ────────────
#
# HITRUST CSF v11.4 cross-references 64 authoritative sources. We pivot
# NIST 800-53 r5 → HITRUST control → {international standard / legal regulation},
# which lets us deliver GDPR, CCPA, PCI DSS, ISO privacy/AI standards, NIST AI RMF,
# CSF 2.0, and US state privacy laws WITHOUT a separate crosswalk for each.
#
# These are TRANSITIVE mappings (NIST↔HITRUST↔X). They are weaker than a direct
# crosswalk and are always labeled relationship_type="transitive_via_hitrust" and
# mapping_source="…via HITRUST CSF hub" so downstream consumers never mistake a
# bridged inference for an authoritative direct mapping (no-fabrication rule).

# column name in the cross-reference  →  {framework, version, category, jurisdiction}
BRIDGED_FRAMEWORKS = {
    "EU GDPR v2023": {
        "framework": "EU GDPR", "version": "2016/679 (2023 consolidation)",
        "category": "privacy_law", "jurisdiction": "EU"},
    "California Consumer Privacy Act § 1798": {
        "framework": "CCPA/CPRA", "version": "Cal. Civ. Code § 1798",
        "category": "privacy_law", "jurisdiction": "US-CA"},
    "PCI DSS v4.0": {
        "framework": "PCI DSS", "version": "v4.0",
        "category": "security_standard", "jurisdiction": "global"},
    "ISO/IEC 27001:2022": {
        "framework": "ISO/IEC 27001", "version": "2022",
        "category": "security_standard", "jurisdiction": "international"},
    "ISO/IEC 27002:2022": {
        "framework": "ISO/IEC 27002", "version": "2022",
        "category": "security_standard", "jurisdiction": "international"},
    "ISO/IEC 29100:2011": {
        "framework": "ISO/IEC 29100 (Privacy Framework)", "version": "2011",
        "category": "privacy_standard", "jurisdiction": "international"},
    "ISO/IEC 29151:2017 (Annex)": {
        "framework": "ISO/IEC 29151 (PII Protection)", "version": "2017",
        "category": "privacy_standard", "jurisdiction": "international"},
    "ISO/IEC 27799:2016": {
        "framework": "ISO/IEC 27799 (Health Informatics)", "version": "2016",
        "category": "security_standard", "jurisdiction": "international"},
    "ISO/IEC 23894:2023": {
        "framework": "ISO/IEC 23894 (AI Risk Management)", "version": "2023",
        "category": "ai_governance", "jurisdiction": "international"},
    "ISO 31000:2018": {
        "framework": "ISO 31000 (Risk Management)", "version": "2018",
        "category": "risk_management", "jurisdiction": "international"},
    "NIST AI RMF 1.0": {
        "framework": "NIST AI RMF", "version": "1.0",
        "category": "ai_governance", "jurisdiction": "US"},
    "NIST Cybersecurity Framework 2.0": {
        "framework": "NIST CSF", "version": "2.0",
        "category": "security_framework", "jurisdiction": "US"},
    "APEC Cross-Border Privacy Rules (CBPR)": {
        "framework": "APEC CBPR", "version": "current",
        "category": "privacy_framework", "jurisdiction": "APEC"},
    "OECD Privacy Framework": {
        "framework": "OECD Privacy Framework", "version": "2013",
        "category": "privacy_framework", "jurisdiction": "OECD"},
    "Singapore Personal Data Protection Act (2023)": {
        "framework": "Singapore PDPA", "version": "2023",
        "category": "privacy_law", "jurisdiction": "SG"},
    "23 NYCRR 500 (2nd Amendment)": {
        "framework": "NY DFS 23 NYCRR 500", "version": "2nd Amendment",
        "category": "regulation", "jurisdiction": "US-NY"},
    "State of Massachusetts Data Protection Act (201 CMR 17.00) 2024": {
        "framework": "Massachusetts 201 CMR 17.00", "version": "2024",
        "category": "privacy_law", "jurisdiction": "US-MA"},
    "State of Nevada Security and Privacy of Personal Information (NRS 603A)": {
        "framework": "Nevada NRS 603A", "version": "current",
        "category": "privacy_law", "jurisdiction": "US-NV"},
    "HIPAA Privacy Rule": {
        "framework": "HIPAA Privacy Rule", "version": "45 CFR 164 Subpart E",
        "category": "privacy_law", "jurisdiction": "US"},
    "PCI DSS v4.0": {
        "framework": "PCI DSS", "version": "v4.0",
        "category": "security_standard", "jurisdiction": "global"},
}


@lru_cache(maxsize=1)
def load_international_via_hitrust() -> Dict[str, List[dict]]:
    """
    Pivot NIST 800-53 r5 → HITRUST → international standards & legal regulations.

    Returns dict[nist_id → list of {framework, framework_version, control_id,
                 category, jurisdiction, relationship_type, mapping_source, via}]

    Every record is TRANSITIVE (bridged through HITRUST) and labeled as such.
    """
    src = "hitrust-csf-cross-reference"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"HITRUST cross-reference not found: {path}")

    sn = sheet_name(src)
    hr = header_row(src)
    skiprows = list(range(hr)) if hr else None
    df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows)
    df.columns = [str(c).strip() if isinstance(c, str) else c for c in df.columns]

    # Locate the NIST r5 column
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
        raise RuntimeError("Cannot find NIST 800-53 r5 column in HITRUST cross-reference")

    # Which bridged frameworks are actually present as columns
    present = {colname: meta for colname, meta in BRIDGED_FRAMEWORKS.items()
               if colname in df.columns}

    result: Dict[str, List[dict]] = {}
    # nist_id → framework → set(refs) to dedupe across HITRUST rows
    acc: Dict[str, Dict[str, set]] = {}

    for _, row in df.iterrows():
        nist_raw = str(row.get(nist_col, "")).strip()
        if not nist_raw or nist_raw == "nan":
            continue
        nist_ids = {_normalize_nist_id(x) for x in re.split(r"[\n;,]+", nist_raw) if x.strip()}
        nist_ids = {n for n in nist_ids if n}
        if not nist_ids:
            continue

        for colname, meta in present.items():
            cell = str(row.get(colname, "")).strip()
            if not cell or cell == "nan":
                continue
            refs = [x.strip() for x in re.split(r"[\n;]+", cell) if x.strip()]
            for nist_id in nist_ids:
                fw_acc = acc.setdefault(nist_id, {}).setdefault(meta["framework"], set())
                fw_acc.update(refs)

    # Materialize accumulated refs into mapping records
    for nist_id, fw_map in acc.items():
        for colname, meta in present.items():
            fw = meta["framework"]
            refs = fw_map.get(fw)
            if not refs:
                continue
            for ref in sorted(refs):
                result.setdefault(nist_id, []).append({
                    "framework": fw,
                    "framework_version": meta["version"],
                    "control_id": ref,
                    "category": meta["category"],
                    "jurisdiction": meta["jurisdiction"],
                    "relationship_type": "transitive_via_hitrust",
                    "mapping_source": "HITRUST CSF v11.4 Cross-Reference (bridged via HITRUST hub)",
                    "via": "HITRUST CSF",
                })

    return result


# ── CUI overlay (NIST 800-53r5 + 800-171r3) ──────────────────────────────────

@lru_cache(maxsize=1)
def load_cui_overlay() -> Dict[str, dict]:
    """
    Load the CUI tailoring overlay.

    Each NIST control gets a tailoring decision (CUI/NCO/FED/ORC) and an
    optional SP 800-171 Rev 3 cross-reference.

    Returns dict[nist_id → {tailoring: "CUI"|..., nist_171r3_ref: "03.15.01"|""}]
    """
    src = "nist-800-53-cui-overlay"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"CUI overlay not found: {path}")

    sn = sheet_name(src)
    hr = header_row(src)
    skiprows = list(range(hr)) if hr else None
    df = pd.read_excel(path, sheet_name=sn, skiprows=skiprows)
    df.columns = [str(c).strip() if isinstance(c, str) else c for c in df.columns]

    sort_col = "Unique Sort ID (800-53r5)"
    tail_col = "Tailoring Decision"
    ref_171_col = "SP 800-171 Rev 3 Security Requirement"

    result: Dict[str, dict] = {}
    for _, row in df.iterrows():
        sort_id = str(row.get(sort_col, "")).strip()
        if not sort_id or sort_id == "nan":
            continue

        parts = sort_id.split("-")
        if len(parts) < 3:
            continue
        family = parts[0]
        base_num = parts[1].lstrip("0") or "0"
        enh_num = parts[2].lstrip("0") if len(parts) > 2 else ""

        if len(parts) >= 4 and parts[3] != "00":
            continue

        nist_id = f"{family}-{base_num}"
        if enh_num and enh_num != "00":
            nist_id = f"{nist_id}({enh_num})"

        tailoring = str(row.get(tail_col, "")).strip()
        ref_171 = str(row.get(ref_171_col, "")).strip()
        if ref_171 == "nan":
            ref_171 = ""
        if ref_171:
            m = re.match(r"([\d.]+)", ref_171)
            ref_171 = m.group(1) if m else ""

        if nist_id not in result:
            result[nist_id] = {
                "tailoring": tailoring,
                "nist_171r3_ref": ref_171,
            }

    return result


# ── SP 800-213A (IoT Federal Profile) ──────────────────────────────────────────

@lru_cache(maxsize=1)
def load_iot_mapping() -> Dict[str, List[str]]:
    """
    Load NIST 800-53 r5 → SP 800-213A IoT Federal Profile mapping.

    Returns dict[nist_id → list of IoT technical capability references]
    (e.g. ["DO:SMP(5e)", "DO:SMP(5f)", ...])
    """
    src = "nist-800-53-to-sp800-213a"
    path = source_path(src)
    if not path.exists():
        raise FileNotFoundError(f"SP 800-213A mapping not found: {path}")

    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]

    result: Dict[str, List[str]] = {}
    for _, row in df.iterrows():
        nist_raw = str(row.get("References", "")).strip()
        iot_raw = str(row.get("SP 800-213A", "")).strip()
        if not nist_raw or nist_raw == "nan" or not iot_raw or iot_raw == "nan":
            continue
        nist_id = _normalize_nist_id(nist_raw)
        if not nist_id or not re.match(r"^[A-Z]{2,3}-\d+", nist_id):
            continue
        refs = [x.strip() for x in re.split(r",\s*", iot_raw) if x.strip()]
        if refs:
            result[nist_id] = refs

    return result
