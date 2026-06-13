#!/usr/bin/env python3
"""Verify culture candidate URLs via HTTP (post-fetch, pre-slim)."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
from datetime import datetime, timezone

from briefing_paths import load_briefing_type
from culture_dates import normalize_tuesday_run_date
from culture_url_verify import verify_culture_items
from fetch_openai_research import log


def main() -> int:
    parser = argparse.ArgumentParser(description="HTTP-verify culture raw inbox official_url fields")
    parser.add_argument("--type", default="berlin-culture")
    parser.add_argument("--date", help="YYYY-MM-DD Tuesday run date (default: today UTC)")
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=80,
        help="Delay between HTTP checks (default: 80ms)",
    )
    parser.add_argument(
        "--all-sources",
        action="store_true",
        help="Also check RSS/WordPress items (default: OpenAI only)",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    original = date_str
    date_str, _ = normalize_tuesday_run_date(date_str)
    if date_str != original:
        log(f"  Note: {original} is not a Tuesday — using week key {date_str}")

    briefing = load_briefing_type(args.type)
    raw_path = briefing.inbox_dir / f"{date_str}-raw.json"
    if not raw_path.is_file():
        log(f"Missing {raw_path} — run pre-fetch first")
        return 1

    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if not items:
        log("No items to verify")
        return 0

    log(f"HTTP-checking official_url for {len(items)} culture items...")
    stats = verify_culture_items(
        items,
        sleep_ms=args.sleep_ms,
        only_openai=not args.all_sources,
    )
    payload["url_verified_at"] = datetime.now(timezone.utc).isoformat()
    payload["url_verify_stats"] = stats
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    log(
        f"  URL verify: checked={stats['checked']} live={stats['live']} "
        f"dead={stats['dead']} shallow={stats.get('shallow', 0)} "
        f"verified_after={stats['verified_after']} skipped={stats['skipped']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
