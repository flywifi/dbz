#!/usr/bin/env python3
"""
ci_status.py — read GitHub Actions state without being able to lie (phase 41).

Why this exists: during the phase-40 close, raw `curl https://api.github.com/...` was
intercepted by the session proxy, which answered with a JSON error body ("GitHub access
is not enabled for this session…"). The ad-hoc pollers parsed that with
`.get('workflow_runs', [])`, so a BLOCKED API printed as "run not scheduled" — repeatedly,
confidently, wrongly. This tool makes that conflation unrepresentable: error, empty, and
data are three distinct outputs with three distinct exit codes.

    exit 0  DATA     at least one run; one line each: <sha10> <status> <conclusion> <created>
    exit 1  EMPTY    HTTP 200 with an empty run list: "no runs found for <query>"
    exit 2  ERROR    HTTP != 200, missing workflow_runs key, transport failure, or missing
                     GITHUB_TOKEN — prints the transport's/API's OWN message verbatim
    exit 3  TIMEOUT  (--wait only) the wait budget elapsed; prints the last observed state

Usage:
    python3 tools/ci_status.py [--branch NAME] [--sha PREFIX] [--wait [SECONDS]] [--selftest]
    python3 tools/ci_status.py --workflow standards-watch.yml [--max-age-days 35]   # cron liveness

Rules learned from the incident, encoded here:
  * Auth comes from $GITHUB_TOKEN (Bearer). No unauthenticated fallback — the proxy
    intercepts those. A missing token is an ERROR that names the variable.
  * Runs are fetched by BRANCH; --sha filters CLIENT-SIDE by full-sha prefix. The server-side
    head_sha filter is deliberately not used, so short-vs-full sha can never matter.
  * --wait prints its expectation up front: GitHub typically schedules a run 1–10 minutes
    after a push. Waiting is not evidence of absence.

Stdlib only (urllib/json/os). The GitHub MCP tools remain the documented alternative.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = "flywifi/dbz"
POLL_SECONDS = 30
DEFAULT_WAIT = 900

# The actual proxy payload captured 2026-08-15 — the body the old pollers misread as
# "no runs". The selftest pins that this tool answers it with ERROR, forever.
_CAPTURED_PROXY_ERROR = (
    '{"message": "GitHub access is not enabled for this session. An org admin must '
    'connect the Claude GitHub App for this organization.", "documentation_url": "x"}')


def _current_branch() -> str:
    return subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def _fetch(branch: str):
    """Return ('data', runs) | ('empty', None) | ('error', message)."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return ("error", "GITHUB_TOKEN is not set in this environment — use the GitHub "
                         "MCP tools instead, or export the token")
    url = (f"https://api.github.com/repos/{REPO}/actions/runs"
           f"?branch={urllib.request.quote(branch, safe='')}&per_page=10")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "dbz-ci-status",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
            code = resp.status
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        return ("error", f"HTTP {e.code}: {detail}")
    except Exception as e:  # transport/proxy failure is an ERROR, never "no runs"
        return ("error", f"{type(e).__name__}: {e}")
    return classify(code, body)


def _fetch_workflow(workflow: str):
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return ("error", "GITHUB_TOKEN is not set in this environment — use the GitHub MCP tools instead")
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{urllib.request.quote(workflow, safe='')}/runs?per_page=5"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "Accept": "application/vnd.github+json", "User-Agent": "dbz-ci-status"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return classify(resp.status, resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return ("error", f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except Exception as e:  # transport/proxy failure is an ERROR, never "no runs"
        return ("error", f"{type(e).__name__}: {e}")


def workflow_liveness(runs: list, max_age_days: int, now: float | None = None) -> tuple:
    """('alive'|'stale', detail) from the newest completed run's created_at."""
    from datetime import datetime, timezone
    done = [r for r in runs if r.get("status") == "completed" and r.get("created_at")]
    if not done:
        return "stale", "no completed run"
    newest = max(datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) for r in done)
    age = ((now or datetime.now(timezone.utc).timestamp()) - newest.timestamp()) / 86400
    return ("alive" if age <= max_age_days else "stale"), f"newest completed run {newest:%Y-%m-%d} ({age:.0f} d ago)"


