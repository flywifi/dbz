#!/usr/bin/env python3
"""Offline tests for the phase-51 weekly workflows, run against the SHIPPED files.
Pins: every slot's cron is in its workflow (and a missing one is caught); the pull-request and digest
scripts are extracted from weekly-refresh.yml and run under node against a fake GitHub API (open vs
update, one dispatch of health.yml on the refresh branch, one digest section replaced in place, the
failed-PR / failed-battery notes); rotation_commit.sh commits trailer-free under GitHub's noreply bot
identity to auto/refresh-<slot> only, in a throwaway repository with a throwaway bare remote; the
build step makes no network request (the OSCAL catalog is committed, phase 52), so a building day carries no
build load; the Monday check measures inactivity.
The repository is never written."""

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "cross-mapping" / "engine"))
import fetch_rotation as fr  # noqa: E402
import fetchkit  # noqa: E402

PASS = 0
SCHED = fr.load_schedule()
WF = ROOT / ".github" / "workflows" / "weekly-refresh.yml"
DEFAULT = "claude/grc-backend-enhancements-0yxff6"


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok: {label}")


def _block(lines, i, indent):
    """Lines after a `key: |` line at index i that are indented deeper than `indent`, dedented."""
    out = []
    for ln in lines[i + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) <= indent:
            break
        out.append(ln)
    deep = min((len(x) - len(x.lstrip()) for x in out if x.strip()), default=0)
    return "\n".join(x[deep:] for x in out).strip("\n")


def _steps(text=None):
    """Stdlib parse of the refresh job's steps (health CI installs no PyYAML): {id|name|uses: {key: value}}
    for the scalar keys id/name/uses/if, and run/script as text (block or inline)."""
    lines = (text or WF.read_text(encoding="utf-8")).splitlines()
    steps, cur = {}, None
    for i, ln in enumerate(lines):
        m = re.match(r"^      - (\w[\w-]*): ?(.*)$", ln)
        if m:
            cur = {m.group(1): m.group(2).strip()}
            steps[len(steps)] = cur
            continue
        if cur is None:
            continue
        m = re.match(r"^( +)(id|name|uses|if|run|script): ?(.*)$", ln)
        if m and len(m.group(1)) == (10 if m.group(2) == "script" else 8):   # step keys; script under with:
            key, val = m.group(2), m.group(3).strip()
            cur[key] = _block(lines, i, len(m.group(1))) if val == "|" else val
    return {s.get("id") or s.get("name") or s.get("uses"): s for s in steps.values()}


def test_workflow_crons():
    ok(fr.verify_workflows(SCHED) == [], "every slot's cron is present in its workflow file")
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / ".github" / "workflows").mkdir(parents=True)
        shutil.copy(WF, tmp / ".github" / "workflows" / "weekly-refresh.yml")
        saved, fr.ROOT = fr.ROOT, tmp
        try:
            bad = fr.verify_workflows(SCHED)
        finally:
            fr.ROOT = saved
        ok(len(bad) == 1 and "standards-watch.yml" in bad[0], "RED: a workflow missing its slot's cron is caught")
    finally:
        shutil.rmtree(tmp)
    dup = copy.deepcopy(SCHED)
    dup["slots"]["wed-vulnerability"]["cron"] = dup["slots"]["tue-regulatory"]["cron"]
    ok(any("share one cron" in b for b in fr.verify_workflows(dup)), "RED: two slots sharing one cron are caught")
    text = WF.read_text(encoding="utf-8")
    perms = re.search(r"(?m)^permissions:\n((?:  .*\n)+)", text).group(1)
    ok(sorted(re.findall(r"(?m)^  ([\w-]+): write", perms)) == ["actions", "contents", "issues", "pull-requests"]
       and re.search(r"(?m)^  cancel-in-progress: false$", text), "weekly-refresh: least permissions it needs; runs never cancel each other")
    st = _steps()
    ok(all("${{" not in (s.get("run") or "") for s in st.values()),
       "no ${{ }} expression is interpolated into a shell line (values arrive through env)")
    ok(st["Update the weekly digest issue (read first by every new session; CLAUDE.md)"]["if"] == "always()",
       "the digest step runs even when an earlier step failed")


