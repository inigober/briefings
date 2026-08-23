#!/usr/bin/env python3
"""Verify Berlin restaurant candidates against Google Places API (post-fetch, pre-slim)."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
import os
import time

from briefing_paths import load_briefing_type
from fetch_openai_research import log
from restaurant_dates import normalize_thursday_run_date
from restaurant_maps import verify_restaurant_item


def missing_maps_key_action(*, dry_run: bool) -> str:
    """What to do when GOOGLE_MAPS_API_KEY is empty.

    Returns:
        proceed — key present or dry-run (caller still reads the env var)
        fail_ci — GitHub Actions must not skip verification
        skip_local — local runs without a key keep working
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if api_key or dry_run:
        return "proceed"
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "fail_ci"
    return "skip_local"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify restaurant raw inbox via Google Places API"
    )
    parser.add_argument("--type", default="berlin-restaurants")
    parser.add_argument("--date", help="YYYY-MM-DD run date (default: today UTC; snaps to Thursday week key)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print search queries only; do not call Places API",
    )
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="Do not require a Places place_id for verified:true (not recommended)",
    )
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=120,
        help="Delay between Places API calls (default: 120ms)",
    )
    args = parser.parse_args()

    date_str = args.date or __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m-%d")
    original = date_str
    date_str, _ = normalize_thursday_run_date(date_str)
    if date_str != original:
        log(
            f"  Note: {original} is not a Thursday — using week key {date_str}"
        )

    briefing = load_briefing_type(args.type)
    if args.type != "berlin-restaurants":
        log(f"Only berlin-restaurants is supported (got {args.type})")
        return 1

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    key_action = missing_maps_key_action(dry_run=args.dry_run)
    if key_action == "fail_ci":
        log(
            "GOOGLE_MAPS_API_KEY is not set — failing Places verification in CI. "
            "Add the GitHub secret so restaurant pre-fetch cannot commit an unverified inbox."
        )
        return 1
    if key_action == "skip_local":
        log(
            "GOOGLE_MAPS_API_KEY is not set — skipping Places verification locally. "
            "Add the key in .env to enable hard verification."
        )
        return 0

    raw_path = briefing.inbox_dir / f"{date_str}-raw.json"
    if not raw_path.is_file():
        log(f"Missing {raw_path} — run pre-fetch first")
        return 1

    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []

    if args.dry_run:
        from restaurant_maps import build_search_query

        for item in items:
            log(f"  {item.get('name')}: {build_search_query(item)}")
        return 0

    before = sum(1 for item in items if item.get("verified"))
    log(f"Verifying {len(items)} candidates via Google Places API...")
    strict = not args.lenient
    import requests

    from datetime import datetime, timezone

    session = requests.Session()
    for index, item in enumerate(items):
        verify_restaurant_item(item, api_key=api_key, session=session, strict=strict)
        status = "verified" if item.get("verified") else "rejected"
        log(f"  [{index + 1}/{len(items)}] {item.get('name')}: {status} — {item.get('verification_notes')}")
        if index + 1 < len(items) and args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000)

    payload["verified_count"] = sum(1 for item in items if item.get("verified"))
    payload["maps_verified_at"] = datetime.now(timezone.utc).isoformat()
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    after = payload["verified_count"]
    log(
        f"Wrote {raw_path} — verified {before} → {after} "
        f"({len(items) - after} failed Places checks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