def classify(status_code: int, body: str):
    """The three-state contract, pure so --selftest can pin it."""
    if status_code != 200:
        return ("error", f"HTTP {status_code}: {body[:300]}")
    try:
        payload = json.loads(body)
    except ValueError:
        return ("error", f"non-JSON body: {body[:200]}")
    if "workflow_runs" not in payload:
        # THE incident shape: a 200-ish JSON answer that is not a runs list.
        return ("error", str(payload.get("message", payload))[:300])
    runs = payload["workflow_runs"]
    if not runs:
        return ("empty", None)
    return ("data", runs)


def _print_runs(runs, sha_prefix: str | None) -> int:
    shown = 0
    for r in runs:
        if sha_prefix and not r.get("head_sha", "").startswith(sha_prefix):
            continue
        print(f"{r.get('head_sha', '')[:10]} {r.get('status'):12} "
              f"{str(r.get('conclusion')):9} {r.get('created_at')}")
        shown += 1
    return shown


def selftest() -> int:
    cases = [
        (200, _CAPTURED_PROXY_ERROR, "error"),
        (200, '{"total_count": 0, "workflow_runs": []}', "empty"),
        (200, '{"workflow_runs": [{"head_sha": "abc", "status": "completed", '
              '"conclusion": "success", "created_at": "t"}]}', "data"),
        (403, '{"message": "rate limited"}', "error"),
        (200, 'not json at all', "error"),
    ]
    bad = 0
    for code, body, want in cases:
        got = classify(code, body)[0]
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok ' if ok else 'FAIL'} classify(HTTP {code}, {body[:42]!r}...) "
              f"= {got} (want {want})")
    bad += selftest_liveness()
    print(f"[ci-status selftest] {'PASS' if not bad else f'FAIL ({bad})'} — error, empty "
          "and data are distinct states; workflow liveness alive/stale")
    return 1 if bad else 0


def selftest_liveness() -> int:
    from datetime import datetime, timezone
    now = datetime(2026, 11, 4, tzinfo=timezone.utc).timestamp()
    cases = [([{"status": "completed", "created_at": "2026-11-03T14:25:03Z"}], "alive"),
             ([{"status": "completed", "created_at": "2026-09-20T00:00:00Z"}], "stale"),
             ([{"status": "in_progress", "created_at": "2026-11-04T00:00:00Z"}], "stale")]
    bad = 0
    for runs, want in cases:
        got = workflow_liveness(runs, 35, now)[0]
        bad += got != want
        print(f"  {'ok ' if got == want else 'FAIL'} liveness({runs[0]['status']}, {runs[0]['created_at'][:10]}) = {got}")
    return bad


def main() -> int:
    args = sys.argv[1:]
    if "--selftest" in args:
        return selftest()
    if "--workflow" in args:
        # cron liveness for a scheduled workflow (e.g. standards-watch.yml): alive | stale
        wf = args[args.index("--workflow") + 1]
        max_age = int(args[args.index("--max-age-days") + 1]) if "--max-age-days" in args else 35
        state, detail = _fetch_workflow(wf)
        if state == "error":
            print(f"ERROR: {detail}")
            return 2
        if state == "empty":
            print(f"no runs found for workflow {wf!r}")
            return 1
        verdict, why = workflow_liveness(detail, max_age)
        print(f"{wf}: {verdict} — {why} (max age {max_age} d)")
        return 0 if verdict == "alive" else 1
    branch = _current_branch()
    if "--branch" in args:
        branch = args[args.index("--branch") + 1]
    sha = None
    if "--sha" in args:
        sha = args[args.index("--sha") + 1]
    wait = 0
    if "--wait" in args:
        i = args.index("--wait")
        wait = (int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit()
                else DEFAULT_WAIT)
        print(f"note: GitHub typically schedules a run 1-10 minutes after a push; "
              f"waiting up to {wait}s")

    deadline = time.monotonic() + wait
    last = "unqueried"
    while True:
        state, detail = _fetch(branch)
        if state == "error":
            print(f"ERROR: {detail}")
            return 2
        if state == "data":
            shown = _print_runs(detail, sha)
            if shown:
                incomplete = any(
                    r.get("status") != "completed" for r in detail
                    if not sha or r.get("head_sha", "").startswith(sha))
                if not incomplete or wait == 0:
                    return 0
                last = "runs in progress"
            else:
                last = f"runs exist but none match sha prefix {sha!r}"
        else:
            last = "no runs found"
        if wait == 0 or time.monotonic() >= deadline:
            if last == "no runs found":
                print(f"no runs found for branch {branch!r}"
                      + (f" sha {sha!r}" if sha else ""))
                return 1
            print(f"TIMEOUT after {wait}s — last state: {last}")
            return 3
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
