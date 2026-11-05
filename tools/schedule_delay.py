#!/usr/bin/env python3
"""
schedule_delay.py — GitHub scheduled-run queue delay per cron time (phase 51, WS-5).

Delay of a run = its run_started_at minus the latest scheduled time of its cron at or before it.
Input: a JSON list of runs (from the GitHub MCP list_workflow_runs, or the REST API with
GITHUB_TOKEN on a runner), each with created_at / run_started_at and the cron that fired: the
probe's run title "probe <cron>" (display_title; run-name in schedule-probe.yml), else a 'schedule'
field, else --cron for a single-cron workflow. Attribution by title matters: a run delayed past the
next candidate time would otherwise be credited to the wrong cron (plan T-6: a 3h48m delay hidden
as 18 minutes).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone


def _fields(cron: str):
    m, h, dom, mon, dow = cron.split()
    return int(m), int(h), dom, dow


def last_fire(cron: str, t: datetime) -> datetime:
    """Latest time <= t that `cron` (minute hour dom * dow, numeric/'*' fields only) fires."""
    m, h, dom, dow = _fields(cron)
    day = t.replace(hour=h, minute=m, second=0, microsecond=0)
    for _ in range(40):
        if day <= t and (dom == "*" or day.day == int(dom)) and (dow == "*" or day.isoweekday() % 7 == int(dow)):
            return day
        day -= timedelta(days=1)
    raise ValueError(f"no fire of {cron!r} within 40 days before {t}")


def delays(runs: list, cron: str | None = None) -> list:
    out = []
    for r in runs:
        title = r.get("display_title") or ""
        c = r.get("schedule") or (title[len("probe "):] if title.startswith("probe ") else None) or cron
        start = datetime.fromisoformat((r.get("run_started_at") or r["created_at"]).replace("Z", "+00:00"))
        fired = last_fire(c, start)
        out.append({"cron": c, "scheduled": fired.isoformat(), "started": start.isoformat(),
                    "delay_min": round((start - fired).total_seconds() / 60, 1)})
    return out


def summary(rows: list) -> dict:
    by = {}
    for r in rows:
        by.setdefault(r["cron"], []).append(r["delay_min"])
    return {c: {"n": len(v), "median_min": statistics.median(v), "p90_min": sorted(v)[max(0, int(len(v) * 0.9) - 1)],
                "max_min": max(v)} for c, v in sorted(by.items())}


def rank(summ: dict) -> list:
    """The pin rule (phase 51 WS-5): lowest median delay first, ties broken by the lower p90. A cron
    on minute :00 or :30 is never eligible (GitHub: high load at the start of every hour)."""
    ok = [c for c in summ if int(c.split()[0]) not in (0, 30)]
    return sorted(ok, key=lambda c: (summ[c]["median_min"], summ[c]["p90_min"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs_json"); ap.add_argument("--cron")
    a = ap.parse_args(argv)
    runs = json.load(open(a.runs_json, encoding="utf-8"))
    runs = runs.get("workflow_runs", runs) if isinstance(runs, dict) else runs
    summ = summary(delays([r for r in runs if r.get("event", "schedule") == "schedule"], a.cron))
    for c, s in summ.items():
        print(f"  {c:16} n={s['n']:3}  median {s['median_min']/60:5.2f} h  p90 {s['p90_min']/60:5.2f} h  max {s['max_min']/60:5.2f} h")
    print("  pin order (lowest median, then p90; never :00/:30):", rank(summ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
