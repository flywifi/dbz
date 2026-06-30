"""
framework-update-check atom — runtime script.

Combines file-level version signals (framework_monitor.py) with
RSS/Atom announcement feed signals (announcement_monitor.py) into a
unified update record per framework. Enables earlier detection of
major revisions, drafts, and public comment periods.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent.parent  # scripts/→update-check/→atoms/→skills/→dbz
_ENGINE = _REPO_ROOT / "cross-mapping" / "engine"

if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))


def _import_engine():
    try:
        import framework_monitor as fm
        import announcement_monitor as am
        return fm, am
    except ImportError as exc:
        raise ImportError(
            f"Cannot import engine modules from {_ENGINE}: {exc}. "
            "Ensure cross-mapping/engine/ is on PYTHONPATH."
        ) from exc


def _get_recent_announcements(
    feed_id: str,
    all_announcements: list,
    days: int = 90,
) -> list:
    """Filter announcements for a feed_id published within `days` days."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results = []
    for entry in all_announcements:
        fw_ids = entry.get("framework_ids", [])
        if feed_id not in fw_ids:
            continue
        published = entry.get("published_at")
        if published:
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if pub_dt < cutoff:
                    continue
            except ValueError:
                pass
        results.append({
            "title": entry.get("title", ""),
            "published_at": entry.get("published_at", ""),
            "url": entry.get("url", ""),
            "change_type": entry.get("change_type", "informational"),
            "human_reviewed": entry.get("human_reviewed", False),
        })
    return sorted(results, key=lambda e: e.get("published_at", ""), reverse=True)


def _get_changelog_recent(
    feed_id: str,
    changelog_path: Path,
    limit: int = 3,
) -> list:
    """Return recent confirmed changelog entries for a framework."""
    if not changelog_path.exists():
        return []
    try:
        with open(changelog_path, encoding="utf-8") as f:
            cl = json.load(f)
    except Exception:
        return []

    entries = [
        e for e in cl.get("entries", [])
        if e.get("framework_id") == feed_id
    ]
    entries.sort(key=lambda e: e.get("change_date", ""), reverse=True)
    return [
        {
            "version_to": e.get("version_to"),
            "change_date": e.get("change_date"),
            "controls_added": len(json.loads(e.get("controls_added", "[]"))),
            "controls_withdrawn": len(json.loads(e.get("controls_withdrawn", "[]"))),
            "human_confirmed": e.get("human_confirmed", False),
        }
        for e in entries[:limit]
    ]


def check_frameworks(
    feed_ids: Optional[List[str]] = None,
    registry_path: Optional[Path] = None,
    announcements_path: Optional[Path] = None,
    changelog_path: Optional[Path] = None,
    dry_run: bool = False,
    announcement_days: int = 90,
) -> dict:
    """
    Run combined file-signal + announcement check for one or more frameworks.

    Parameters
    ----------
    feed_ids           : Framework IDs to check; None = all.
    registry_path      : Path to feed_registry.json.
    announcements_path : Path to announcements_feed.json.
    changelog_path     : Path to framework_changelog.json.
    dry_run            : Pass through to monitors (don't write outputs).
    announcement_days  : How many days back to include announcements.
    """
    fm, am = _import_engine()

    reg = registry_path or (_REPO_ROOT / "canonical-sources" / "feed_registry.json")
    ann_path = announcements_path or (_REPO_ROOT / "canonical-sources" / "announcements_feed.json")
    cl_path = changelog_path or (_REPO_ROOT / "canonical-sources" / "framework_changelog.json")
    monitor_out = _REPO_ROOT / "cross-mapping" / "output" / "framework_updates_feed.json"

    # 1. File-level version signals
    monitor_feed = fm.run_monitor(
        registry_path=reg,
        out_path=monitor_out,
        dry_run=dry_run,
        feed_ids=feed_ids,
    )

    # 2. Announcement signals (refresh feed with latest RSS/Atom entries)
    ann_feed = am.run(
        registry_path=reg,
        output_path=ann_path,
        dry_run=dry_run,
        feed_ids=feed_ids,
        window_days=announcement_days,
    )
    all_announcements = ann_feed.get("entries", []) if isinstance(ann_feed, dict) else []

    # 3. Merge into unified records
    results_by_id = {r["feed_id"]: r for r in monitor_feed.get("results", [])}
    target_ids = feed_ids or list(results_by_id.keys())

    unified_results = []
    human_review_required = False

    for fid in target_ids:
        file_result = results_by_id.get(fid, {})
        file_changed = file_result.get("change_status") == "changed"
        file_confidence = file_result.get("confidence", 0.0)

        announcements = _get_recent_announcements(fid, all_announcements, days=announcement_days)
        changelog = _get_changelog_recent(fid, cl_path)

        # Determine action items
        action_items: list = []
        for ai in monitor_feed.get("action_items", []):
            if ai.get("feed_id") == fid:
                action_items.append(ai.get("manifest_key", ""))

        high_signal_types = {"major_revision", "minor_update", "draft_release", "retired"}
        announcement_high_signal = any(
            a["change_type"] in high_signal_types for a in announcements
        )

        review_needed = file_changed or announcement_high_signal
        if review_needed:
            human_review_required = True

        record = {
            "feed_id": fid,
            "label": file_result.get("label", fid),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "file_signals": {
                "changed": file_changed,
                "confidence": file_confidence,
                "update_notes": file_result.get("update_notes", ""),
                "version_signal": file_result.get("version_signal", ""),
            },
            "announcements": announcements,
            "changelog_recent": changelog,
            "action_items": action_items,
            "human_review_required": review_needed,
        }
        unified_results.append(record)

    changed = [r for r in unified_results if r["human_review_required"]]
    unchanged = [r for r in unified_results if not r["human_review_required"]]

    return {
        "tool": "framework-update-check",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_checked": len(unified_results),
            "action_required": len(changed),
            "unchanged": len(unchanged),
            "errors": monitor_feed.get("summary", {}).get("errors", 0),
        },
        "action_required": changed,
        "unchanged_ids": [r["feed_id"] for r in unchanged],
        "human_review_required": human_review_required,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Combined framework update + announcement check")
    parser.add_argument("--feed", "-f", nargs="+", help="Framework IDs to check")
    parser.add_argument("--registry", help="Path to feed_registry.json")
    parser.add_argument("--announcements", help="Path to announcements_feed.json")
    parser.add_argument("--changelog", help="Path to framework_changelog.json")
    parser.add_argument("--days", type=int, default=90, help="Announcement lookback window (days)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--format", choices=["json", "summary"], default="json")
    args = parser.parse_args()

    result = check_frameworks(
        feed_ids=args.feed,
        registry_path=Path(args.registry) if args.registry else None,
        announcements_path=Path(args.announcements) if args.announcements else None,
        changelog_path=Path(args.changelog) if args.changelog else None,
        dry_run=args.dry_run,
        announcement_days=args.days,
    )

    if args.format == "summary":
        s = result["summary"]
        print(f"Checked {s['total_checked']} frameworks")
        print(f"Action required: {s['action_required']}")
        print(f"Unchanged: {s['unchanged']}")
        for r in result["action_required"]:
            print(f"  [{r['feed_id']}] file_changed={r['file_signals']['changed']} "
                  f"announcements={len(r['announcements'])}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
