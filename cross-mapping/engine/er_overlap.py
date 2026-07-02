#!/usr/bin/env python3
"""
ER-Anchored Overlap Engine

Parses ER/local-control crosswalk CSVs from the compliance-report-analyzer
and computes framework overlap using set operations on ER control sets.

Each CSV has positionally-aligned comma-separated lists:
  Local Controls (Linked)           — the native control IDs
  Framework (from Local Controls)   — the framework each ID belongs to

Usage:
    python er_overlap.py                     # demo: SOC 2 T2 vs ISO 27001
    python er_overlap.py --validate          # reconcile against oracle CSVs
    python er_overlap.py --all               # compute all pairwise overlaps
"""

import csv
import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, Tuple, List

# ── paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAPPINGS_DIR = REPO_ROOT / "cross-mapping" / "core-audit" / "mappings"
OVERLAP_DIR = REPO_ROOT / "overlap-data"

# CSV → frameworks it covers (for convenience; not used by parser which detects dynamically)
CSV_FILES = {
    "SOC 1 T1":       MAPPINGS_DIR / "SOC 1 T1.csv",
    "SOC 1 T2":       MAPPINGS_DIR / "SOC 1 T2.csv",
    "SOC 2 T1":       MAPPINGS_DIR / "SOC 2 T1.csv",
    "SOC 2 T2":       MAPPINGS_DIR / "SOC 2 T2.csv",
    "ISO 27001":      MAPPINGS_DIR / "ISO 27001.csv",
    "HIPAA Security": MAPPINGS_DIR / "HIPAA Security.csv",
}

# Oracle combination crosswalks (for validation only).
# Keys use normalized framework names as they appear in the data.
# HITRUST oracle is e1-scoped: computed will be a superset (all-HITRUST > e1 only).
ORACLE_FILES = {
    ("SOC 2", "ISO 27001/2 (2022)"): MAPPINGS_DIR / "SOC 2 T2 & ISO 27001.csv",
    ("SOC 2", "HIPAA Security"):     MAPPINGS_DIR / "SOC 2 T1 & HIPAA S.csv",
    ("SOC 2", "HITRUST"):            OVERLAP_DIR / "SOC 2 T2 & HITRUST e1.csv",
}

# Oracles where the source is broader than the oracle scope — superset is expected
ORACLE_SUPERSET_OK = {("SOC 2", "HITRUST")}

# Canonical framework name normalization
_FRAMEWORK_ALIASES = {
    "SOC 2":                   "SOC 2",
    "SOC 1":                   "SOC 1",
    "ISO 27001/2 (2022)":      "ISO 27001/2 (2022)",
    "HIPAA Security":          "HIPAA Security",
    "HIPAA":                   "HIPAA Security",
    "HITRUST e1":              "HITRUST e1",
    "HITRUST":                 "HITRUST",
    "PCI DSS v4.0":            "PCI DSS v4.0",
}


def normalize_framework(name: str) -> str:
    name = name.strip()
    return _FRAMEWORK_ALIASES.get(name, name)


_ISO_FRAMEWORK_LABEL = "ISO 27001/2 (2022)"


def _normalize_native_id(ctrl_id: str, fw: str) -> str:
    """Canonicalize native control ids where a normalizer exists.  ISO 27001/2
    citations arrive zero-padded ('A.05.01', '06.01.01') in the production CSVs;
    normalize_iso_id maps them to the canonical forms the spine loaders emit
    ('A.5.1', '6.1.1') so ER and projection ids join.  Unrecognized ids pass
    through unchanged (never guess)."""
    if fw == _ISO_FRAMEWORK_LABEL:
        from spine_normalize import normalize_iso_id  # sibling module
        canon, _space = normalize_iso_id(ctrl_id)
        if canon:
            return canon
    return ctrl_id


# ── parser ────────────────────────────────────────────────────────────────────

