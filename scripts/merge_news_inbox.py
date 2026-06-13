#!/usr/bin/env python3
"""Merge RSS + WordPress inbox files into news raw.json (no OpenAI)."""

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
from fetch_openai_research import normalize_url

NEWS_SECTION_IDS = ("spain", "germany", "berlin", "world")


def log(message: str) -> None:
    print(message, flush=True)


def item_url(item: dict) -> str:
    for src in item.get("sources") or []:
        url = (src.get("url") or "").strip()
        if url.startswith("http"):
            return url
    return (item.get("official_url") or "").strip()


def merge_inbox_items(*item_lists: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Dedupe by URL; first list wins (rss before wordpress)."""
    seen: set[str] = set()
    merged: list[dict] = []
    counts: dict[str, int] = {"rss": 0, "wordpress": 0}

    for items in item_lists:
        for item in items:
            url = item_url(item)
            if not url.startswith("http"):
                continue
            norm = normalize_url(url)
            if norm in seen:
                continue
            seen.add(norm)
            merged.append(item)
            source = item.get("ingestion_source") or "unknown"
            counts[source] = counts.get(source, 0) + 1

    return merged, counts


def section_counts(items: list[dict]) -> dict[str, int]:
    counts = {sid: 0 for sid in NEWS_SECTION_IDS}
    for item in items:
        tags = item.get("topic_ids") or []
        for sid in NEWS_SECTION_IDS:
            if sid in tags:
                counts[sid] += 1
                break
    return counts


def load_items(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"  Warning: could not read {path.name}: {exc}")
        return []
    return payload.get("items") or []


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge RSS + WordPress into news raw inbox")
    parser.add_argument("--type", default="news")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    if args.type != "news":
        log(f"Briefing type '{args.type}' does not use merge_news_inbox — skipping")
        return 0

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    inbox_dir = briefing.inbox_dir
    rss_path = inbox_dir / f"{date_str}-rss.json"
    wp_path = inbox_dir / f"{date_str}-wordpress.json"
    out_path = inbox_dir / f"{date_str}-raw.json"

    rss_items = load_items(rss_path)
    wp_items = load_items(wp_path)
    merged, ingestion = merge_inbox_items(rss_items, wp_items)
    sections = section_counts(merged)
    publishers: dict[str, int] = {}
    for item in merged:
        for src in item.get("sources") or []:
            pub = src.get("publisher") or "unknown"
            publishers[pub] = publishers.get(pub, 0) + 1

    payload = {
        "briefing_type": "news",
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "rss+wordpress",
        "items": merged,
        "rss_counts": sections,
        "ingestion": ingestion,
        "merge_notes": (
            f"RSS file: {rss_path.name} ({len(rss_items)} items). "
            f"WordPress file: {wp_path.name} ({len(wp_items)} items). "
            f"Merged: {len(merged)}. Ingestion: {ingestion}. "
            f"Section counts: {sections}. Publisher mix: {publishers}."
        ),
    }

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(
        f"Wrote {out_path} — {len(rss_items)} RSS + {len(wp_items)} WordPress → "
        f"{len(merged)} items ({sections})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
