#!/usr/bin/env python3
"""
fetch_census.py — offline census of one monthly standards-watch network plan (phase 50).

Every request the monthly `standards_refresh.py --check` makes is answered locally (no network):
the two registry-driven monitors, the GitHub release checks, the STIG currency signals and the CCI
check run as the workflow runs them, and every request is counted per host against
canonical-sources/host_policies.json. --check exits 1 when
  * any request bypasses fetchkit (an 'ungoverned' urlopen), or
  * a host's planned count exceeds its run_cap, or the total exceeds the runaway ceiling.
Upper-bound mode: canned responses carry no validators, so poll_landing feeds cost HEAD+GET, and
every GitHub releases lookup answers 404, so each release feed also costs its tags call.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "cross-mapping" / "engine", ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


class _Resp(io.BytesIO):
    def __init__(self, url: str):
        if "api.github.com" in url:
            body = b'[{"name": "census"}]' if url.endswith("/tags") else b'{"tag_name": "census"}'
        elif "cyber.trackr.live" in url:
            body = b"{}"
        elif url.endswith(".meta"):
            body = b"sha256:00\n"
        else:
            body = b'<?xml version="1.0"?><rss><channel></channel></rss>'
        super().__init__(body)
        self.status = 200
        self.headers = {"Content-Type": "text/xml"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def census(policies: dict) -> dict:
    import fetchkit
    governed, ungoverned = [], []

    def gov_open(req, timeout=None):
        governed.append(req.full_url)
        if req.full_url.endswith("/releases/latest"):
            # Upper bound: every repo answers "no releases", so each lookup also costs the tags
            # call. The first census answered with a release and counted 37 GitHub calls; the
            # first live dispatch (run 41936204283) made 54.
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b""))
        return _Resp(req.full_url)

    def raw_open(req, timeout=None, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        ungoverned.append(url)
        return _Resp(url)

    counting = {"_default": {"enforced": {"min_interval_s": 0, "run_cap": 10 ** 9}}, "hosts": {}}
    try:
        gov = fetchkit.RateGovernor(state_path=None, opener=gov_open, sleeper=lambda s: None,
                                    budget=10 ** 9, policies=counting)
    except TypeError:  # pre-phase-50 governor: no policies parameter
        gov = fetchkit.RateGovernor(state_path=None, opener=gov_open, sleeper=lambda s: None,
                                    budget=10 ** 9)
    fetchkit._GOV = gov
    fetchkit.save_state = lambda: None
    urllib.request.urlopen = raw_open
    real_sleep, time.sleep = time.sleep, (lambda s: None)
    import announcement_monitor, cci_harvest, framework_monitor, standards_refresh, stig_harvest
    for mod in (announcement_monitor, cci_harvest, framework_monitor, standards_refresh, stig_harvest):
        if hasattr(mod, "urlopen"):
            mod.urlopen = raw_open
    reg_path = ROOT / "canonical-sources" / "feed_registry.json"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            framework_monitor.run_monitor(dry_run=True, skip_strategies=["github_release"])  # as standards_refresh runs it
            announcement_monitor.run(argparse.Namespace(
                registry=str(reg_path), output=str(ROOT / "canonical-sources" / "announcements_feed.json"),
                feed=None, days=45, dry_run=True, log_dir=None))
            for fid, e in sorted(reg["feeds"].items()):
                if isinstance(e, dict) and e.get("check_strategy") == "github_release" and e.get("github_repo"):
                    standards_refresh._latest_release_tag(e["github_repo"])
            if hasattr(stig_harvest, "collect_signals"):
                stig_harvest.collect_signals(stig_harvest.read_catalog(), stig_harvest.read_map()["benchmarks"])
            else:
                stig_harvest.fetch_registry()
            cci_harvest._http(cci_harvest.TRACKR_ENUM)
    finally:
        time.sleep = real_sleep
    host = fetchkit._host
    robots = [u for u in governed if u.endswith("/robots.txt")]
    paced = [u for u in governed if not u.endswith("/robots.txt")]
    per_host = collections.Counter(host(u) for u in paced + ungoverned)
    violations, caps = [], {}
    if ungoverned:
        top = collections.Counter(host(u) for u in ungoverned).most_common(5)
        violations.append(f"{len(ungoverned)} ungoverned request(s) bypass fetchkit: "
                          + ", ".join(f"{h} x{n}" for h, n in top))
    for h, n in sorted(per_host.items()):
        p = dict(policies.get("_default", {}).get("enforced", {}))
        p.update(policies.get("hosts", {}).get(h, {}).get("enforced", {}))
        caps[h] = int(p.get("run_cap", 25))
        if n > caps[h]:
            violations.append(f"{h}: {n} planned > run_cap {caps[h]}")
    total = len(paced) + len(ungoverned)
    ceiling = getattr(fetchkit, "DEFAULT_BUDGET", 200)
    if total > ceiling:
        violations.append(f"total {total} > runaway ceiling {ceiling}")
    return {"total": total, "governed": len(paced), "ungoverned": len(ungoverned),
            "robots": len(robots), "hosts": len(per_host),
            "per_host": dict(per_host.most_common()), "caps": caps, "violations": violations}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 on any violation (CI gate)")
    ap.add_argument("--policies", default=str(ROOT / "canonical-sources" / "host_policies.json"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    policies = json.loads(Path(a.policies).read_text(encoding="utf-8"))
    r = census(policies)
    # Phase 51: the weekly rotation's per-day plan (fetch_schedule.json requests_measured) joins the gate.
    import fetch_rotation
    days, slot_bad = fetch_rotation.census_slots(fetch_rotation.load_schedule(), policies)
    r["violations"] += [f"rotation {v}" for v in slot_bad]
    r["rotation_days"] = {d: sum(v["requests"] for v in h.values()) for d, h in sorted(days.items())}
    if a.json:
        print(json.dumps(r, indent=2, sort_keys=True))
    else:
        print(f"[census] {r['total']} requests to {r['hosts']} hosts per monthly --check "
              f"({r['governed']} governed, {r['ungoverned']} ungoverned; {r['robots']} robots.txt)")
        for h, n in list(r["per_host"].items())[:8]:
            print(f"  {n:4} / cap {r['caps'][h]:<4} {h}")
        print(f"[census] weekly rotation, planned requests per weekday (cron day-of-week): {r['rotation_days']}")
        for v in r["violations"]:
            print(f"  VIOLATION {v}")
        print(f"[census] {'FAIL' if r['violations'] else 'PASS'}")
    return 1 if (a.check and r["violations"]) else 0


if __name__ == "__main__":
    sys.exit(main())
