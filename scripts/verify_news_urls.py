#!/usr/bin/env python3
"""Verify news candidate URLs via HTTP (post-fetch, pre-slim)."""

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
from fetch_openai_research import log
from news_url_verify import verify_news_items


def main() -> int:
    parser = argparse.ArgumentParser(description="HTTP-verify news raw inbox source URLs")
    parser.add_argument("--type", default="news")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=80,
        help="Delay between HTTP checks (default: 80ms)",
    )
    parser.add_argument(
        "--openai-only",
        action="store_true",
        help="Only HTTP-check OpenAI items; trust RSS/WordPress URLs (legacy)",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
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

    log(f"HTTP-checking source URLs for {len(items)} news items...")
    stats = verify_news_items(
        items,
        sleep_ms=args.sleep_ms,
        only_openai=args.openai_only,
    )
    payload["url_verified_at"] = datetime.now(timezone.utc).isoformat()
    payload["url_verify_stats"] = stats
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    log(
        f"  URL verify: checked={stats['checked']} live={stats['live']} "
        f"paywalled={stats['paywalled']} dead={stats['dead']} "
        f"suspicious={stats['suspicious']} verified_after={stats['verified_after']} "
        f"skipped={stats['skipped']}"
    )
    if stats["dead"] > 0 or stats["suspicious"] > 0:
        log("FAIL: dead or suspicious news URLs found — fix sources before slim.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
