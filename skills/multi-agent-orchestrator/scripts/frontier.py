#!/usr/bin/env python3
"""
frontier.py — deterministic backers for recursion control (frontier-expand + the
stop-condition half of task-decompose). Implements skills/shared/frontier-model.md.

Two pure functions (the "LLM decides, script computes" split):
  - expand_frontier(): given a wave's envelopes + the run's seen set, dedup the residual
    leads against seen and return the next wave — or signal a stop condition. This is the
    mechanical recursion step; the manager still decides how to word each next-wave prompt.
  - resolve_stop_conditions(): map a chosen mode + depth to the fixed {k_dry, depth_cap,
    size_cap} numbers from routing.md, so task-decompose never invents caps per run.

Determinism: next_scopes and seen_out are sorted; the same inputs always produce the same
output. Dependency-free (stdlib only).

Usage:
    from frontier import expand_frontier, resolve_stop_conditions
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Fixed stop-condition presets (mirror references/routing.md). task-decompose picks the
# mode + depth; these numbers are not re-invented per run.
_STOP_PRESETS = {
    ("read-fanout", "quick"): {"k_dry": 1, "depth_cap": 2, "size_cap": 24},
    ("read-fanout", "deep"):  {"k_dry": 2, "depth_cap": 4, "size_cap": 24},
    ("mutate", "quick"):      {"k_dry": 1, "depth_cap": 1, "size_cap": 12},
    ("mutate", "deep"):       {"k_dry": 1, "depth_cap": 1, "size_cap": 12},
    ("external", "quick"):    {"k_dry": 1, "depth_cap": 1, "size_cap": 8},
    ("external", "deep"):     {"k_dry": 1, "depth_cap": 1, "size_cap": 8},
}


def _sig(scope: Any) -> str:
    """Normalized scope signature: lowercased, whitespace-collapsed."""
    return " ".join(str(scope).lower().split())


def resolve_stop_conditions(mode: str, depth: str = "quick") -> Dict[str, int]:
    """Return the fixed {k_dry, depth_cap, size_cap} for a mode+depth (routing.md)."""
    return dict(_STOP_PRESETS.get((mode, depth), _STOP_PRESETS[("read-fanout", "quick")]))


def expand_frontier(envelopes: List[Dict[str, Any]], seen: List[str], wave: int,
                    stop_conditions: Dict[str, int], agents_so_far: int,
                    dry_streak: int = 0) -> Dict[str, Any]:
    """
    Dedup this wave's residual leads against `seen` and decide the next wave or a stop.

    Hard caps (size, depth) are checked first and stop the run even if new leads remain —
    the un-expanded leads are still returned so the manager can surface them. Saturation
    (k_dry consecutive dry waves) is the soft, primary stop signal.
    """
    size_cap = stop_conditions.get("size_cap", 24)
    depth_cap = stop_conditions.get("depth_cap", 2)
    k_dry = stop_conditions.get("k_dry", 1)

    seen_sigs = {_sig(s) for s in (seen or [])}

    # Collect new leads (deduped against seen and within this wave), preserving parent.
    new_scopes: List[Dict[str, Any]] = []
    picked: set[str] = set()
    for e in envelopes or []:
        if not isinstance(e, dict):
            continue
        parent = e.get("task_id")
        for lead in e.get("residual_frontier", []) or []:
            if not (isinstance(lead, dict) and "scope" in lead):
                continue
            sig = _sig(lead["scope"])
            if sig in seen_sigs or sig in picked:
                continue
            picked.add(sig)
            new_scopes.append({
                "scope": lead["scope"],
                "reason": lead.get("reason", ""),
                "parent_task_id": parent,
            })
    new_scopes.sort(key=lambda s: _sig(s["scope"]))

    is_dry = not new_scopes
    new_streak = dry_streak + 1 if is_dry else 0

    # seen grows by this wave's dispatched scopes.
    seen_out = sorted(seen_sigs | {_sig(e.get("scope", "")) for e in (envelopes or [])
                                   if isinstance(e, dict)})

    # Precedence: hard caps first, then saturation.
    if agents_so_far >= size_cap:
        stop = "size_cap_reached"
    elif wave >= depth_cap:
        stop = "depth_cap_reached"
    elif is_dry and new_streak >= k_dry:
        stop = "saturated"
    else:
        stop = None

    return {
        "next_scopes": new_scopes,
        "saturated": is_dry,
        "dry_streak": new_streak,
        "stop_condition": stop,
        "seen_out": seen_out,
        "human_review_required": True,
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: frontier.py <payload.json | ->   "
              "(payload: {envelopes, seen, wave, stop_conditions, agents_so_far, dry_streak?}) "
              "OR {mode, depth} to resolve stop conditions", file=sys.stderr)
        return 2
    raw = sys.stdin.read() if argv[0] == "-" else Path(argv[0]).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if "envelopes" in payload:
        out = expand_frontier(
            payload.get("envelopes", []), payload.get("seen", []),
            payload.get("wave", 1), payload.get("stop_conditions", {}),
            payload.get("agents_so_far", 0), payload.get("dry_streak", 0),
        )
    else:
        out = resolve_stop_conditions(payload.get("mode", "read-fanout"),
                                      payload.get("depth", "quick"))
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
