#!/usr/bin/env python3
"""Offline tests for the phase-51 weekly rotation (tools/fetch_rotation.py, fetch_schedule.json,
stig_harvest --auto-library). Temporary copies only — the repository is never written.
Pins: the cron that fired selects the slot (a delayed run keeps its slot); a change that is only
volatile stamps is reverted; a report job never leaves a change; the per-day census fails on a
collision or a cap breach; commit messages are trailer-free; suggestions come from measured output;
--auto-library downloads only on a newer DISA quarter."""

import argparse
import contextlib
import io
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
    # phase 53: a job's captured output is progress lines, then the document, then stderr — never one JSON value
    real = ("=== NVD CVE API 2.0 Loader ===\n  No API key — NVD window from host_policies.json (5 per 30 s; 50 with NVD_API_KEY)\n"
            "  Date range: 2026-11-04 → 2026-11-11 (7 days)\n  Fetched 2000/9676 CVEs…\n\n  Summary: 9676 CVEs loaded, CVSS >= 7.0: 3100, CRITICAL: 820\n"
            "  [dry-run] Skipping file write.\n" + json.dumps(json.loads(nvd), indent=2) + "\n[fetchkit] ledger saved\n")
    try:
        json.loads(real)
        whole = True
    except ValueError:
        whole = False
    s = fr.suggest("nvd-7d", real, SCHED)
    ok(not whole and s["suggest"] == "not as weekly snapshots" and "9,676 CVEs" in s["why"],
       "the real output shape (progress lines, the document, stderr) is parsed although the whole text is not JSON")
    ok(fr.suggest("nvd-7d", "=== NVD CVE API 2.0 Loader ===\n  [error] HTTP 503\n", SCHED)["why"] == "the run produced no parseable result",
       "an output with no document still says so")
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


def test_writers_no_churn():
    """Phase 52: a Tuesday run with nothing new leaves announcements_feed.json byte-identical (no false PR);
    a run with something new changes entries and generated_at only, and every other top-level key (a
    human's _note_hipaa_prune, the other writer's _usage/_purpose) survives; a repeat of the same document
    is deduplicated and writes nothing."""
    import fr_watcher as fw
    import announcement_monitor as am
    src = ROOT / "canonical-sources" / "announcements_feed.json"
    new = {"feed_id": "fr-2026-24001", "entry_id": "fr-2026-24001", "title": "t", "published_at": "2026-11-09",
           "url": "https://www.federalregister.gov/d/2026-24001", "human_reviewed": False}

    def fw_write(entries, path):
        fw._write_output(*fw._merge_entries(entries, fw._load_existing(path)), 7, path)

    def am_write(entries, path):
        merged, added = am.merge_with_existing(entries, path)
        am._write_feed_doc(merged, added, 45, path)
    for label, write in (("fr_watcher", fw_write), ("announcement_monitor", am_write)):
        tmp = Path(tempfile.mkdtemp()) / "announcements_feed.json"
        shutil.copy(src, tmp)
        before = tmp.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            write([], tmp)
            zero = tmp.read_bytes()
            write([dict(new)], tmp)
            one = tmp.read_bytes()
            write([dict(new)], tmp)
            again = tmp.read_bytes()
        b, o = json.loads(before), json.loads(one)
        changed = sorted(k for k in set(o) | set(b) if o.get(k) != b.get(k))
        ok(zero == before, f"{label}: zero new documents -> file byte-identical (no PR)")
        ok(changed == ["entries", "generated_at"] and set(b) <= set(o) and "_note_hipaa_prune" in o,
           f"{label}: one new document -> only entries + generated_at change; no top-level key dropped")
        ok(again == one, f"{label}: the same document next week -> deduplicated, file unchanged")


