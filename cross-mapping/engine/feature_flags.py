#!/usr/bin/env python3
"""
Feature-flag layer for gated integrations.

Anything that needs OAuth, an API key, or other per-user setup is gated here and
DISABLED by default, so the core cross-mapping pipeline runs for everyone with
zero configuration. Individual users opt in once they have credentials.

A flag is only EFFECTIVE when it is both:
  1. enabled  — via feature_flags.json `enabled:true` OR env override DBZ_FF_<ID>=1
  2. provisioned — all of its `requires.env` variables are present

Code should call `flags.effective(flag_id)` and degrade gracefully when it is
False (use bundled data, report a gap, etc.) rather than failing.

Usage:
    from feature_flags import FeatureFlags
    flags = FeatureFlags.load()

    if flags.effective("github_authenticated"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    # else: unauthenticated fallback

CLI:
    python3 feature_flags.py --list                 # show all flags + status
    python3 feature_flags.py --status github_authenticated
    python3 feature_flags.py --enable cloud_render   # persist enabled=true to the json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
DEFAULT_FLAGS_PATH = _REPO_ROOT / "canonical-sources" / "feature_flags.json"

ENV_PREFIX = "DBZ_FF_"


class FeatureFlags:
    """Loads the flag registry and answers enabled / provisioned / effective."""

    def __init__(self, registry: dict, path: Optional[Path] = None):
        self._registry = registry
        self._flags: Dict[str, dict] = registry.get("flags", {})
        self._path = path

    # ── loading ──────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: Path = DEFAULT_FLAGS_PATH) -> "FeatureFlags":
        if not Path(path).exists():
            # No registry → everything off, but don't crash the pipeline.
            return cls({"flags": {}}, path=Path(path))
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f), path=Path(path))

    # ── queries ──────────────────────────────────────────────────────────────
    def exists(self, flag_id: str) -> bool:
        return flag_id in self._flags

    def _env_override(self, flag_id: str) -> Optional[bool]:
        """DBZ_FF_<ID>=1/true/on → True; =0/false/off → False; unset → None."""
        raw = os.environ.get(ENV_PREFIX + flag_id.upper())
        if raw is None:
            return None
        return raw.strip().lower() in ("1", "true", "on", "yes")

    def is_enabled(self, flag_id: str) -> bool:
        """Enabled by config or env override (does NOT check credentials)."""
        override = self._env_override(flag_id)
        if override is not None:
            return override
        return bool(self._flags.get(flag_id, {}).get("enabled", False))

    def missing_requirements(self, flag_id: str) -> List[str]:
        """Names of required env vars that are not currently set."""
        req = self._flags.get(flag_id, {}).get("requires", {})
        return [v for v in req.get("env", []) if not os.environ.get(v)]

    def needs_oauth(self, flag_id: str) -> bool:
        return bool(self._flags.get(flag_id, {}).get("requires", {}).get("oauth", False))

    def provisioned(self, flag_id: str) -> bool:
        """All required credentials present. (OAuth flags can't be verified headless.)"""
        return not self.missing_requirements(flag_id)

    def effective(self, flag_id: str) -> bool:
        """
        True only when the flag is enabled AND its credentials are provisioned.
        This is the gate code should check before using a gated integration.
        """
        if not self.is_enabled(flag_id):
            return False
        if self.needs_oauth(flag_id):
            # OAuth can't be verified here; trust the operator's enable + env creds.
            return self.provisioned(flag_id)
        return self.provisioned(flag_id)

    def reason_disabled(self, flag_id: str) -> str:
        """Human-readable explanation of why a flag is not effective."""
        if not self.exists(flag_id):
            return f"unknown flag '{flag_id}'"
        if not self.is_enabled(flag_id):
            return "disabled (set enabled=true or DBZ_FF_%s=1)" % flag_id.upper()
        missing = self.missing_requirements(flag_id)
        if missing:
            return f"enabled but missing credentials: {', '.join(missing)}"
        if self.needs_oauth(flag_id):
            return "enabled; requires interactive OAuth authorization"
        return "effective"

    def status(self, flag_id: str) -> dict:
        meta = self._flags.get(flag_id, {})
        return {
            "flag": flag_id,
            "label": meta.get("label", ""),
            "category": meta.get("category", ""),
            "enabled": self.is_enabled(flag_id),
            "provisioned": self.provisioned(flag_id),
            "effective": self.effective(flag_id),
            "needs_oauth": self.needs_oauth(flag_id),
            "missing_requirements": self.missing_requirements(flag_id),
            "reason": self.reason_disabled(flag_id),
            "degradation": meta.get("degradation", ""),
        }

    def all_status(self) -> List[dict]:
        return [self.status(fid) for fid in self._flags]

    # ── mutation (persist enable/disable) ─────────────────────────────────────
    def set_enabled(self, flag_id: str, enabled: bool) -> None:
        if flag_id not in self._flags:
            raise KeyError(f"unknown flag '{flag_id}'")
        self._flags[flag_id]["enabled"] = enabled
        if self._path:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._registry, f, indent=2, ensure_ascii=False)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Inspect / toggle GRC feature flags")
    ap.add_argument("--flags", default=str(DEFAULT_FLAGS_PATH))
    ap.add_argument("--list", action="store_true", help="list all flags + status")
    ap.add_argument("--status", metavar="FLAG", help="show one flag's status")
    ap.add_argument("--enable", metavar="FLAG", help="persist enabled=true for FLAG")
    ap.add_argument("--disable", metavar="FLAG", help="persist enabled=false for FLAG")
    a = ap.parse_args(argv)

    flags = FeatureFlags.load(Path(a.flags))

    if a.enable:
        flags.set_enabled(a.enable, True)
        print(f"[✓] enabled '{a.enable}' — {flags.reason_disabled(a.enable)}")
        return 0
    if a.disable:
        flags.set_enabled(a.disable, False)
        print(f"[✓] disabled '{a.disable}'")
        return 0
    if a.status:
        print(json.dumps(flags.status(a.status), indent=2))
        return 0

    # default: list
    rows = flags.all_status()
    print(f"{'FLAG':<28} {'CATEGORY':<20} {'EFFECTIVE':<10} REASON")
    print("-" * 90)
    for r in rows:
        eff = "yes" if r["effective"] else "no"
        print(f"{r['flag']:<28} {r['category']:<20} {eff:<10} {r['reason']}")
    print(f"\n{sum(r['effective'] for r in rows)}/{len(rows)} effective "
          f"(everything off by default — opt in per user).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
