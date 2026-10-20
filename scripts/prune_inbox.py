#!/usr/bin/env python3
"""Delete old pre-fetch intermediates from inbox/ so the repo does not grow forever.

Only bulky intermediates are removed (raw/rss/wordpress/calendar feeds). Files that
later steps or audits still read are kept: *-synthesis.json, *-spend.json,
*-context.json, *-taste-snapshot.md and .gitkeep.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from briefing_paths import REPO_ROOT, load_briefing_type, load_manifest  # noqa: E402

DEFAULT_KEEP_DAYS = 60
PRUNABLE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})-"
    r"(raw|rss|wordpress|wordpress-events|html-calendars|ics)\.json$"
    r"|^(\d{4}-\d{2}-\d{2})-raw\.error\.txt$"
)


def prunable_files(inbox_dir: Path, *, today: date, keep_days: int) -> list[Path]:
    """Files in ``inbox_dir`` older than ``keep_days`` that are safe to delete."""
    if not inbox_dir.is_dir():
        return []
    cutoff = today - timedelta(days=keep_days)
    found: list[Path] = []
    for path in sorted(inbox_dir.iterdir()):
        match = PRUNABLE.match(path.name)
        if not match or not path.is_file():
            continue
        date_str = match.group(1) or match.group(3)
        try:
            file_day = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_day < cutoff:
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune old inbox intermediates")
    parser.add_argument("--days", type=int, default=DEFAULT_KEEP_DAYS, help="Keep this many days")
    parser.add_argument("--dry-run", action="store_true", help="List files without deleting")
    args = parser.parse_args()
    if args.days < 14:
        print("--days must be at least 14 (synthesis and health checks look back that far)")
        return 1

    today = datetime.now(timezone.utc).date()
    removed = 0
    freed = 0
    for type_id in sorted(load_manifest()):
        inbox_dir = load_briefing_type(type_id).inbox_dir
        for path in prunable_files(inbox_dir, today=today, keep_days=args.days):
            size = path.stat().st_size
            rel = path.relative_to(REPO_ROOT)
            print(f"{'would delete' if args.dry_run else 'delete'} {rel}")
            if not args.dry_run:
                path.unlink()
            removed += 1
            freed += size
    verb = "would free" if args.dry_run else "freed"
    print(f"{removed} files, {verb} {freed / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
