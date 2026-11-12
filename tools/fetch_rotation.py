#!/usr/bin/env python3
"""
fetch_rotation.py — the weekly keep-current rotation (phase 51).

  --slot NAME | --cron "<github.event.schedule>"   run one slot's jobs (the cron string that fired
                                                   decides the slot, so a delayed run keeps its slot)
  --plan                                           print what the slot would run, run nothing
  --verify-workflows                               every slot's cron is present in its workflow file
  --census                                         per-day, per-host planned requests vs run_cap

A 'pr' job may change canonical files; a change that is ONLY volatile stamps (_as_of_date, fetched_at
…) is reverted so a pull request never carries date-only noise. A 'report' job never leaves a change
in the repository. Writes .fetch-cache/rotation/<slot>.json for the workflow (PR body, digest).
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = ROOT / "canonical-sources" / "fetch_schedule.json"
OUT_DIR = ROOT / ".fetch-cache" / "rotation"


def load_schedule(path: Path | None = None) -> dict:
    return json.loads((path or SCHEDULE).read_text(encoding="utf-8"))


def slot_for(sched: dict, slot: str | None = None, cron: str | None = None) -> str:
    if slot:
        if slot not in sched["slots"]:
            raise SystemExit(f"unknown slot {slot!r}")
        return slot
    hits = [n for n, s in sched["slots"].items() if s["cron"].split() == (cron or "").split()]
    if len(hits) != 1:
        raise SystemExit(f"cron {cron!r} matches {len(hits)} slots — each slot needs a distinct cron")
    return hits[0]


def strip_volatile(obj, keys):
    if isinstance(obj, dict):
        return {k: strip_volatile(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [strip_volatile(x, keys) for x in obj]
    return obj


def substantive_change(before: bytes | None, after: bytes | None, keys) -> bool:
    """True when the file changed beyond volatile stamps (JSON) or at all (other formats)."""
    if before == after:
        return False
    if before is None or after is None:
        return True
    try:
        return strip_volatile(json.loads(before), keys) != strip_volatile(json.loads(after), keys)
    except ValueError:
        return True


def _paths(patterns) -> list:
    out = []
    for p in patterns:
        out += sorted(glob.glob(str(ROOT / p))) if any(c in p for c in "*?[") else [str(ROOT / p)]
    return out


def _snapshot(paths) -> dict:
    return {p: (Path(p).read_bytes() if Path(p).exists() else None) for p in paths}


def check_condition(name: str | None) -> tuple:
    """(due, reason) for a job's 'when' precondition; an unknown name is never due."""
    if not name:
        return True, "always"
    for p in (ROOT / "tools", ROOT / "cross-mapping" / "engine"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    try:
        if name == "stig_library_newer":
            import stig_harvest
            sig = stig_harvest.library_signal(stig_harvest.read_catalog().get("_meta", {}).get("library"))
            return sig.get("status") == "newer", f"library signal: {sig.get('status')} {sig.get('library') or sig.get('reason') or ''}".strip()
        if name == "attack_version_changed":
            import attack_stix_loader
            live = attack_stix_loader.remote_attack_version()
            have = json.loads((ROOT / "canonical-sources" / "mitre-attack-techniques.json").read_text(encoding="utf-8")).get("_attack_version")
            return str(live) != str(have), f"ATT&CK live {live} vs committed {have}"
    except Exception as e:  # noqa: BLE001 — a failed check never runs the job, and says why
        return False, f"check failed: {type(e).__name__}: {e}"
    return False, f"unknown condition {name!r}"


def run_slot(sched: dict, slot: str, runner=None) -> dict:
    keys = set(sched.get("volatile_keys", []))
    report = {"slot": slot, "jobs": [], "changed_files": []}
    for jid in sched["slots"][slot]["jobs"]:
        job = sched["jobs"][jid]
        due, why = check_condition(job.get("when"))
        entry = {"job": jid, "mode": job["mode"], "due": due, "why": why}
        if not due:
            report["jobs"].append({**entry, "status": "skipped"})
            continue
        paths = _paths(job.get("outputs", []))
        before = _snapshot(paths)
        rc, out = (runner or _run)([sys.executable, *(str(ROOT / job["argv"][0]),), *job["argv"][1:]])
        if job["mode"] == "report":   # full output kept as a workflow artifact for the digest (never committed)
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUT_DIR / f"{jid}.out").write_text(out, encoding="utf-8")
        after = _snapshot(_paths(job.get("outputs", [])))
        changed, reverted = [], []
        for p in sorted(set(before) | set(after)):
            b, a = before.get(p), after.get(p)
            if b == a:
                continue
            if job["mode"] == "report" or not substantive_change(b, a, keys):
                (Path(p).write_bytes(b) if b is not None else Path(p).unlink(missing_ok=True))
                reverted.append(str(Path(p).relative_to(ROOT)))
            else:
                changed.append(str(Path(p).relative_to(ROOT)))
        report["jobs"].append({**entry, "status": "ok" if rc == 0 else f"rc={rc}", "changed": changed,
                               "reverted_volatile_only": reverted, "tail": out[-1500:]})
        report["changed_files"] += changed
    report["changed"] = bool(report["changed_files"])
    return report


