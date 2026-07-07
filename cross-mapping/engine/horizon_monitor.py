#!/usr/bin/env python3
"""
horizon_monitor.py — active watcher over the anticipated-updates registry.

The keep-current pipeline (framework_monitor / announcement_monitor) detects changes that
ALREADY happened. This watcher covers changes that are EXPECTED to happen: it reads
`canonical-sources/anticipated_updates.json` (structured horizon records) and

  * `--list` / `--upcoming N`  — the horizon, nearest expected window first;
  * `--overdue`                — records past their expected window (or undated + due for a
                                 manual re-check) that must be re-investigated so a landing
                                 update is never missed or overlooked;
  * `--check`                  — best-effort, offline-safe materialization detection: poll each
                                 watching record's detection URL and flag ones whose expected
                                 artifact appears (a couple have machine-checkable matches; the
                                 rest report reachability + point at source_urls for manual
                                 confirmation).

Pure registry intelligence (list/upcoming/overdue) uses no network and is deterministic given
an "as-of" date (`--as-of YYYY-MM-DD`, default today) so it is unit-testable. Never fabricates
a date — records carry an explicit `expected_window` or `no_fixed_date`.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "canonical-sources" / "anticipated_updates.json"

_FREQ_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 90, "semiannual": 182, "annual": 365}


def load_records() -> list[dict]:
    if not REGISTRY.exists():
        return []
    return json.loads(REGISTRY.read_text(encoding="utf-8")).get("records", [])


def _as_of(arg: str | None) -> date:
    if arg:
        return date.fromisoformat(arg)
    return datetime.now(timezone.utc).date()


def _latest(rec: dict) -> date | None:
    w = rec.get("expected_window")
    if isinstance(w, dict) and w.get("latest"):
        try:
            return date.fromisoformat(w["latest"])
        except ValueError:
            return None
    return None


def _sort_key(rec: dict):
    """Nearest dated window first; undated records after, by confidence then id."""
    lt = _latest(rec)
    return (0, lt.isoformat()) if lt else (1, {"high": "0", "med": "1", "low": "2"}.get(rec.get("confidence"), "3") + rec["id"])


def classify(rec: dict, today: date) -> str:
    """materialized | superseded | overdue | due_review | draft_observed | watching."""
    st = rec.get("status")
    if st in ("materialized", "superseded"):
        return st
    lt = _latest(rec)
    grace = int(rec.get("escalate_after_days", 120))
    if lt is not None and today > lt + timedelta(days=grace):
        return "overdue"
    # Undated records still need periodic manual re-check so nothing is silently forgotten —
    # but only the ones worth chasing: a fixed date is absent yet the item is med/high
    # confidence or carries a lifecycle stage (e.g. the CCM v4.1 flagship). Low-confidence
    # "not announced" items stay passively `watching` until a signal arrives (they'd otherwise
    # flood the report). due_review when last_checked is null or older than 2× the poll cadence.
    if isinstance(rec.get("expected_window"), str):  # no_fixed_date
        worth_review = rec.get("confidence") in ("high", "med") or rec.get("lifecycle_stage")
        if worth_review:
            lc = rec.get("last_checked")
            review_days = 2 * _FREQ_DAYS.get(rec.get("poll_frequency", "quarterly"), 90)
            due = True
            if lc:
                try:
                    due = today > date.fromisoformat(lc[:10]) + timedelta(days=review_days)
                except ValueError:
                    due = True
            if due:
                return "due_review"
    return st if st in ("draft_observed",) else "watching"


def _fmt_window(rec: dict) -> str:
    w = rec.get("expected_window")
    if isinstance(w, dict):
        return w["latest"] if w["earliest"] == w["latest"] else f'{w["earliest"]}…{w["latest"]}'
    return "no_fixed_date"


# ── materialization detection (best-effort, offline-safe) ────────────────────

def _http_ok(url: str, timeout: int = 20) -> tuple[bool, str]:
    if not url:
        return False, "no url"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dbz-horizon/1.0"}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, r.read(4096).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 — offline-safe
        return False, f"{type(e).__name__}"


def _cci_list_version(body: str) -> str | None:
    import re
    m = re.search(r"<version>([^<]+)</version>", body)
    return m.group(1).strip() if m else None


def check_materialization(rec: dict) -> dict:
    """Best-effort: reachable? + a concrete match for the machine-checkable methods."""
    det = rec.get("detection", {}) or {}
    url, method = det.get("url", ""), det.get("method", "")
    ok, body = _http_ok(url)
    result = {"reachable": ok, "verdict": "check_failed" if not ok else "pending"}
    if not ok:
        return result
    if method == "poll_versioned_zip" and rec["feed_id"] == "disa-cci":
        # the detection points at the zip; the version lives in the XML inside, not fetchable
        # cheaply here — reachability is the signal, version compare is done by cci_harvest.
        result["verdict"] = "reachable_verify_via_cci_harvest"
    elif method == "poll_feed_json":
        import re
        fam = (det.get("match") or "").lower()
        hit = "800-53" in body and ("800-53" in fam or "sp 800-53" in fam)
        result["verdict"] = "candidate_materialized" if hit else "pending"
    else:
        result["verdict"] = "reachable_manual_confirm"
    return result


# ── report ───────────────────────────────────────────────────────────────────

def build_report(records: list[dict], today: date) -> dict:
    buckets: dict[str, list[dict]] = {}
    for rec in records:
        buckets.setdefault(classify(rec, today), []).append(rec)
    for k in buckets:
        buckets[k].sort(key=_sort_key)
    return buckets


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="full horizon, grouped by state")
    ap.add_argument("--upcoming", type=int, metavar="N", help="the N nearest dated expectations")
    ap.add_argument("--overdue", action="store_true", help="past-window or due-for-review records")
    ap.add_argument("--summary", action="store_true", help="one-line JSON counts by state")
    ap.add_argument("--check", action="store_true", help="best-effort materialization poll (network)")
    ap.add_argument("--as-of", metavar="YYYY-MM-DD", help="reference date (default today; for tests)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not (a.list or a.upcoming or a.overdue or a.check or a.summary):
        a.list = True

    records = load_records()
    if not records:
        print("[horizon] no anticipated_updates.json registry found")
        return 0
    today = _as_of(a.as_of)
    buckets = build_report(records, today)

    if a.summary:
        print(json.dumps({k: len(v) for k, v in sorted(buckets.items())}))
        return 0

    if a.check:
        watching = [r for r in records if classify(r, today) in ("watching", "due_review", "overdue", "draft_observed")]
        out = []
        for r in watching:
            res = check_materialization(r)
            out.append({"id": r["id"], "artifact": r["artifact"], **res})
        materialized = [o for o in out if o["verdict"] == "candidate_materialized"]
        if a.json:
            print(json.dumps({"checked": len(out), "candidate_materialized": materialized, "all": out}, indent=1))
        else:
            print(f"[horizon] checked {len(out)} watching records")
            for o in materialized:
                print(f"  MATERIALIZED? {o['id']}: {o['artifact']}")
            print(f"  ({sum(1 for o in out if o['reachable'])}/{len(out)} detection URLs reachable; "
                  "verify candidates at their source_urls before ingesting)")
        return 0

    if a.overdue:
        od = buckets.get("overdue", []) + buckets.get("due_review", [])
        if a.json:
            print(json.dumps([{"id": r["id"], "artifact": r["artifact"], "window": _fmt_window(r),
                               "reason": classify(r, today)} for r in od], indent=1))
        else:
            if not od:
                print("[horizon] nothing overdue or due for review")
            for r in od:
                print(f"  {classify(r, today).upper():10} {r['id']}  ({_fmt_window(r)})  {r['artifact']}")
        return 0

    if a.upcoming:
        dated = sorted([r for r in records if _latest(r) and classify(r, today) not in ("superseded",)],
                       key=_sort_key)[:a.upcoming]
        if a.json:
            print(json.dumps([{"id": r["id"], "window": _fmt_window(r), "artifact": r["artifact"],
                               "confidence": r["confidence"]} for r in dated], indent=1))
        else:
            print(f"[horizon] {len(dated)} nearest dated expectations (as of {today}):")
            for r in dated:
                print(f"  {_fmt_window(r):24} [{r['confidence']:4}] {r['id']}: {r['artifact']}")
        return 0

    # --list
    order = ["overdue", "due_review", "draft_observed", "materialized", "watching", "superseded"]
    if a.json:
        print(json.dumps({k: [r["id"] for r in buckets.get(k, [])] for k in order if buckets.get(k)}, indent=1))
    else:
        print(f"[horizon] {len(records)} anticipated updates (as of {today}):")
        for k in order:
            recs = buckets.get(k, [])
            if not recs:
                continue
            print(f"\n== {k} ({len(recs)}) ==")
            for r in recs:
                print(f"  {_fmt_window(r):24} {r['id']}: {r['artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