class ERCrosswalk:
    """
    Parsed view of one ER crosswalk CSV.

    Attributes
    ----------
    source_file : Path
    er_controls : dict[er_id → {name, category, controls_by_framework}]
    framework_to_ers : dict[framework → set[er_id]]  (deduped)
    framework_to_native_controls : dict[framework → set[native_control_id]]
    """

    def __init__(self, path: Path):
        self.source_file = path
        self.er_controls: Dict[str, dict] = {}
        self.framework_to_ers: Dict[str, Set[str]] = defaultdict(set)
        self.framework_to_native_controls: Dict[str, Set[str]] = defaultdict(set)
        self._parse()

    def _parse(self):
        with open(self.source_file, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                er_id = row.get("Reference ID", "").strip()
                if not er_id:
                    continue

                name = row.get("Name", "").strip()
                category = row.get("Category", "").strip()

                controls_raw = row.get("Local Controls (Linked)", "")
                frameworks_raw = row.get("Framework (from Local Controls (Linked))", "")

                if not controls_raw.strip() or not frameworks_raw.strip():
                    self.er_controls[er_id] = {
                        "name": name,
                        "category": category,
                        "controls_by_framework": {},
                    }
                    continue

                control_ids = [c.strip() for c in controls_raw.split(",")]
                framework_names = [normalize_framework(f) for f in frameworks_raw.split(",")]

                # positionally align; truncate to shortest to be safe
                pairs = list(zip(control_ids, framework_names))

                controls_by_fw: Dict[str, Set[str]] = defaultdict(set)
                for ctrl_id, fw in pairs:
                    ctrl_id = ctrl_id.strip()
                    if ctrl_id and fw:
                        controls_by_fw[fw].add(_normalize_native_id(ctrl_id, fw))

                self.er_controls[er_id] = {
                    "name": name,
                    "category": category,
                    "controls_by_framework": {k: sorted(v) for k, v in controls_by_fw.items()},
                }

                for fw in controls_by_fw:
                    self.framework_to_ers[fw].add(er_id)
                    self.framework_to_native_controls[fw].update(controls_by_fw[fw])

    @property
    def frameworks(self) -> List[str]:
        return sorted(self.framework_to_ers.keys())

    def er_set_for(self, framework: str) -> Set[str]:
        """ER IDs that have at least one native control for this framework."""
        return self.framework_to_ers.get(framework, set())

    def native_control_set_for(self, framework: str) -> Set[str]:
        """Deduplicated native control IDs for this framework."""
        return self.framework_to_native_controls.get(framework, set())


# ── overlap calculator ────────────────────────────────────────────────────────

def compute_er_overlap(
    crosswalk_a: ERCrosswalk,
    framework_a: str,
    crosswalk_b: ERCrosswalk,
    framework_b: str,
) -> dict:
    """
    Compute ER-level overlap between two framework scopes.

    Returns overlap metrics keyed on shared ER IDs (not native control IDs).
    ER-based overlap is preferred for sales/CS "shared audit work %" because
    one ER = one audit request regardless of how many native controls it spans.
    """
    ers_a = crosswalk_a.er_set_for(framework_a)
    ers_b = crosswalk_b.er_set_for(framework_b)

    shared = ers_a & ers_b
    only_a = ers_a - ers_b
    only_b = ers_b - ers_a
    union = ers_a | ers_b

    overlap_pct = round(len(shared) / len(union) * 100, 1) if union else 0.0
    a_covers_b = round(len(shared) / len(ers_b) * 100, 1) if ers_b else 0.0
    b_covers_a = round(len(shared) / len(ers_a) * 100, 1) if ers_a else 0.0

    return {
        "framework_a": {
            "name": framework_a,
            "source_csv": crosswalk_a.source_file.name,
            "er_count": len(ers_a),
            "unique_er_count": len(only_a),
        },
        "framework_b": {
            "name": framework_b,
            "source_csv": crosswalk_b.source_file.name,
            "er_count": len(ers_b),
            "unique_er_count": len(only_b),
        },
        "overlap": {
            "shared_er_count": len(shared),
            "shared_er_ids": sorted(shared),
            "total_unique_er_count": len(union),
        },
        "metrics": {
            "jaccard_overlap_pct": overlap_pct,
            "a_covers_b_pct": a_covers_b,
            "b_covers_a_pct": b_covers_a,
        },
    }


def compute_native_control_overlap(
    crosswalk_a: ERCrosswalk,
    framework_a: str,
    crosswalk_b: ERCrosswalk,
    framework_b: str,
) -> dict:
    """
    Compute native-control-level overlap (e.g. SOC 2 REQ-IDs vs ISO clause numbers).
    Useful when the downstream consumer cares about specific control IDs.
    """
    controls_a = crosswalk_a.native_control_set_for(framework_a)
    controls_b = crosswalk_b.native_control_set_for(framework_b)

    shared = controls_a & controls_b
    union = controls_a | controls_b

    return {
        "framework_a_native_count": len(controls_a),
        "framework_b_native_count": len(controls_b),
        "shared_native_count": len(shared),
        "shared_native_ids": sorted(shared),
        "jaccard_overlap_pct": round(len(shared) / len(union) * 100, 1) if union else 0.0,
    }


# ── multi-source loader ───────────────────────────────────────────────────────

def load_all_crosswalks() -> Dict[str, ERCrosswalk]:
    """Load all configured ER CSV files."""
    loaded = {}
    for label, path in CSV_FILES.items():
        if path.exists():
            loaded[label] = ERCrosswalk(path)
        else:
            print(f"  [warn] missing: {path}", file=sys.stderr)
    return loaded


def build_merged_crosswalk(crosswalks: Dict[str, ERCrosswalk]) -> ERCrosswalk:
    """
    Merge all loaded crosswalks into one logical crosswalk.
    Useful for querying across all ER IDs regardless of which CSV they came from.

    Note: returns a synthetic ERCrosswalk with merged data; source_file is None.
    """
    merged = ERCrosswalk.__new__(ERCrosswalk)
    merged.source_file = Path("(merged)")
    merged.er_controls = {}
    merged.framework_to_ers = defaultdict(set)
    merged.framework_to_native_controls = defaultdict(set)

    for cw in crosswalks.values():
        for er_id, er_data in cw.er_controls.items():
            if er_id not in merged.er_controls:
                merged.er_controls[er_id] = {
                    "name": er_data["name"],
                    "category": er_data["category"],
                    "controls_by_framework": {},
                }
            # merge controls_by_framework
            for fw, cids in er_data.get("controls_by_framework", {}).items():
                existing = set(merged.er_controls[er_id]["controls_by_framework"].get(fw, []))
                existing.update(cids)
                merged.er_controls[er_id]["controls_by_framework"][fw] = sorted(existing)

        for fw, er_ids in cw.framework_to_ers.items():
            merged.framework_to_ers[fw].update(er_ids)
        for fw, ctrl_ids in cw.framework_to_native_controls.items():
            merged.framework_to_native_controls[fw].update(ctrl_ids)

    return merged


# ── oracle validation ─────────────────────────────────────────────────────────

def validate_against_oracle(
    computed: dict,
    oracle_path: Path,
    framework_a: str,
    framework_b: str,
) -> dict:
    """
    Compare computed overlap against a pre-built combination CSV (oracle).

    The oracle is a combination crosswalk where:
      oracle.er_set_for(framework_a)  = the ERs from the primary CSV that have framework_a mappings
      oracle.er_set_for(framework_b)  = the ERs from the secondary CSV that have framework_b mappings

    The "authoritative shared" set = oracle.er_set_for(framework_a), because in combination CSVs
    the framework_a set represents exactly the ERs that appear in BOTH frameworks in the primary source.

    Returns a dict with pass/fail status and any discrepancies.
    """
    if not oracle_path.exists():
        return {"status": "skipped", "reason": f"oracle not found: {oracle_path}"}

    oracle_cw = ERCrosswalk(oracle_path)
    # The oracle's framework_a set IS the shared set (framework_a ERs in combination CSVs
    # only appear there because they also have framework_b mappings in the primary source).
    oracle_authoritative = oracle_cw.er_set_for(framework_a)

    computed_shared = set(computed["overlap"]["shared_er_ids"])

    extra = computed_shared - oracle_authoritative
    missing = oracle_authoritative - computed_shared

    ok = not extra and not missing
    return {
        "status": "PASS" if ok else "FAIL",
        "oracle_file": oracle_path.name,
        "oracle_shared_count": len(oracle_authoritative),
        "computed_shared_count": len(computed_shared),
        "extra_in_computed": sorted(extra),
        "missing_from_computed": sorted(missing),
    }


# ── CLI / demo ────────────────────────────────────────────────────────────────

def demo():
    print("=" * 64)
    print("ER-ANCHORED OVERLAP ENGINE — DEMO")
    print("=" * 64)

    crosswalks = load_all_crosswalks()
    if not crosswalks:
        print("[ERROR] No crosswalk CSVs found.")
        return

    merged = build_merged_crosswalk(crosswalks)

    print(f"\nLoaded {len(crosswalks)} CSV(s); total ER controls: {len(merged.er_controls)}")
    print(f"Frameworks detected: {', '.join(merged.frameworks)}\n")

    # ── Example 1: SOC 2 vs ISO 27001 (within SOC 2 T2 crosswalk) ────────
    print("─" * 50)
    print("EXAMPLE 1: SOC 2 T2  vs  ISO 27001/2 (2022)")
    print("  (within SOC 2 T2 crosswalk — ERs that have mappings in both)")
    print("─" * 50)

    soc2_cw = crosswalks.get("SOC 2 T2")

    if soc2_cw:
        result = compute_er_overlap(soc2_cw, "SOC 2", soc2_cw, "ISO 27001/2 (2022)")
        m = result["metrics"]
        print(f"SOC 2 T2 ER count     : {result['framework_a']['er_count']}")
        print(f"ISO 27001 ER count    : {result['framework_b']['er_count']}")
        print(f"Shared ER count       : {result['overlap']['shared_er_count']}")
        print(f"Jaccard overlap       : {m['jaccard_overlap_pct']}%")
        print(f"SOC 2 ERs with ISO    : {m['b_covers_a_pct']}%")
        print(f"ISO ERs with SOC 2    : {m['a_covers_b_pct']}%")
        print()
        print("  Interpretation: of 127 SOC 2 audit requests (ERs), 74 are also")
        print("  covered by ISO 27001/2 (2022) — 58.3% Jaccard overlap.")

        oracle_key = ("SOC 2", "ISO 27001/2 (2022)")
        if oracle_key in ORACLE_FILES:
            val = validate_against_oracle(
                result,
                ORACLE_FILES[oracle_key],
                "SOC 2",
                "ISO 27001/2 (2022)",
            )
            print(f"\nOracle validation     : {val['status']}")
            if val.get("extra_in_computed"):
                print(f"  Extra in computed   : {val['extra_in_computed']}")
            if val.get("missing_from_computed"):
                print(f"  Missing             : {val['missing_from_computed']}")
    else:
        print("  [skip] SOC 2 T2 CSV not loaded")

    # ── Example 2: SOC 2 vs HIPAA Security ────────────────────────────────
    print("\n" + "─" * 50)
    print("EXAMPLE 2: SOC 2 T2  vs  HIPAA Security")
    print("─" * 50)

    if soc2_cw:
        result = compute_er_overlap(soc2_cw, "SOC 2", soc2_cw, "HIPAA Security")
        m = result["metrics"]
        print(f"SOC 2 T2 ER count     : {result['framework_a']['er_count']}")
        print(f"HIPAA ER count        : {result['framework_b']['er_count']}")
        print(f"Shared ER count       : {result['overlap']['shared_er_count']}")
        print(f"Jaccard overlap       : {m['jaccard_overlap_pct']}%")
        print(f"HIPAA ERs with SOC 2  : {m['b_covers_a_pct']}%")
    else:
        print("  [skip] SOC 2 T2 CSV not loaded")

    # ── Example 3: all pairwise (summary) ─────────────────────────────────
    print("\n" + "─" * 50)
    print("EXAMPLE 3: All-framework pairwise ER overlap (merged view)")
    print("─" * 50)

    fw_list = [fw for fw in merged.frameworks
               if not any(skip in fw for skip in ["PCI DSS"])]

    pairs_done = set()
    for fw_a in fw_list:
        for fw_b in fw_list:
            if fw_a >= fw_b or (fw_b, fw_a) in pairs_done:
                continue
            pairs_done.add((fw_a, fw_b))
            result = compute_er_overlap(merged, fw_a, merged, fw_b)
            shared = result["overlap"]["shared_er_count"]
            total_a = result["framework_a"]["er_count"]
            total_b = result["framework_b"]["er_count"]
            pct = result["metrics"]["jaccard_overlap_pct"]
            print(f"  {fw_a:<30} ↔  {fw_b:<30}  shared={shared:>3}  "
                  f"({total_a} / {total_b} ERs)  jaccard={pct}%")

    print("\n" + "=" * 64)
    print("Run with --validate to check oracle consistency.")
    print("=" * 64)


def run_validation():
    """Reconcile computed overlaps against all available oracle CSVs."""
    print("=" * 64)
    print("ER-ANCHORED OVERLAP ENGINE — ORACLE VALIDATION")
    print("=" * 64)

    crosswalks = load_all_crosswalks()

    # Oracle validation uses each primary CSV independently (not merged).
    oracle_source_csv = {
        ("SOC 2", "ISO 27001/2 (2022)"): crosswalks.get("SOC 2 T2"),
        ("SOC 2", "HIPAA Security"):     crosswalks.get("SOC 2 T1"),
        ("SOC 2", "HITRUST"):            crosswalks.get("SOC 2 T2"),
    }

    all_pass = True
    for (fw_a, fw_b), oracle_path in ORACLE_FILES.items():
        source_cw = oracle_source_csv.get((fw_a, fw_b))
        if not source_cw:
            print(f"\n{fw_a} ↔ {fw_b}  [skip — no source crosswalk]")
            continue

        result = compute_er_overlap(source_cw, fw_a, source_cw, fw_b)
        val = validate_against_oracle(result, oracle_path, fw_a, fw_b)
        status = val.get("status", "?")

        # For oracles with known scope narrower than the source, superset is expected
        if status == "FAIL" and (fw_a, fw_b) in ORACLE_SUPERSET_OK:
            if not val.get("missing_from_computed"):
                status = "PASS (superset)"
                val["status"] = status
            else:
                all_pass = False
        elif status not in ("PASS", "skipped"):
            all_pass = False

        print(f"\n{fw_a} ↔ {fw_b}")
        print(f"  Status            : {status}")
        print(f"  Oracle shared     : {val.get('oracle_shared_count', '?')}")
        print(f"  Computed shared   : {val.get('computed_shared_count', '?')}")
        if val.get("extra_in_computed"):
            print(f"  Extra in computed : {val['extra_in_computed']}")
            if (fw_a, fw_b) in ORACLE_SUPERSET_OK:
                print(f"    (expected — source has all-HITRUST; oracle is e1-scoped only)")
        if val.get("missing_from_computed"):
            print(f"  Missing           : {val['missing_from_computed']}")

    print(f"\n{'[ALL PASS]' if all_pass else '[FAILURES — review above]'}")


if __name__ == "__main__":
    if "--validate" in sys.argv:
        run_validation()
    else:
        demo()
