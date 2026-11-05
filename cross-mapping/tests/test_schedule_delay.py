#!/usr/bin/env python3
"""Offline tests for the phase-51 queue-delay probe (tools/schedule_delay.py, schedule-probe.yml).
Pins: the five measured standards-watch runs reproduce their recorded delays (3.34 / 3.85 / 5.08 /
5.49 / 8.13 h, median 304.8 min); a run delayed past the next candidate time is attributed to its
own cron by the run title, not to the nearest earlier fire; the pin rule ranks by median then p90
and never picks minute :00 or :30; the probe workflow carries the attributing run-name, six
off-the-hour crons, no permissions and no checkout."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import schedule_delay as sd  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok: {label}")


def test_measured_runs():
    starts = ("2026-07-03T09:37:33Z", "2026-08-03T10:07:54Z", "2026-09-03T11:21:47Z", "2026-10-03T11:46:21Z",
              "2026-11-03T14:25:03Z")
    rows = sd.delays([{"created_at": t, "run_started_at": t} for t in starts], "17 6 3 * *")
    ok([round(r["delay_min"] / 60, 2) for r in rows] == [3.34, 3.85, 5.08, 5.49, 8.13],
       "the five measured scheduled runs (cron 17 6 3 * *) reproduce their recorded delays")
    s = sd.summary(rows)["17 6 3 * *"]
    ok(s["n"] == 5 and s["median_min"] == 304.8 and s["max_min"] == 488.1, "summary: n 5, median 304.8 min, max 488.1 min")


def test_attribution_and_rank():
    fx = [{"display_title": "probe 17 6 * * *", "run_started_at": "2026-11-06T10:05:00Z", "created_at": ""},
          {"display_title": "probe 41 2 * * *", "run_started_at": "2026-11-06T02:58:00Z", "created_at": ""},
          {"display_title": "probe 41 2 * * *", "run_started_at": "2026-11-07T03:05:00Z", "created_at": ""},
          {"schedule": "43 13 * * *", "run_started_at": "2026-11-06T13:49:00Z", "created_at": ""},
          {"schedule": "43 13 * * *", "run_started_at": "2026-11-07T13:52:00Z", "created_at": ""}]
    rows = sd.delays(fx)
    ok(rows[0]["cron"] == "17 6 * * *" and rows[0]["delay_min"] == 228.0,
       "a 06:17 run that starts at 10:05 is credited to 06:17 (3h48m), not to 09:47 (18 min)")
    summ = sd.summary(rows)
    ok(sd.rank(summ) == ["43 13 * * *", "41 2 * * *", "17 6 * * *"], "pin order: lowest median first")
    summ["0 12 * * *"] = {"n": 9, "median_min": 0.0, "p90_min": 0.0, "max_min": 0.0}
    summ["30 4 * * *"] = {"n": 9, "median_min": 0.0, "p90_min": 0.0, "max_min": 0.0}
    ok(sd.rank(summ)[0] == "43 13 * * *", "a :00 or :30 cron is never eligible, however quiet it measured")
    tie = {"a": {"median_min": 5, "p90_min": 9}, "b": {"median_min": 5, "p90_min": 7}}
    ok(sd.rank({"11 1 * * *": tie["a"], "13 1 * * *": tie["b"]}) == ["13 1 * * *", "11 1 * * *"], "a median tie goes to the lower p90")
    ok(sd.last_fire("17 6 * * 1", sd.datetime(2026, 11, 12, 9, 0, tzinfo=sd.timezone.utc)).isoformat()
       == "2026-11-09T06:17:00+00:00", "a weekly cron's last fire is found on its weekday (Monday)")


def test_probe_workflow():
    text = (ROOT / ".github" / "workflows" / "schedule-probe.yml").read_text(encoding="utf-8")
    crons = re.findall(r"(?m)^    - cron: '([^']+)'", text)
    ok('run-name: "probe ${{ github.event.schedule }}"' in text, "the probe titles each run with the cron that fired")
    ok(len(crons) == 6 and len(set(crons)) == 6 and all(int(c.split()[0]) not in (0, 30) for c in crons),
       f"six distinct candidate times, none on :00/:30 ({', '.join(c.split()[1] + ':' + c.split()[0].zfill(2) for c in crons)} UTC)")
    ok("permissions: {}" in text and "actions/checkout" not in text and "${{" not in re.sub(r"(?m)^.*(run-name|FIRED):.*$", "", text),
       "no permissions, no checkout, no expression in a shell line")


if __name__ == "__main__":
    for fn in (test_measured_runs, test_attribution_and_rank, test_probe_workflow):
        fn()
    print(f"\nschedule-delay tests: {PASS} assertions PASS")