HARNESS = r"""
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const AF = Object.getPrototypeOf(async function () {}).constructor;
(async () => { const out = []; for (const c of inp.cases) {
  const log = []; let stored = c.body === undefined ? null : c.body;
  const fsx = {existsSync: (p) => c.files[p] !== undefined, readFileSync: (p) => c.files[p]};
  const github = {rest: {
    pulls: {list: async () => ({data: c.open ? [{number: 7}] : []}),
            update: async (a) => log.push('pr-update #' + a.pull_number),
            create: async (a) => { log.push(`pr-create ${a.head} -> ${a.base} "${a.title}"`); return {data: {number: 8}}; }},
    issues: {addLabels: async (a) => log.push('label ' + a.labels),
             listForRepo: async () => ({data: stored === null ? [] : [{number: 3, body: stored}]}),
             create: async (a) => { log.push('issue-create ' + a.labels); stored = a.body; },
             update: async (a) => { log.push('issue-update #' + a.issue_number); stored = a.body; }},
    actions: {createWorkflowDispatch: async (a) => log.push(`dispatch ${a.workflow_id}@${a.ref}`)}}};
  const ctx = {repo: {owner: 'o', repo: 'r'}, payload: {repository: {default_branch: inp.base}}};
  const proc = {env: c.env};
  await new AF('require', 'core', 'github', 'context', 'process', c.script)(() => fsx, {info: m => log.push('info ' + m)}, github, ctx, proc);
  out.push({log, body: stored});
} console.log(JSON.stringify(out)); })();"""