def test_digest_rules():
    """Phase 52: only report jobs with a suggestion rule (nvd-7d) produce a 'suggest' line; horizon-check
    printed 'suggest: no. no suggestion rule for this dataset' on the first Thursday run."""
    rep = {"slot": "thu-dod-mitre", "jobs": [
        {"job": "attack", "mode": "pr", "status": "skipped", "changed": [], "why": "check failed"},
        {"job": "horizon-check", "mode": "report", "status": "ok", "changed": [], "why": "always"}]}
    ok(fr.slot_suggestions(rep, SCHED) == [], "Thursday digest: no suggestion line for horizon-check")
    ok("nvd-7d" in fr.SUGGEST_RULES, "Wednesday digest still suggests the NVD dataset")


def test_gated_atom_entries():
    """Phase 52: the 18 releases.atom announcement entries are kept but gated ("enabled": false): a gated
    entry makes no request at all, so github.com's robots refusals (16 per run) vanish and every other
    request is unchanged. Whole dry-run of the monitor against a fake governor serving github.com's real
    '/*.atom$' rule."""
    import announcement_monitor as am
    import urllib.error

    class R(io.BytesIO):
        def __init__(s, b):
            super().__init__(b)
            s.status = 200
            s.headers = {"Content-Type": "text/xml"}

        def __enter__(s):
            return s

        def __exit__(s, *a):
            return False

    def run_with(registry):
        sent = []

        def opener(req, t):
            u = req.full_url
            if u == "https://github.com/robots.txt":
                return R(b"User-agent: *\nDisallow: /*.atom$\n")
            if u.endswith("/robots.txt"):
                raise urllib.error.HTTPError(u, 404, "nf", {}, io.BytesIO(b""))
            sent.append(u)
            return R(b'<?xml version="1.0"?><rss><channel></channel></rss>')
        g = fetchkit.RateGovernor(state_path=None, opener=opener, sleeper=lambda s: None, budget=10 ** 6,
                                  policies={"_default": {"enforced": {"min_interval_s": 0, "run_cap": 10 ** 6}}, "hosts": {}})
        fetchkit._GOV = g
        am.GATED.clear()
        am._FETCH_MEMO.clear()
        d = Path(tempfile.mkdtemp())
        (d / "reg.json").write_text(json.dumps(registry), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            am.run(argparse.Namespace(registry=str(d / "reg.json"), output=str(d / "out.json"), feed=None,
                                      days=45, dry_run=True, log_dir=None))
        return g, sent
    reg = json.loads((ROOT / "canonical-sources" / "feed_registry.json").read_text(encoding="utf-8"))
    atoms = [a for e in reg["feeds"].values() if isinstance(e, dict) for a in e.get("announcement_feeds") or []
             if isinstance(a, dict) and (a.get("url") or "").endswith("/releases.atom")]
    ok(len(atoms) == 18 and all(a.get("enabled") is False and a.get("gated_reason") for a in atoms),
       "the 18 releases.atom entries are gated with a recorded reason")
    g1, s1 = run_with(reg)
    ok(len(g1.refusals.get("github.com", [])) == 0 and len(am.GATED) == 18, "gated entries make no request: 0 github.com refusals, 18 gated")
    ungated = copy.deepcopy(reg)
    for e in ungated["feeds"].values():
        for a in (e.get("announcement_feeds") or []) if isinstance(e, dict) else []:
            if isinstance(a, dict):
                a.pop("enabled", None)
    g0, s0 = run_with(ungated)
    ok(len(g0.refusals.get("github.com", [])) == 16 and sorted(s0) == sorted(s1),
       f"RED without the gate: 16 refusals; every other request unchanged ({len(s1)} sent either way)")
    fetchkit._GOV = None


if __name__ == "__main__":
    for fn in (test_slot_resolution, test_volatile_and_report_reverts, test_census,
               test_commit_message_and_suggestions, test_auto_library,
               test_writers_no_churn, test_digest_rules, test_gated_atom_entries):
        fn()
    print(f"\nrotation tests: {PASS} assertions PASS")
