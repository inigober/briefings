#!/usr/bin/env python3
"""HTTP-verify music-discovery raw inbox Listen / cover / Dig URLs (post-fetch, pre-slim)."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from briefing_paths import load_briefing_type
from culture_url_verify import check_url_live
from fetch_openai_research import log
from music_dates import normalize_friday_run_date

MIN_VERIFIED_CANDIDATES = 10

URL_FIELDS = ("bandcamp_url", "cover_url", "youtube_url", "dig_url", "writeup_url")
REQUIRED_LIVE_FIELDS = ("bandcamp_url", "cover_url")


def is_http_url(value: str | None) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def verify_music_item(
    item: dict,
    *,
    session=None,
    sleep_ms: int = 80,
) -> dict:
    import time

    notes: list[str] = []
    live_fields: dict[str, str] = {}
    for field in URL_FIELDS:
        raw = item.get(field)
        if raw is None or str(raw).strip() in ("", "null"):
            item[field] = None if field in ("youtube_url", "writeup_url") else item.get(field)
            continue
        url = str(raw).strip()
        if not is_http_url(url):
            notes.append(f"{field}: invalid URL")
            if field in ("youtube_url", "writeup_url"):
                item[field] = None
            else:
                live_fields[field] = "dead"
            continue
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        ok, note = check_url_live(url, session=session)
        if ok:
            live_fields[field] = "live"
        else:
            live_fields[field] = "dead"
            notes.append(f"{field}: {note or 'unreachable'}")
            if field in ("youtube_url", "writeup_url"):
                item[field] = None
                notes.append(f"{field}: cleared (optional)")

    required_ok = all(live_fields.get(field) == "live" for field in REQUIRED_LIVE_FIELDS)
    dig = item.get("dig_url")
    if is_http_url(str(dig or "")) and live_fields.get("dig_url") != "live":
        item["dig_url"] = ""
        notes.append("dig_url: cleared (dead)")

    item["url_live"] = "live" if required_ok else "dead"
    item["url_field_status"] = live_fields
    item["url_verify_notes"] = "; ".join(notes) if notes else "ok"
    item["verified"] = bool(required_ok and item.get("artist") and item.get("release"))
    return item


def verify_music_items(
    items: list[dict],
    *,
    sleep_ms: int = 80,
) -> dict[str, int]:
    import requests

    session = requests.Session()
    checked = live = dead = 0
    for item in items:
        verify_music_item(item, session=session, sleep_ms=sleep_ms)
        checked += 1
        if item.get("verified"):
            live += 1
        else:
            dead += 1
    return {
        "checked": checked,
        "live": live,
        "dead": dead,
        "verified_after": live,
        "skipped": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HTTP-verify music-discovery raw inbox Bandcamp/cover/Dig URLs"
    )
    parser.add_argument("--type", default="music-discovery")
    parser.add_argument("--date", help="YYYY-MM-DD Friday run date (default: today UTC)")
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=80,
        help="Delay between HTTP checks (default: 80ms)",
    )
    parser.add_argument(
        "--min-verified",
        type=int,
        default=MIN_VERIFIED_CANDIDATES,
        help="Fail if fewer verified candidates remain (default: 10)",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    original = date_str
    date_str, _ = normalize_friday_run_date(date_str)
    if date_str != original:
        log(f"  Note: {original} is not a Friday — using week key {date_str}")

    briefing = load_briefing_type(args.type)
    raw_path = briefing.inbox_dir / f"{date_str}-raw.json"
    if not raw_path.is_file():
        log(f"Missing {raw_path} — run fetch_music_research.py first")
        return 1

    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if not items:
        log("No items to verify")
        return 1

    log(f"HTTP-checking Listen/cover/Dig URLs for {len(items)} music items...")
    stats = verify_music_items(items, sleep_ms=args.sleep_ms)
    payload["items"] = items
    payload["url_verified_at"] = datetime.now(timezone.utc).isoformat()
    payload["url_verify_stats"] = stats
    payload["verified_count"] = stats["verified_after"]
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    log(
        f"  URL verify: checked={stats['checked']} live={stats['live']} "
        f"dead={stats['dead']} verified_after={stats['verified_after']}"
    )
    if stats["verified_after"] < args.min_verified:
        log(
            f"FAIL: only {stats['verified_after']} verified music candidates "
            f"(need {args.min_verified}). Dead Bandcamp/cover URLs were dropped."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
