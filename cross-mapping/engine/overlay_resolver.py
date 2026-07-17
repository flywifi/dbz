#!/usr/bin/env python3
"""
overlay_resolver.py — load, validate, and combine context overlays.

Overlays (canonical-sources/overlays/) are presentation-layer profiles that
tailor query output to an industry / jurisdiction / client-template context.
They NEVER alter mappings, tiers, or tables — they set defaults, reorder
framework-keyed results (emphasized first), and may restrict the framework
universe, in which case every suppressed row is COUNTED and disclosed
(suppressed_count) — never silently dropped.

Precedence when several overlays combine (sets < adds < overrides application
order; conflicts won by the higher-precedence overlay):
    jurisdiction (regulatory) > industry > client-template
ties break on precedence_rank (lower rank = higher precedence) then id.
Resolution is fully deterministic: sorted inputs, sorted output lists.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERLAY_DIR = ROOT / "canonical-sources" / "overlays"

_SCOPE_PRECEDENCE = {"jurisdiction": 0, "industry": 1, "client-template": 2}
_VALID_SCOPES = set(_SCOPE_PRECEDENCE)
_VALID_TIERS = {"owner_direct", "nist_stated", "owner_stated", "hub",
                "bundled", "consensus", "production_aggregate"}
_VALID_LEVELS = {"low", "moderate", "high"}


class OverlayError(ValueError):
    pass


def _validate(o: dict, path: Path):
    for req in ("id", "scope", "description", "precedence_rank"):
        if req not in o:
            raise OverlayError(f"{path}: missing required field '{req}'")
    if o["scope"] not in _VALID_SCOPES:
        raise OverlayError(f"{path}: invalid scope {o['scope']!r}")
    mt = (o.get("sets") or {}).get("default_min_tier")
    if mt and mt not in _VALID_TIERS:
        raise OverlayError(f"{path}: invalid default_min_tier {mt!r}")
    lv = (o.get("sets") or {}).get("default_scope_fedramp")
    if lv and lv not in _VALID_LEVELS:
        raise OverlayError(f"{path}: invalid default_scope_fedramp {lv!r}")


def available() -> dict:
    """{name: path} for every shipped overlay; name is '<dir>/<id>' (e.g. industry/healthcare)."""
    out = {}
    if not OVERLAY_DIR.exists():
        return out
    for p in sorted(OVERLAY_DIR.rglob("*.json")):
        if p.name == "overlay.schema.json":
            continue
        rel = p.relative_to(OVERLAY_DIR).with_suffix("")
        out[str(rel)] = p
    return out


def load(name: str) -> dict:
    """Load one overlay by name ('industry/healthcare' or bare id 'healthcare')."""
    avail = available()
    path = avail.get(name)
    if path is None:
        matches = [p for n, p in avail.items() if n.split("/")[-1] == name]
        if len(matches) == 1:
            path = matches[0]
    if path is None:
        raise OverlayError(f"unknown overlay {name!r}; available: {sorted(avail)}")
    o = json.loads(path.read_text(encoding="utf-8"))
    _validate(o, path)
    return o


def resolve(names: list) -> dict:
    """Combine overlays into one effective profile (deterministic).

    Returns {names, sets, emphasized_frameworks, framework_universe|None}.
    Higher-precedence overlays win conflicting `sets`; emphasized lists concatenate
    in precedence order (deduped); universes intersect (most restrictive wins) —
    an empty intersection is an error, not a silent empty result.
    """
    overlays = [load(n) for n in names]
    overlays.sort(key=lambda o: (_SCOPE_PRECEDENCE[o["scope"]], o["precedence_rank"], o["id"]))
    sets_out: dict = {}
    emphasized: list = []
    universe = None
    for o in overlays:  # precedence order: first writer wins for sets
        for k, v in (o.get("sets") or {}).items():
            sets_out.setdefault(k, v)
        for fw in (o.get("adds") or {}).get("emphasized_frameworks", []):
            if fw not in emphasized:
                emphasized.append(fw)
        u = (o.get("overrides") or {}).get("framework_universe")
        if u is not None:
            universe = set(u) if universe is None else (universe & set(u))
    if universe is not None and not universe:
        raise OverlayError(f"overlays {names} produce an empty framework universe")
    return {
        "names": sorted(o["id"] for o in overlays),
        "sets": sets_out,
        "emphasized_frameworks": emphasized,
        "framework_universe": sorted(universe) if universe is not None else None,
    }


def apply_to_rows(profile: dict, rows: list, fw_keys=("fw_a", "fw_b")):
    """Filter + reorder framework-keyed row dicts per the profile.

    Suppresses rows involving a framework outside the universe (NIST 800-53, the
    spine, is always allowed) and moves rows involving an emphasized framework to
    the front (stable within groups). Returns (rows, suppressed_count).
    """
    universe = profile.get("framework_universe")
    emphasized = set(profile.get("emphasized_frameworks") or [])
    kept, suppressed = [], 0
    for r in rows:
        fws = {r.get(k) for k in fw_keys if r.get(k)}
        if universe is not None and any(
                fw != "NIST 800-53" and fw not in universe for fw in fws):
            suppressed += 1
            continue
        kept.append(r)
    if emphasized:
        kept.sort(key=lambda r: 0 if any(r.get(k) in emphasized for k in fw_keys) else 1)
    return kept, suppressed


def stamp(profile: dict, suppressed_count: int = 0) -> dict:
    """The disclosure block every overlay-filtered output must carry."""
    return {"names": profile["names"], "suppressed_count": suppressed_count,
            "emphasized": profile["emphasized_frameworks"]}