def _run(argv) -> tuple:
    p = subprocess.run(argv, capture_output=True, text=True, cwd=str(ROOT), timeout=3600)
    return p.returncode, (p.stdout + p.stderr)


def verify_workflows(sched: dict) -> list:
    bad = []
    for name, s in sched["slots"].items():
        wf = ROOT / ".github" / "workflows" / s["workflow"]
        text = wf.read_text(encoding="utf-8") if wf.exists() else ""
        if f"'{s['cron']}'" not in text and f'"{s["cron"]}"' not in text:
            bad.append(f"slot {name}: cron '{s['cron']}' not found in {s['workflow']}")
    crons = [s["cron"] for s in sched["slots"].values()]
    if len(set(crons)) != len(crons):
        bad.append("two slots share one cron — a fired cron must identify exactly one slot")
    return bad


def census_slots(sched: dict, policies: dict) -> tuple:
    """Per weekday: summed measured requests per host vs run_cap; one slot per host per day. A slot
    whose workflow builds (its 'builds' field) also carries build_requests_measured, the OSCAL
    warm-up of the build (upper bound: a weekly-refresh slot builds only when a file changed)."""
    def cap(h):
        p = dict(policies.get("_default", {}).get("enforced", {}))
        p.update(policies.get("hosts", {}).get(h, {}).get("enforced", {}))
        return int(p.get("run_cap", 25))
    days, violations = {}, []
    for name, s in sched["slots"].items():
        dow = s["cron"].split()[4]
        loads = [sched["jobs"][jid].get("requests_measured", {}) for jid in s["jobs"]]
        if s.get("builds"):
            loads.append(sched.get("build_requests_measured", {}))
        for load in loads:
            for h, n in load.items():
                if h.startswith("_"):
                    continue
                d = days.setdefault(dow, {}).setdefault(h, {"requests": 0, "slots": set()})
                d["requests"] += n
                d["slots"].add(name)
    for dow, hosts in sorted(days.items()):
        for h, v in sorted(hosts.items()):
            if len(v["slots"]) > 1:
                violations.append(f"day {dow}: {h} is hit by {sorted(v['slots'])} — one slot per host per day")
            if v["requests"] > cap(h):
                violations.append(f"day {dow}: {h} {v['requests']} planned > run_cap {cap(h)}")
    return days, violations


def commit_message(report: dict, today: str) -> str:
    jobs = [j["job"] for j in report["jobs"] if j.get("changed")]
    files = ", ".join(Path(f).name for f in report["changed_files"][:4]) + (" …" if len(report["changed_files"]) > 4 else "")
    return (f"Weekly refresh ({report['slot']}, {today}): {', '.join(jobs)} changed at the issuer ({files}). "
            f"Proposed for human review; the build, oracle benchmark and scenarios ran on this tree.")

SUGGEST_MAX_MB = 1.0   # a committed weekly snapshot above this grows history by > 52 MB/year
SUGGEST_RULES = ("nvd-7d",)


def _report_json(out_text: str | None) -> tuple:
    """(document, its text) from a report job's captured output. That output is stdout + stderr
    (_run), and a loader prints progress lines before its --format json document, so the whole
    text is never one JSON value: the first real Wednesday run (2026-11-11) said "no parseable
    result" for a run that had fetched its window. The document starts at the first line that
    opens with "{"; raw_decode stops at its end, so stderr after it is ignored. Raises ValueError."""
    text = out_text or ""
    m = re.search(r"^\{", text, re.M)
    if not m:
        raise ValueError("no JSON document in the output")
    doc, end = json.JSONDecoder().raw_decode(text, m.start())
    if not isinstance(doc, dict):
        raise ValueError("the JSON value in the output is not an object")
    return doc, text[m.start():end]


