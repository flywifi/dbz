#!/usr/bin/env python3
"""
stig_harvest.py — DISA STIG/SRG rule→CCI harvester (technology/application tier).

STIG rules cite CCIs (`<ident system="http://cyber.mil/cci">`), which makes each
STIG a per-product implementation footprint over the 800-53 spine via cci_bridge.
This tool distills the multi-hundred-MB DISA SRG-STIG Library compilation (never
committed) into two small deterministic artifacts under
`canonical-sources/source_data/stig/`:

  stig_cci_map.json.gz   per-benchmark rules with severity, STIG version id, and
                         validated CCI citations (the loader input)
  stig_catalog.json      harvested-benchmark ledger (version/release/date/
                         rule_count/content sha) + full registry snapshot of the
                         cyber.trackr.live title catalog (the delta detector)

Modes
  --catalog                refresh the registry section from the trackr API (1 call)
  --full --from-zip PATH   distill a downloaded SRG-STIG Library compilation zip
                           (per-STIG zips of XCCDF 1.1 benchmarks) into both artifacts
  --check                  compare the live trackr catalog against the committed
                           artifacts; print per-title drift lines (offline-safe)
  --delta                  re-harvest ONLY changed/new titles via the trackr API
                           (rate-limited per-rule calls); large drifts are referred
                           to --full with a fresh library zip instead
  --via-trackr --titles T  targeted per-title harvest through the trackr API
                           (backfill for titles absent from the current library)

Acceptance/precedence: DISA compilation (primary) > trackr mirror (fallback) >
community aggregations (watch-only, never loader inputs). Malformed CCI tokens are
counted and refused, never guessed. All output is sorted; the gzip member is
written with mtime=0 so byte-identical inputs give byte-identical artifacts.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STIG_DIR = ROOT / "canonical-sources" / "source_data" / "stig"
MAP_PATH = STIG_DIR / "stig_cci_map.json.gz"
CATALOG_PATH = STIG_DIR / "stig_catalog.json"

TOOL_VERSION = "1.0.0"
TRACKR_BASE = "https://cyber.trackr.live/api"
# DISA publishes the compilation quarterly at dl.dod.cyber.mil with a
# month-name pattern; probe recent quarters newest-first.
COMPILATION_URL_PATTERN = (
    "https://dl.dod.cyber.mil/wp-content/uploads/stigs/zip/"
    "U_SRG-STIG_Library_{month}_{year}.zip"
)
_QUARTER_MONTHS = ("October", "July", "April", "January")

CCI_RE = re.compile(r"^CCI-\d{6}$")
_RELEASE_RE = re.compile(r"Release:\s*([\w.]+)\s+Benchmark Date:\s*(.+?)\s*$")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
_TRACKR_RATE_S = 0.35  # ~3 requests/second


# ── helpers ──────────────────────────────────────────────────────────────────

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _http_json(url: str, timeout: int = 90):
    req = urllib.request.Request(url, headers={"User-Agent": "dbz-stig-harvest/" + TOOL_VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _iso_date(raw: str) -> str:
    """'01 Apr 2026' -> '2026-04-01'; unparseable stays raw (never guessed)."""
    parts = raw.strip().split()
    if len(parts) == 3 and parts[1][:3] in _MONTHS:
        try:
            return f"{int(parts[2]):04d}-{_MONTHS[parts[1][:3]]:02d}-{int(parts[0]):02d}"
        except ValueError:
            pass
    return raw.strip()


def _norm_title(s: str) -> str:
    """Normalization used to match XCCDF benchmark ids to trackr catalog keys.
    SRG-aware: 'Security Requirements Guide' canonicalizes to a kept 'srg' token
    (so a product's SRG never collides with its STIG), while STIG markers are
    dropped (benchmark ids carry `_STIG`, trackr keys usually do not)."""
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    s = s.replace("securityrequirementsguide", "srg")
    s = s.replace("securitytechnicalimplementationguide", "")
    for suf in ("manualstig", "benchmark", "stig"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s


def _vr_key(version: str, release: str):
    """Orderable (version, release) key; numeric when possible (floats cover
    interim releases like '0.1'), non-numeric tokens sort BELOW numeric ones —
    version ordering for those formats is decided by dates, never guessed."""
    def _one(x):
        try:
            return (1, float(str(x)), "")
        except (TypeError, ValueError):
            return (0, 0.0, str(x))
    return (_one(version), _one(release))


def _trackr_norm_map(registry: dict) -> dict:
    """normalized-title -> trackr key; near-duplicate catalog keys that normalize
    identically resolve to the entry with the newest (date, version, release)."""
    out: dict[str, str] = {}
    for k in sorted(registry):
        n = _norm_title(k)
        if n in out:
            a, b = registry[out[n]], registry[k]
            if (str(a.get("date") or ""), _vr_key(a["version"], a["release"])) >= \
               (str(b.get("date") or ""), _vr_key(b["version"], b["release"])):
                continue
        out[n] = k
    return out


def _bench_sha(rules: list[dict]) -> str:
    return hashlib.sha256(
        json.dumps(rules, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def _write_map(benchmarks: dict, meta: dict) -> None:
    """The gz map is a pure function of its inputs (library zip + registry):
    volatile fields (retrieved_at) stay out so byte-identity across re-runs is
    the determinism check. Retrieval provenance lives in stig_catalog.json."""
    STIG_DIR.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in meta.items() if k != "retrieved_at"}
    payload = {"_meta": meta, "benchmarks": {k: benchmarks[k] for k in sorted(benchmarks)}}
    raw = json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        gz.write(raw)
    MAP_PATH.write_bytes(buf.getvalue())


def read_map() -> dict:
    with gzip.open(MAP_PATH, "rt", encoding="utf-8") as f:
        return json.load(f)


def _write_catalog(cat: dict) -> None:
    STIG_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(
        json.dumps(cat, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")


def read_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _catalog_from(benchmarks: dict, registry: dict, meta: dict) -> dict:
    harvested = {}
    for bid, b in benchmarks.items():
        harvested[bid] = {
            "title": b["title"],
            "version": b["version"],
            "release": b["release"],
            "benchmark_date": b["benchmark_date"],
            "type": b["type"],
            "source": b["source"],
            "trackr_title": b.get("trackr_title"),
            "rule_count": len(b["rules"]),
            "cci_citations": sum(len(r["ccis"]) for r in b["rules"]),
            "distinct_ccis": len({c for r in b["rules"] for c in r["ccis"]}),
            "sha16": _bench_sha(b["rules"]),
        }
    return {"_meta": meta,
            "harvested": {k: harvested[k] for k in sorted(harvested)},
            "registry": {k: registry[k] for k in sorted(registry)}}


# ── trackr registry ──────────────────────────────────────────────────────────

def fetch_registry() -> dict:
    """Latest entry per title from the trackr STIG catalog (1 API call)."""
    raw = _http_json(f"{TRACKR_BASE}/stig")
    registry = {}
    for title, versions in raw.items():
        if not isinstance(versions, list) or not versions:
            continue
        # newest first by benchmark date, then numeric version/release
        def _key(v):
            def _num(x):
                try:
                    return (0, float(str(x)))
                except (TypeError, ValueError):
                    return (1, 0.0)
            return (str(v.get("date") or ""), _num(v.get("version")), _num(v.get("release")))
        latest = sorted(versions, key=_key)[-1]
        registry[title] = {
            "date": latest.get("date"),
            "version": str(latest.get("version") or ""),
            "release": str(latest.get("release") or ""),
            "n_versions": len(versions),
            "sev": latest.get("sev") or {},
        }
    return registry


# ── XCCDF distillation ───────────────────────────────────────────────────────

def parse_xccdf(data: bytes, source_zip: str, stats: dict) -> dict | None:
    """One XCCDF 1.1 benchmark -> distilled dict, or None if not a benchmark."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        stats["xml_parse_errors"] += 1
        return None
    if _local(root.tag) != "Benchmark":
        return None
    bid = root.get("id") or ""
    title = version = ""
    release = benchmark_date = ""
    rules: list[dict] = []
    for child in root:
        lc = _local(child.tag)
        if lc == "title":
            title = (child.text or "").strip()
        elif lc == "version":
            version = (child.text or "").strip()
        elif lc == "plain-text" and child.get("id") == "release-info":
            m = _RELEASE_RE.search(child.text or "")
            if m:
                release, benchmark_date = m.group(1), _iso_date(m.group(2))
        elif lc == "Group":
            gid = child.get("id") or ""
            for rule in child:
                if _local(rule.tag) != "Rule":
                    continue
                ccis = []
                version_id = rtitle = ""
                for el in rule:
                    rl = _local(el.tag)
                    if rl == "version":
                        version_id = (el.text or "").strip()
                    elif rl == "title":
                        rtitle = (el.text or "").strip()
                    elif rl == "ident" and "cci" in (el.get("system") or "").lower():
                        tok = (el.text or "").strip()
                        if CCI_RE.match(tok):
                            ccis.append(tok)
                        else:
                            stats["malformed_cci_citations"] += 1
                rules.append({
                    "group": gid,
                    "rule": rule.get("id") or "",
                    "version_id": version_id,
                    "severity": rule.get("severity") or "",
                    "title": rtitle,
                    "ccis": sorted(set(ccis)),
                })
    if not bid or not rules:
        stats["benchmarks_without_rules"] += 1
        return None
    rules.sort(key=lambda r: (r["group"], r["rule"]))
    kind = "srg" if ("SRG" in bid or "Security Requirements Guide" in title) else "stig"
    return {"benchmark_id": bid, "title": title, "version": version,
            "release": release, "benchmark_date": benchmark_date,
            "type": kind, "source": "disa_compilation",
            "source_zip": source_zip, "rules": rules}


def distill_library(zip_path: Path, registry: dict) -> tuple[dict, dict]:
    """Walk the compilation zip -> {benchmark_id: distilled}, stats."""
    stats = {"member_zips": 0, "xccdf_files": 0, "benchmarks": 0,
             "rules": 0, "cci_citations": 0, "malformed_cci_citations": 0,
             "xml_parse_errors": 0, "benchmarks_without_rules": 0,
             "duplicate_benchmark_ids": 0, "trackr_matched": 0}
    trackr_norm = _trackr_norm_map(registry)
    benchmarks: dict[str, dict] = {}
    with zipfile.ZipFile(zip_path) as z:
        for name in sorted(z.namelist()):
            if not name.lower().endswith(".zip"):
                continue
            stats["member_zips"] += 1
            with z.open(name) as f:
                try:
                    inner = zipfile.ZipFile(io.BytesIO(f.read()))
                except zipfile.BadZipFile:
                    continue
            for member in sorted(inner.namelist()):
                low = member.lower()
                if not (low.endswith("-xccdf.xml") or low.endswith("_xccdf.xml")):
                    continue
                stats["xccdf_files"] += 1
                bench = parse_xccdf(inner.read(member), Path(name).name, stats)
                if bench is None:
                    continue
                bid = bench.pop("benchmark_id")
                if bid in benchmarks:
                    stats["duplicate_benchmark_ids"] += 1
                    # keep the lexically-later (version, release) — deterministic
                    old = benchmarks[bid]
                    if (bench["version"], bench["release"]) <= (old["version"], old["release"]):
                        continue
                title = bench["title"]
                candidates = (bid, title,
                              title.replace("Security Technical Implementation Guide", ""),
                              title.replace("Security Requirements Guide", ""))
                tk = next((trackr_norm[c] for c in map(_norm_title, candidates)
                           if c in trackr_norm), None)
                bench["trackr_title"] = tk
                benchmarks[bid] = bench
    for b in benchmarks.values():
        stats["benchmarks"] += 1
        stats["rules"] += len(b["rules"])
        stats["cci_citations"] += sum(len(r["ccis"]) for r in b["rules"])
        if b.get("trackr_title"):
            stats["trackr_matched"] += 1
    return benchmarks, stats


# ── trackr per-title harvest (fallback / delta path) ────────────────────────

def harvest_title_via_trackr(title: str, ver: str, rel: str) -> dict | None:
    """One title through the trackr API: rule list + per-rule detail calls."""
    listing = _http_json(f"{TRACKR_BASE}/stig/{title}/{ver}/{rel}")
    reqs = listing.get("requirements") or {}
    rules = []
    for vid in sorted(reqs):
        time.sleep(_TRACKR_RATE_S)
        det = _http_json(f"{TRACKR_BASE}/stig/{title}/{ver}/{rel}/{vid}")
        ccis = sorted({t for t in (det.get("identifiers") or []) if CCI_RE.match(t)})
        rules.append({
            "group": det.get("id") or vid,
            "rule": det.get("rule") or "",
            "version_id": det.get("version") or "",
            "severity": det.get("severity") or "",
            "title": det.get("requirement-title") or "",
            "ccis": ccis,
        })
    if not rules:
        return None
    rules.sort(key=lambda r: (r["group"], r["rule"]))
    bid = listing.get("id") or title
    btitle = listing.get("title") or title
    kind = "srg" if ("SRG" in bid or "Security Requirements Guide" in btitle) else "stig"
    published = str(listing.get("published") or "")
    return {"title": btitle, "version": str(ver), "release": str(rel),
            "benchmark_date": published[:10] if published else "",
            "type": kind, "source": "trackr", "source_zip": None,
            "trackr_title": title, "rules": rules}


# ── drift comparison ─────────────────────────────────────────────────────────

def compute_drift(live: dict, committed_cat: dict) -> dict:
    reg = committed_cat.get("registry", {})
    harvested = committed_cat.get("harvested", {})
    by_trackr = {h["trackr_title"]: (bid, h) for bid, h in harvested.items()
                 if h.get("trackr_title")}
    new_titles = sorted(set(live) - set(reg))
    removed_titles = sorted(set(reg) - set(live))
    changed = []
    stale_harvested = []
    mirror_lag = []
    for t in sorted(set(live) & set(reg)):
        lv, rv = live[t], reg[t]
        if (lv["date"], lv["version"], lv["release"]) != (rv["date"], rv["version"], rv["release"]):
            changed.append({"title": t,
                            "registry": f'v{rv["version"]}r{rv["release"]} {rv["date"]}',
                            "live": f'v{lv["version"]}r{lv["release"]} {lv["date"]}'})
        if t in by_trackr:
            bid, h = by_trackr[t]
            entry = {"benchmark_id": bid, "title": t,
                     "harvested": f'v{h["version"]}r{h["release"]}',
                     "live": f'v{lv["version"]}r{lv["release"]}'}
            # identical (version, release) tokens = same release (trackr's date
            # field differs by days from the XCCDF benchmark date — metadata
            # noise, never drift). Numeric tokens order numerically; date-coded
            # formats (e.g. Y26M04) fall back to date ordering.
            if (str(h["version"]), str(h["release"])) == (str(lv["version"]), str(lv["release"])):
                continue
            hk, lk = _vr_key(h["version"], h["release"]), _vr_key(lv["version"], lv["release"])
            if all(part[0] == 1 for pair in (hk, lk) for part in pair):
                live_newer, live_older = lk > hk, lk < hk
            else:
                hd, ld = str(h.get("benchmark_date") or ""), str(lv.get("date") or "")
                live_newer, live_older = ld > hd, ld < hd
            if live_newer:
                stale_harvested.append(entry)
            elif live_older:
                # harvested (DISA-primary) is ahead of the mirror — informational,
                # never a re-harvest trigger (precedence: DISA > trackr)
                mirror_lag.append(entry)
    return {"new_titles": new_titles, "removed_titles": removed_titles,
            "changed_titles": changed, "stale_harvested": stale_harvested,
            "mirror_lag": mirror_lag}


# ── modes ────────────────────────────────────────────────────────────────────

def _meta(source: str, extra: dict | None = None) -> dict:
    from datetime import datetime, timezone
    m = {"tool": "stig_harvest.py", "tool_version": TOOL_VERSION,
         "source": source,
         "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if extra:
        m.update(extra)
    return m


def mode_catalog(args) -> int:
    registry = fetch_registry()
    if CATALOG_PATH.exists():
        cat = read_catalog()
    else:
        cat = {"_meta": {}, "harvested": {}, "registry": {}}
    cat["registry"] = {k: registry[k] for k in sorted(registry)}
    cat["_meta"] = _meta(cat.get("_meta", {}).get("source", "trackr"),
                         {"registry_titles": len(registry),
                          "library": cat.get("_meta", {}).get("library")})
    _write_catalog(cat)
    print(f"[catalog] {len(registry)} titles -> {CATALOG_PATH.relative_to(ROOT)}")
    return 0


def mode_full(args) -> int:
    zip_path = Path(args.from_zip) if args.from_zip else None
    if not zip_path or not zip_path.exists():
        print("[full] --from-zip PATH is required (download the current SRG-STIG "
              "Library compilation first; see feed disa-stig-library). Probe pattern:")
        print("       " + COMPILATION_URL_PATTERN.format(month="<Month>", year="<YYYY>")
              + f"  months={_QUARTER_MONTHS}")
        return 1
    try:
        registry = fetch_registry()
        reg_note = f"{len(registry)} titles"
    except Exception as e:  # offline distill still works; registry kept if present
        registry = read_catalog().get("registry", {}) if CATALOG_PATH.exists() else {}
        reg_note = f"trackr unreachable ({type(e).__name__}); kept committed registry ({len(registry)})"
    print(f"[full] registry: {reg_note}")
    print(f"[full] distilling {zip_path.name} …")
    benchmarks, stats = distill_library(zip_path, registry)
    if not benchmarks:
        print("[full] no benchmarks distilled — refusing to overwrite artifacts")
        return 1
    library = args.library or zip_path.stem
    meta = _meta("disa_compilation", {"library": library, "stats": stats})
    _write_map(benchmarks, meta)
    _write_catalog(_catalog_from(benchmarks, registry, meta))
    print(f"[full] {stats}")
    print(f"[full] wrote {MAP_PATH.relative_to(ROOT)} "
          f"({MAP_PATH.stat().st_size // 1024} KB) + {CATALOG_PATH.relative_to(ROOT)}")
    return 0


def mode_check(args) -> int:
    if not CATALOG_PATH.exists():
        print("[check] no committed stig_catalog.json — run --full first")
        return 0
    cat = read_catalog()
    try:
        live = fetch_registry()
    except Exception as e:  # offline-safe: the report is the deliverable
        print(f"[check] trackr unreachable ({type(e).__name__}: {e}) — check_failed")
        if args.json:
            print(json.dumps({"status": "check_failed"}))
        return 0
    drift = compute_drift(live, cat)
    n = sum(len(v) for k, v in drift.items() if k != "mirror_lag")
    if args.json:
        print(json.dumps({"status": "drift" if n else "current", **drift},
                         indent=1, sort_keys=True))
    else:
        print(f"[check] registry {len(cat.get('registry', {}))} committed vs {len(live)} live; "
              f"harvested {len(cat.get('harvested', {}))}")
        for kind in ("new_titles", "removed_titles"):
            for t in drift[kind][:20]:
                print(f"  {kind[:-7]}: {t}")
            if len(drift[kind]) > 20:
                print(f"  … +{len(drift[kind]) - 20} more {kind}")
        for c in drift["changed_titles"][:40]:
            print(f"  changed: {c['title']}  {c['registry']} -> {c['live']}")
        if len(drift["changed_titles"]) > 40:
            print(f"  … +{len(drift['changed_titles']) - 40} more changed")
        for s in drift["stale_harvested"][:40]:
            print(f"  stale-harvest: {s['benchmark_id']}  {s['harvested']} -> {s['live']}")
        if drift["mirror_lag"]:
            print(f"  (mirror lag: {len(drift['mirror_lag'])} harvested benchmarks are "
                  "NEWER than the trackr mirror — informational, DISA is primary)")
        print(f"[check] {'CURRENT — no drift' if n == 0 else f'{n} drift signals'}")
    return 0


def _merge_and_rewrite(new_benchmarks: dict, registry: dict, source: str) -> None:
    data = read_map()
    benchmarks = data["benchmarks"]
    benchmarks.update(new_benchmarks)
    meta = _meta(source, {"library": data.get("_meta", {}).get("library"),
                          "merged_titles": sorted(new_benchmarks)})
    _write_map(benchmarks, meta)
    _write_catalog(_catalog_from(benchmarks, registry, meta))


def mode_delta(args) -> int:
    if not (CATALOG_PATH.exists() and MAP_PATH.exists()):
        print("[delta] committed artifacts missing — run --full first")
        return 1
    cat = read_catalog()
    live = fetch_registry()
    drift = compute_drift(live, cat)
    stale = drift["stale_harvested"]
    if not stale:
        # registry-only drift (new/removed/changed unharvested titles) still gets recorded
        cat["registry"] = {k: live[k] for k in sorted(live)}
        _write_catalog(cat)
        print(f"[delta] no harvested benchmark is stale; registry refreshed "
              f"({len(drift['changed_titles'])} changed / {len(drift['new_titles'])} new titles noted)")
        return 0
    if len(stale) > args.max_delta:
        print(f"[delta] {len(stale)} stale benchmarks > --max-delta {args.max_delta}: "
              "quarterly-scale drift — download the new library compilation and run --full")
        return 0
    harvested_new = {}
    for s in stale:
        t = s["title"]
        lv = live[t]
        print(f"[delta] re-harvesting {t} v{lv['version']}r{lv['release']} via trackr …")
        bench = harvest_title_via_trackr(t, lv["version"], lv["release"])
        if bench is None:
            print(f"[delta]   {t}: no rules returned — kept committed version")
            continue
        harvested_new[s["benchmark_id"]] = bench
    if harvested_new:
        _merge_and_rewrite(harvested_new, live, "disa_compilation+trackr_delta")
        print(f"[delta] merged {len(harvested_new)} benchmarks; artifacts rewritten")
    return 0


def _fetch_disa_title_zip(old_zip_name: str, old_v: str, old_r: str,
                          new_v: str, new_r: str) -> bytes | None:
    """DISA posts updated individual STIG zips between quarterly compilations at
    the same URL layout as the library members. Rewrite the recorded member zip
    name's V{v}R{r} token to the live version and probe; None on any miss."""
    m = re.search(r"V\d+R\d+", old_zip_name)
    if not m:
        return None
    new_name = old_zip_name[: m.start()] + f"V{new_v}R{new_r}" + old_zip_name[m.end():]
    url = "https://dl.dod.cyber.mil/wp-content/uploads/stigs/zip/" + new_name
    req = urllib.request.Request(url, headers={"User-Agent": "dbz-stig-harvest/" + TOOL_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except Exception:
        return None


def mode_refresh_stale(args) -> int:
    """Bring stale harvested benchmarks current: per-title DISA zip first
    (authoritative, one small download), trackr per-rule crawl as fallback."""
    if not (CATALOG_PATH.exists() and MAP_PATH.exists()):
        print("[refresh-stale] committed artifacts missing — run --full first")
        return 1
    cat = read_catalog()
    live = fetch_registry()
    stale = compute_drift(live, cat)["stale_harvested"]
    if not stale:
        print("[refresh-stale] nothing stale")
        return 0
    if len(stale) > args.max_delta:
        print(f"[refresh-stale] {len(stale)} stale > --max-delta {args.max_delta} — "
              "refusing; raise --max-delta or run --full with a new library zip")
        return 1
    data = read_map()
    harvested_new: dict[str, dict] = {}
    stats = {"disa_zip": 0, "trackr": 0, "failed": 0,
             "malformed_cci_citations": 0, "xml_parse_errors": 0,
             "benchmarks_without_rules": 0}
    for s in stale:
        t, bid = s["title"], s["benchmark_id"]
        lv = live[t]
        old = data["benchmarks"].get(bid, {})
        blob = _fetch_disa_title_zip(old.get("source_zip") or "",
                                     old.get("version", ""), old.get("release", ""),
                                     lv["version"], lv["release"])
        bench = None
        if blob:
            try:
                inner = zipfile.ZipFile(io.BytesIO(blob))
                for member in sorted(inner.namelist()):
                    if member.lower().endswith(("-xccdf.xml", "_xccdf.xml")):
                        parsed = parse_xccdf(inner.read(member), Path(member).name, stats)
                        if parsed and parsed["benchmark_id"] == bid:
                            bench = parsed
                            bench.pop("benchmark_id")
                            bench["trackr_title"] = t
                            break
            except zipfile.BadZipFile:
                bench = None
        if bench:
            stats["disa_zip"] += 1
            print(f"[refresh-stale] {bid}: {s['harvested']} -> {s['live']} (DISA zip)")
        else:
            try:
                bench = harvest_title_via_trackr(t, lv["version"], lv["release"])
            except Exception as e:
                print(f"[refresh-stale] {bid}: FAILED ({type(e).__name__}) — kept committed")
                stats["failed"] += 1
                continue
            if bench is None:
                stats["failed"] += 1
                print(f"[refresh-stale] {bid}: no rules via trackr — kept committed")
                continue
            stats["trackr"] += 1
            print(f"[refresh-stale] {bid}: {s['harvested']} -> {s['live']} (trackr)")
        harvested_new[bid] = bench
    if harvested_new:
        _merge_and_rewrite(harvested_new, live, "disa_compilation+title_refresh")
    print(f"[refresh-stale] {stats}")
    return 0 if stats["failed"] == 0 else 1


def _bid_for_trackr_title(t: str) -> str:
    if t.endswith(("_STIG", "_SRG")):
        return t
    kind = "SRG" if ("Security_Requirements_Guide" in t or t.endswith("SRG")) else "STIG"
    return f"{t}_{kind}"


def mode_via_trackr(args) -> int:
    titles = []
    if args.titles_file:
        titles += [x.strip() for x in Path(args.titles_file).read_text().splitlines() if x.strip()]
    if args.titles:
        titles += [x.strip() for x in args.titles.split(",") if x.strip()]
    if not titles:
        print("[via-trackr] --titles T1,T2 or --titles-file PATH required")
        return 1
    live = fetch_registry()
    harvested_new: dict[str, dict] = {}
    done = 0
    flushed = 0
    for i, t in enumerate(titles, 1):
        if t not in live:
            print(f"[via-trackr] {t}: not in trackr catalog — skipped")
            continue
        lv = live[t]
        print(f"[via-trackr] ({i}/{len(titles)}) {t} v{lv['version']}r{lv['release']} …")
        try:
            bench = harvest_title_via_trackr(t, lv["version"], lv["release"])
        except Exception as e:  # transient mirror errors: skip, never crash the crawl
            print(f"[via-trackr]   {t}: {type(e).__name__} — skipped")
            continue
        if bench is None:
            print(f"[via-trackr]   {t}: no rules — skipped")
            continue
        harvested_new[_bid_for_trackr_title(t)] = bench
        done += 1
        # incremental flush so a mid-crawl failure preserves progress
        if done - flushed >= args.flush_every:
            _flush_backfill(harvested_new, live)
            flushed = done
            print(f"[via-trackr]   … checkpoint: {done} benchmarks merged")
    if not harvested_new:
        return 1
    _flush_backfill(harvested_new, live)
    print(f"[via-trackr] merged {len(harvested_new)} benchmarks")
    return 0


def _flush_backfill(harvested_new: dict, live: dict) -> None:
    if MAP_PATH.exists():
        _merge_and_rewrite(harvested_new, live, "disa_compilation+trackr_backfill")
    else:
        meta = _meta("trackr", {"library": None})
        _write_map(harvested_new, meta)
        _write_catalog(_catalog_from(harvested_new, live, meta))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", action="store_true", help="refresh registry from trackr")
    ap.add_argument("--full", action="store_true", help="distill a library compilation zip")
    ap.add_argument("--check", action="store_true", help="drift report vs live trackr catalog")
    ap.add_argument("--delta", action="store_true", help="re-harvest only stale titles via trackr")
    ap.add_argument("--refresh-stale", action="store_true", dest="refresh_stale",
                    help="re-harvest stale benchmarks (per-title DISA zip, trackr fallback)")
    ap.add_argument("--via-trackr", action="store_true", dest="via_trackr",
                    help="targeted per-title trackr harvest")
    ap.add_argument("--from-zip", metavar="PATH", help="path to U_SRG-STIG_Library_*.zip")
    ap.add_argument("--library", metavar="NAME", help="library label (default: zip stem)")
    ap.add_argument("--titles", metavar="T1,T2", help="trackr titles for --via-trackr")
    ap.add_argument("--max-delta", type=int, default=25,
                    help="max stale titles to re-harvest via API before deferring to --full")
    ap.add_argument("--json", action="store_true", help="machine-readable --check output")
    args = ap.parse_args(argv)
    if args.full:
        return mode_full(args)
    if args.delta:
        return mode_delta(args)
    if args.refresh_stale:
        return mode_refresh_stale(args)
    if args.via_trackr:
        return mode_via_trackr(args)
    if args.check:
        return mode_check(args)
    if args.catalog:
        return mode_catalog(args)
    ap.error("choose one of --catalog / --full / --check / --delta / --via-trackr")
    return 2


if __name__ == "__main__":
    sys.exit(main())
