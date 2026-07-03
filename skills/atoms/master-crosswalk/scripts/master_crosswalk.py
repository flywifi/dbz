#!/usr/bin/env python3
"""
master_crosswalk.py — atom wrapper over the master mapping surface.

Thin delegate to dbz_query's `master` subcommand so the atom and the CLI share
one implementation (no drift). Same flags:

    python3 master_crosswalk.py --framework-a "SOC 2" --framework-b "PCI DSS v4.0"
    python3 master_crosswalk.py --framework "HIPAA Security" --control "164.312(a)(1)"
    python3 master_crosswalk.py --framework-a "SOC 2" --scope-fedramp moderate --format json
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "cross-mapping" / "engine"))


def main(argv=None) -> int:
    import dbz_query  # type: ignore
    argv = list(sys.argv[1:] if argv is None else argv)
    return dbz_query.main(["master", *argv])


if __name__ == "__main__":
    sys.exit(main())
