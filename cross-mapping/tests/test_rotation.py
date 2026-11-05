#!/usr/bin/env python3
"""Offline tests for the phase-51 weekly rotation (tools/fetch_rotation.py, fetch_schedule.json,
stig_harvest --auto-library). Temporary copies only — the repository is never written.
Pins: the cron that fired selects the slot (a delayed run keeps its slot); a change that is only
volatile stamps is reverted; a report job never leaves a change; the per-day census fails on a
collision or a cap breach; commit messages are trailer-free; suggestions come from measured output;
--auto-library downloads only on a newer DISA quarter."""

import argparse
import copy
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
import fetch_rotation as fr  # noqa: E402
import fetchkit  # noqa: E402

PASS = 0
SCHED = fr.load_schedule()
KEYS = set(SCHED["volatile_keys"])


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok: {label}")


def test_slot_resolution():
    for name, s in SCHED["slots"].items():
        ok(fr.slot_for(SCHED, cron=s["cron"]) == name, f"cron '{s['cron']}' selects {name}")
    try:
        fr.slot_for(SCHED, cron="0 0 * * *")
        ok(False, "an unknown cron must be refused")
    except SystemExit:
        ok(True, "an unknown cron is refused")


def test_volatile_and_report_reverts():
    real = (ROOT / "canonical-sources/cfr/45-cfr-164.json").read_bytes()
    d = json.loads(real)
    d["_as_of_date"] = "2099-01-01"
    ok(not fr.substantive_change(real, json.dumps(d).encode(), KEYS), "a date-only change is not substantive")
    d2 = json.loads(real)
    d2["sections"][0]["text"] = d2["sections"][0].get("text", "") + " amended"
    ok(fr.substantive_change(real, json.dumps(d2).encode(), KEYS), "an amended section is substantive")
    tmp = Path(tempfile.mkdtemp())
    try:
        for rel in ("canonical-sources/cfr/45-cfr-164.json", "canonical-sources/cfr/32-cfr-170.json",
                    "canonical-sources/announcements_feed.json"):
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, tmp / rel)
        saved_root, saved_out = fr.ROOT, fr.OUT_DIR
        fr.ROOT, fr.OUT_DIR = tmp, tmp / ".fetch-cache" / "rotation"

        def runner(argv):
            a = " ".join(argv)
            for part, mut in (("164", "date"), ("170", "text")):
                if f"--part {part}" in a:
                    p = next((tmp / "canonical-sources/cfr").glob(f"*-cfr-{part}.json"))
                    x = json.loads(p.read_text(encoding="utf-8"))
                    if mut == "date":
                        x["_as_of_date"] = "2099-01-01"
                    else:
                        x["sections"][0]["title"] += " (amended)"
                    p.write_text(json.dumps(x), encoding="utf-8")
            return 0, "ok"
        rep = fr.run_slot(SCHED, "tue-regulatory", runner=runner)
        ok(rep["changed_files"] == ["canonical-sources/cfr/32-cfr-170.json"], "only the substantive change is proposed")
        ok((tmp / "canonical-sources/cfr/45-cfr-164.json").read_bytes() == real, "the date-only file is restored byte-identical")
        s2 = copy.deepcopy(SCHED)
        s2["jobs"]["fr-watcher"]["mode"] = "report"
        before = (ROOT / "canonical-sources/announcements_feed.json").read_bytes()

        def writer(argv):
            if "fr_watcher" in " ".join(argv):
                (tmp / "canonical-sources/announcements_feed.json").write_text("{}", encoding="utf-8")
            return 0, "{}"
        rep2 = fr.run_slot(s2, "tue-regulatory", runner=writer)
        ok((tmp / "canonical-sources/announcements_feed.json").read_bytes() == before and not rep2["changed_files"],
           "a report-mode job's write is reverted")
    finally:
        fr.ROOT, fr.OUT_DIR = saved_root, saved_out
        shutil.rmtree(tmp)


