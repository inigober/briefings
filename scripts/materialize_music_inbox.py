#!/usr/bin/env python3
"""Materialize music-discovery inbox files from the committed taste cache.

Cloud Friday pre-fetch uses this so synthesis does not depend on a same-day
Mac taste refresh. Update the cache anytime via local
``refresh_taste_and_bridge.py`` (Thursday launchd is optional).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from briefing_paths import REPO_ROOT, load_briefing_type  # noqa: E402
from music_dates import normalize_friday_run_date  # noqa: E402

CACHE_DIR = REPO_ROOT / "state" / "music-discovery" / "taste-cache"
CACHE_CONTEXT = CACHE_DIR / "context.json"
CACHE_SNAPSHOT = CACHE_DIR / "taste-snapshot.md"


def materialize(run_date: str, *, dry_run: bool = False) -> tuple[Path, Path]:
    friday, _ = normalize_friday_run_date(run_date)
    if not CACHE_CONTEXT.exists() or not CACHE_SNAPSHOT.exists():
        raise FileNotFoundError(
            f"Missing taste cache under {CACHE_DIR}. "
            "Run personal refresh_taste_and_bridge.py --push-cache once."
        )

    bt = load_briefing_type("music-discovery")
    bt.inbox_dir.mkdir(parents=True, exist_ok=True)
    dest_context = bt.inbox_dir / f"{friday}-context.json"
    dest_snapshot = bt.inbox_dir / f"{friday}-taste-snapshot.md"

    data = json.loads(CACHE_CONTEXT.read_text(encoding="utf-8"))
    data["run_date"] = friday
    data["built_at"] = datetime.now(timezone.utc).isoformat()
    data["briefing_type"] = "music-discovery"
    data.setdefault("source", {})["from_taste_cache"] = True
    data["source"]["taste_cache_path"] = str(CACHE_CONTEXT.relative_to(REPO_ROOT))

    print(f"cache → {dest_context.relative_to(REPO_ROOT)}")
    print(f"cache → {dest_snapshot.relative_to(REPO_ROOT)}")
    print(f"axes={len(data.get('axes') or [])} skip={len(data.get('skip_list') or [])} "
          f"library_albums={(data.get('library_skip') or {}).get('album_count')}")

    if dry_run:
        return dest_context, dest_snapshot

    dest_context.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copyfile(CACHE_SNAPSHOT, dest_snapshot)
    return dest_context, dest_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Any date in the target week (normalized to Friday)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        materialize(args.date, dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
