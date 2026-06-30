"""
Config loader — reads source_manifest.json for all column/sheet references.
All other ingestion modules must import column names from here.
Never hardcode column names in loader code.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "canonical-sources" / "source_manifest.json"
SOURCE_DATA_DIR = REPO_ROOT / "canonical-sources" / "source_data"


def _load_manifest() -> dict:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_source(source_id: str) -> dict:
    """Return the manifest entry for a given source id."""
    manifest = _load_manifest()
    for entry in manifest.get("sources", []):
        if entry.get("id") == source_id:
            return entry
    raise KeyError(f"Source id not found in manifest: {source_id!r}")


def col(source_id: str, role: str) -> str:
    """Return the actual column name for a semantic role in the given source."""
    entry = get_source(source_id)
    col_roles = entry.get("column_roles", {})
    for col_name, col_role in col_roles.items():
        if col_role == role:
            return col_name
    raise KeyError(f"Role {role!r} not found in source {source_id!r}. "
                   f"Available roles: {list(col_roles.values())}")


def source_path(source_id: str) -> Path:
    """Return the resolved filesystem path for a source."""
    entry = get_source(source_id)
    rel = entry.get("file", "")
    if rel.startswith("canonical-sources/source_data/"):
        fname = rel.split("canonical-sources/source_data/")[-1]
        return SOURCE_DATA_DIR / fname
    return REPO_ROOT / rel


def header_row(source_id: str) -> int:
    """Return the header_row index (0-based) for a source."""
    entry = get_source(source_id)
    return entry.get("header_row", 0)


def sheet_name(source_id: str) -> str:
    """Return the primary sheet name for a source."""
    entry = get_source(source_id)
    return entry.get("sheet", "")