def test_census():
    pol = fetchkit.load_policies()
    days, bad = fr.census_slots(SCHED, pol)
    per_day = {d: sum(v["requests"] for v in h.values()) for d, h in sorted(days.items())}
    ok(not bad, f"the committed rotation is inside every cap: {per_day}")
    red = copy.deepcopy(SCHED)
    red["slots"]["tue-extra"] = {"cron": "59 20 * * 2", "workflow": "weekly-refresh.yml", "jobs": ["ecfr-45-164"]}
    ok(any("one slot per host per day" in v for v in fr.census_slots(red, pol)[1]), "RED: two slots on one host and day")
    red2 = copy.deepcopy(SCHED)
    red2["jobs"]["kev"]["requests_measured"] = {"www.cisa.gov": 26}
    ok(any("run_cap 25" in v for v in fr.census_slots(red2, pol)[1]), "RED: a day over a host's run_cap")


def test_commit_message_and_suggestions():
    rep = {"slot": "tue-regulatory", "changed_files": ["canonical-sources/cfr/32-cfr-170.json"],
           "jobs": [{"job": "ecfr-32-170", "changed": ["canonical-sources/cfr/32-cfr-170.json"]}]}
    msg = fr.commit_message(rep, "2026-11-10")
    ok(msg.startswith("Weekly refresh (tue-regulatory, 2026-11-10)") and not re.search(r"(?m)^[A-Za-z-]+: ", msg)
       and msg.count(". ") <= 1, "commit message: plain 1-2 sentences, no trailers")
    nvd = json.dumps({"metadata": {"total_cves": 9676, "critical_count": 820, "days_covered": 7}, "cves": ["x" * 800] * 9676})
    s = fr.suggest("nvd-7d", nvd, SCHED)
    ok(s["suggest"] == "not as weekly snapshots" and "9,676 CVEs" in s["why"], "NVD over 1 MB: suggest a rolling file, with measured numbers")
    s = fr.suggest("nvd-7d", json.dumps({"metadata": {"total_cves": 3, "critical_count": 0, "days_covered": 7}}), SCHED)
    ok(s["suggest"] == "yes", "a small NVD window: suggest commit")
    ok(fr.suggest("fips", None, SCHED)["suggest"] == "repair first", "an unschedulable source: repair first, with its reason")
    sec = fr.digest_section({"slot": "wed-vulnerability", "jobs": [{"job": "kev", "mode": "pr", "status": "ok", "changed": [], "why": "always"}]},
                            SCHED, [fr.suggest("olir", None, SCHED)])
    ok(sec.startswith("<!-- slot:wed-vulnerability -->") and sec.endswith("<!-- /slot:wed-vulnerability -->")
       and "Suggested to commit" in sec, "digest section is delimited per slot and carries the suggestions")


def test_auto_library():
    import stig_harvest as sh
    calls = {}
    saved = sh.library_signal, sh.ROOT
    try:
        sh.library_signal = lambda pinned: {"status": "same", "library": "U_SRG-STIG_Library_October_2026"}
        rc = sh.mode_auto_library(argparse.Namespace(), _fetch=lambda u: calls.setdefault("get", u), _full=lambda ns: 1)
        ok(rc == 0 and "get" not in calls, "--auto-library: no newer quarter -> no download")
        sh.library_signal = lambda pinned: {"status": "newer", "library": "U_SRG-STIG_Library_January_2027"}
        sh.ROOT = Path(tempfile.mkdtemp())
        rc = sh.mode_auto_library(argparse.Namespace(), _fetch=lambda u: calls.setdefault("get", u) and b"PK",
                                  _full=lambda ns: calls.setdefault("full", vars(ns)) and 0)
        ok(calls["get"].endswith("U_SRG-STIG_Library_January_2027.zip") and calls["full"]["retain_absent"]
           and calls["full"]["refresh_final"], "--auto-library: a newer quarter -> one GET, then the retaining refresh")
    finally:
        sh.library_signal, sh.ROOT = saved


if __name__ == "__main__":
    for fn in (test_slot_resolution, test_volatile_and_report_reverts, test_census,
               test_commit_message_and_suggestions, test_auto_library):
        fn()
    print(f"\nrotation tests: {PASS} assertions PASS")