def suggest(job_id: str, out_text: str | None, sched: dict) -> dict:
    """A commit suggestion for one report-only dataset, from what this run measured."""
    ns = sched.get("not_scheduled", {})
    if job_id in ns:
        return {"dataset": job_id, "suggest": "repair first", "why": ns[job_id]}
    if job_id == "nvd-7d":
        try:
            d, raw = _report_json(out_text)
        except ValueError:
            return {"dataset": job_id, "suggest": "no", "why": "the run produced no parseable result"}
        md = d.get("metadata", {})
        n, crit = md.get("total_cves", 0), md.get("critical_count", 0)
        mb = len(raw.encode()) / 1e6
        if not n:
            return {"dataset": job_id, "suggest": "no", "why": "0 CVEs in the window"}
        base = (f"{n:,} CVEs in the last {md.get('days_covered')} days ({crit:,} critical), {mb:.1f} MB as one file; "
                f"build_db loads canonical-sources/nvd-cve-*.json into nvd_cves, which is empty in every committed build")
        if mb <= SUGGEST_MAX_MB:
            return {"dataset": job_id, "suggest": "yes", "why": base}
        return {"dataset": job_id, "suggest": "not as weekly snapshots",
                "why": base + f"; weekly files would add about {mb * 52:,.0f} MB a year of history. If CVE rows are "
                       f"wanted in the database, commit one rolling file replaced weekly, or keep it local "
                       f"(the build loads it when present)"}
    return {"dataset": job_id, "suggest": "no", "why": "no suggestion rule for this dataset"}


def digest_section(report: dict, sched: dict, suggestions: list) -> str:
    rows = [f"| {j['job']} | {j['mode']} | {j['status']} | {', '.join(j.get('changed') or []) or '—'} | {j['why']} |"
            for j in report["jobs"]]
    sug = [f"- **{s['dataset']}** — suggest: **{s['suggest']}**. {s['why']}" for s in suggestions]
    return "\n".join([f"<!-- slot:{report['slot']} -->", f"### {report['slot']}", "",
                      "| job | mode | status | changed | condition |", "|---|---|---|---|---|", *rows, "",
                      "**Suggested to commit at your next session:**" if sug else "", *sug,
                      f"<!-- /slot:{report['slot']} -->"])

REPAIR_SLOT = "wed-vulnerability"   # the report-only day carries the "repair first" lines (WS-8)


def slot_suggestions(report: dict, sched: dict) -> list:
    out = []
    for j in report["jobs"]:
        if j["mode"] == "report" and j.get("status") == "ok" and j["job"] in SUGGEST_RULES:
            f = OUT_DIR / f"{j['job']}.out"
            out.append(suggest(j["job"], f.read_text(encoding="utf-8") if f.exists() else None, sched))
    if report["slot"] == REPAIR_SLOT:
        out += [suggest(n, None, sched) for n in sched.get("not_scheduled", {}) if n != "oscal"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slot"); ap.add_argument("--cron")
    ap.add_argument("--plan", action="store_true"); ap.add_argument("--verify-workflows", action="store_true")
    ap.add_argument("--census", action="store_true"); ap.add_argument("--commit-message", metavar="REPORT")
    a = ap.parse_args(argv)
    if a.commit_message:
        from datetime import datetime, timezone
        print(commit_message(json.loads(Path(a.commit_message).read_text(encoding="utf-8")),
                             datetime.now(timezone.utc).strftime("%Y-%m-%d")))
        return 0
    sched = load_schedule()
    if a.verify_workflows:
        bad = verify_workflows(sched)
        for b in bad:
            print(f"  VIOLATION {b}")
        print(f"[rotation] workflows {'FAIL' if bad else 'PASS'}")
        return 1 if bad else 0
    if a.census:
        sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
        import fetchkit
        days, bad = census_slots(sched, fetchkit.load_policies())
        for dow, hosts in sorted(days.items()):
            top = sorted(hosts.items(), key=lambda kv: -kv[1]["requests"])[:4]
            print(f"  day {dow}: {sum(v['requests'] for v in hosts.values())} requests to {len(hosts)} hosts; busiest "
                  + ", ".join(f"{h} {v['requests']}" for h, v in top))
        for b in bad:
            print(f"  VIOLATION {b}")
        print(f"[rotation] census {'FAIL' if bad else 'PASS'}")
        return 1 if bad else 0
    slot = slot_for(sched, a.slot, a.cron)
    if a.plan:
        for jid in sched["slots"][slot]["jobs"]:
            j = sched["jobs"][jid]
            print(f"  {slot}: {jid:14} mode={j['mode']:6} when={j.get('when', 'always')} argv={' '.join(j['argv'])}")
        return 0
    rep = run_slot(sched, slot)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{slot}.json").write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / f"digest-{slot}.md").write_text(digest_section(rep, sched, slot_suggestions(rep, sched)) + "\n", encoding="utf-8")
    print(f"[rotation] {slot}: {len(rep['jobs'])} job(s), changed files: {rep['changed_files'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