def _node(cases):
    r = subprocess.run(["node", "-e", HARNESS], input=json.dumps({"base": DEFAULT, "cases": cases}),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_pr_and_digest_scripts():
    if not shutil.which("node"):
        print("  SKIP (LOUD): node is not on PATH — the github-script steps were NOT exercised here; "
              "GitHub's ubuntu runners carry node, so CI runs this test")
        return
    st = _steps()
    pr = st["pr"]["script"]
    dg = st["Update the weekly digest issue (read first by every new session; CLAUDE.md)"]["script"]
    rep = {"slot": "tue-regulatory", "changed": True, "changed_files": ["canonical-sources/cfr/32-cfr-170.json"],
           "jobs": [{"job": "ecfr-32-170", "mode": "pr", "status": "ok", "changed": ["canonical-sources/cfr/32-cfr-170.json"], "why": "always"}]}
    files = {"r.json": json.dumps(rep), ".fetch-cache/rotation/battery.txt": "oracle benchmark: PASS"}
    a, b = _node([{"script": pr, "open": False, "files": files, "env": {"REPORT": "r.json"}},
                  {"script": pr, "open": True, "files": files, "env": {"REPORT": "r.json"}}])
    ok(a["log"][:3] == [f'pr-create auto/refresh-tue-regulatory -> {DEFAULT} "Weekly refresh: tue-regulatory"',
                        "label auto-refresh", "dispatch health.yml@auto/refresh-tue-regulatory"],
       "PR script, no open PR: opens one against the default branch, labels it, dispatches health.yml on the refresh branch")
    ok(b["log"][:2] == ["pr-update #7", "dispatch health.yml@auto/refresh-tue-regulatory"],
       "PR script, PR already open: updates its body (never a second PR), dispatches health.yml")
    sec = "<!-- slot:wed-vulnerability -->\n### wed-vulnerability\nNEW\n<!-- /slot:wed-vulnerability -->\n"
    two = ("# Weekly refresh digest\n\n<!-- slot:tue-regulatory -->\nTUE\n<!-- /slot:tue-regulatory -->\n\n"
           "<!-- slot:wed-vulnerability -->\nOLD\n<!-- /slot:wed-vulnerability -->")
    dfiles = {".fetch-cache/rotation/digest-wed-vulnerability.md": sec}
    env = {"SLOT": "wed-vulnerability", "BATTERY": "", "PR_STEP": ""}
    c1, c2, c3, c4 = _node([
        {"script": dg, "files": dfiles, "env": env},
        {"script": dg, "files": dfiles, "env": env, "body": two},
        {"script": dg, "files": dfiles, "env": {**env, "BATTERY": "success", "PR_STEP": "failure"}, "body": two},
        {"script": dg, "files": {}, "env": {**env, "SLOT": "thu-dod-mitre"}, "body": two}])
    ok(c1["log"][0] == "issue-create weekly-digest" and "NEW" in c1["body"], "digest: no issue yet -> one is created with the slot's section")
    ok(c2["log"][0] == "issue-update #3" and "TUE" in c2["body"] and "NEW" in c2["body"] and "OLD" not in c2["body"],
       "digest: only this slot's section is replaced; the other slot's survives")
    ok("Allow GitHub Actions to create and approve pull requests" in c3["body"] and c3["body"].count("<!-- /slot:wed-vulnerability -->") == 1,
       "digest: a failed PR step names the owner setting, inside the slot's own section")
    ok("<!-- slot:thu-dod-mitre -->" in c4["body"] and "did not produce a report" in c4["body"],
       "digest: a slot that produced no report still gets a section saying so")


def _git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def test_commit_script():
    tmp = Path(tempfile.mkdtemp())
    try:
        work, bare = tmp / "work", tmp / "remote.git"
        (work / "tools").mkdir(parents=True)
        (work / "canonical-sources" / "cfr").mkdir(parents=True)
        shutil.copy(ROOT / "tools" / "fetch_rotation.py", work / "tools")
        shutil.copy(ROOT / "tools" / "rotation_commit.sh", work / "tools")
        f = work / "canonical-sources" / "cfr" / "32-cfr-170.json"
        f.write_text('{"sections": [{"title": "a"}]}\n', encoding="utf-8")
        env_id = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "0+ambient-identity@users.noreply.github.com",
                  "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "0+ambient-identity@users.noreply.github.com"}
        os.environ.update(env_id)
        _git(work, "init", "-q", "-b", DEFAULT)
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", "base")
        subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
        _git(work, "remote", "add", "origin", str(bare))
        base = _git(bare, "rev-parse", DEFAULT)
        f.write_text('{"sections": [{"title": "a (amended)"}]}\n', encoding="utf-8")
        rep = {"slot": "tue-regulatory", "changed_files": ["canonical-sources/cfr/32-cfr-170.json"],
               "jobs": [{"job": "ecfr-32-170", "changed": ["canonical-sources/cfr/32-cfr-170.json"]}]}
        (tmp / "rep.json").write_text(json.dumps(rep), encoding="utf-8")
        r = subprocess.run(["bash", "tools/rotation_commit.sh", "tue-regulatory", str(tmp / "rep.json")],
                           cwd=work, capture_output=True, text=True)
        ok(r.returncode == 0, f"rotation_commit.sh exits 0 ({(r.stdout + r.stderr).strip().splitlines()[-1]})")
        who = _git(bare, "log", "-1", "--format=%an <%ae>", "auto/refresh-tue-regulatory")
        body = _git(bare, "log", "-1", "--format=%B", "auto/refresh-tue-regulatory")
        files = _git(bare, "show", "--name-only", "--format=", "auto/refresh-tue-regulatory")
        ok(who == "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>",
           "the bot commits under GitHub's noreply identity, overriding an ambient git identity")
        ok(body.startswith("Weekly refresh (tue-regulatory, ") and not re.search(r"(?m)^[A-Za-z-]+: ", body),
           "the bot's commit message is plain and trailer-free")
        ok(files == "canonical-sources/cfr/32-cfr-170.json", "only the report's changed files are committed")
        ok(_git(bare, "rev-parse", DEFAULT) == base, "the default branch on the remote is untouched")
        (tmp / "empty.json").write_text('{"changed_files": []}', encoding="utf-8")
        r2 = subprocess.run(["bash", "tools/rotation_commit.sh", "tue-regulatory", str(tmp / "empty.json")],
                            cwd=work, capture_output=True, text=True)
        ok(r2.returncode == 0 and "nothing to commit" in r2.stdout, "an empty report commits nothing")
    finally:
        for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
            os.environ.pop(k, None)
        shutil.rmtree(tmp)


def test_build_census_and_inactivity():
    pol = fetchkit.load_policies()
    days, bad = fr.census_slots(SCHED, pol)
    ok(SCHED["build_requests_measured"] == {}, "the build makes no network request: the OSCAL catalog is committed (phase 52)")
    ok(not bad and days["1"]["raw.githubusercontent.com"]["requests"] == 3
       and days["2"].get("raw.githubusercontent.com", {}).get("requests", 0) == 0,
       "a building day carries only its jobs' own raw-GitHub reads (Monday 3, Tuesday 0), inside the cap")
    nob = copy.deepcopy(SCHED)
    for s in nob["slots"].values():
        s.pop("builds", None)
    ok("raw.githubusercontent.com" not in fr.census_slots(nob, pol)[0]["2"], "a slot that does not build carries no build load")
    import standards_refresh as sr
    ok(sr.days_since_last_commit(lambda: str(int(time.time()) - 50 * 86400)) == 50
       and sr.days_since_last_commit(lambda: "fatal: not a git repository") is None
       and sr.INACTIVITY_WARN_DAYS == 45, "inactivity: days since HEAD's commit; unknown stays None (never a guessed 0)")


if __name__ == "__main__":
    for fn in (test_workflow_crons, test_pr_and_digest_scripts, test_commit_script, test_build_census_and_inactivity):
        fn()
    print(f"\nweekly workflow tests: {PASS} assertions PASS")
