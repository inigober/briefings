#!/usr/bin/env python3
"""Fetch recent posts from WordPress REST APIs into typed inbox/."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any
from urllib.parse import urlparse

import requests
import yaml

from briefing_paths import load_briefing_type

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MAX_AGE_HOURS = 336  # 14 days — weekly culture window
DEFAULT_MAX_ITEMS = 12


def log(message: str) -> None:
    print(message, flush=True)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def strip_html(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", unescape(text))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def is_blocked(url: str, blocklist: list[str]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in blocklist)


def make_item_id(url: str, section_id: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"wp-{section_id}-{digest}"


def parse_post_date(post: dict) -> datetime | None:
    raw = post.get("date_gmt") or post.get("date")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def post_to_culture_item(
    post: dict,
    *,
    feed_cfg: dict,
    section_id: str,
    blocklist: list[str],
) -> dict | None:
    link = (post.get("link") or "").strip()
    if not link.startswith("http") or is_blocked(link, blocklist):
        return None

    title = strip_html((post.get("title") or {}).get("rendered") or "")
    if not title:
        return None

    excerpt = strip_html((post.get("excerpt") or {}).get("rendered") or "")
    if len(excerpt) > 400:
        excerpt = excerpt[:397] + "..."

    venue = feed_cfg.get("venue") or feed_cfg.get("publisher") or urlparse(link).netloc
    why = excerpt or title
    if len(why) > 300:
        why = why[:297] + "..."

    return {
        "id": make_item_id(link, section_id),
        "topic_ids": [section_id],
        "title": title,
        "venue": venue,
        "dates": "",
        "times": "",
        "artists": [],
        "official_url": link,
        "closing_soon": False,
        "why_candidate": why,
        "ingestion_source": "wordpress",
        "verified": False,
    }


def fetch_wordpress_feed(
    feed_cfg: dict,
    *,
    cutoff: datetime,
    blocklist: list[str],
) -> tuple[list[dict], str | None]:
    api_url = (feed_cfg.get("url") or "").strip()
    if not api_url:
        return [], "missing url"

    section_ids = feed_cfg.get("section_ids") or ["wildcards"]
    section_id = section_ids[0]
    max_items = int(feed_cfg.get("max_items") or DEFAULT_MAX_ITEMS)

    params = {"per_page": min(max_items, 100), "_fields": "id,link,title,excerpt,date,date_gmt"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BriefingBot/1.0)"}

    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        posts = response.json()
    except requests.RequestException as exc:
        return [], str(exc)
    except ValueError as exc:
        return [], f"invalid JSON: {exc}"

    if not isinstance(posts, list):
        return [], "unexpected API response"

    items: list[dict] = []
    seen_urls: set[str] = set()

    for post in posts:
        if len(items) >= max_items:
            break
        if not isinstance(post, dict):
            continue

        post_dt = parse_post_date(post)
        if post_dt and post_dt < cutoff:
            continue

        item = post_to_culture_item(
            post,
            feed_cfg=feed_cfg,
            section_id=section_id,
            blocklist=blocklist,
        )
        if not item:
            continue

        norm = normalize_url(item["official_url"])
        if not norm or norm in seen_urls:
            continue
        seen_urls.add(norm)
        items.append(item)

    return items, None


def fetch_all_wordpress(
    *,
    date_str: str,
    sources_cfg: dict,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
) -> dict:
    feeds = sources_cfg.get("wordpress_feeds") or []
    blocklist = sources_cfg.get("blocklist_domains") or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    all_items: list[dict] = []
    feed_notes: list[str] = []
    errors: list[str] = []

    for feed_cfg in feeds:
        label = feed_cfg.get("publisher") or feed_cfg.get("url", "unknown")
        items, err = fetch_wordpress_feed(feed_cfg, cutoff=cutoff, blocklist=blocklist)
        if err:
            errors.append(f"{label}: {err}")
            log(f"  [{label}] skipped — {err}")
            continue
        all_items.extend(items)
        feed_notes.append(f"{label}: {len(items)}")
        log(f"  [{label}] {len(items)} items")

    seen: set[str] = set()
    deduped: list[dict] = []
    for item in all_items:
        url = normalize_url(item.get("official_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)

    return {
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "wordpress",
        "items": deduped,
        "feed_counts": feed_notes,
        "errors": errors,
    }


def resolve_max_age_hours(sources_cfg: dict) -> int:
    if sources_cfg.get("wordpress_max_age_hours") is not None:
        return int(sources_cfg["wordpress_max_age_hours"])
    if sources_cfg.get("rss_max_age_hours") is not None:
        return int(sources_cfg["rss_max_age_hours"])
    return DEFAULT_MAX_AGE_HOURS


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch WordPress posts into typed inbox/")
    parser.add_argument("--type", default="berlin-culture", help="Briefing type")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=None,
        help="Ignore posts older than N hours (default: from sources.yaml or 336)",
    )
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sources_cfg = load_yaml(briefing.sources_path)
    feeds = sources_cfg.get("wordpress_feeds") or []
    max_age_hours = args.max_age_hours or resolve_max_age_hours(sources_cfg)

    inbox_dir = briefing.inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-wordpress.json"

    if not feeds:
        log(f"No wordpress_feeds configured in {briefing.sources_path} — writing empty inbox file")
        payload = {
            "date": date_str,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "wordpress",
            "items": [],
            "feed_counts": [],
            "errors": [],
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0

    log(f"Fetching WordPress for {date_str} ({len(feeds)} feeds, max age {max_age_hours}h)...")
    payload = fetch_all_wordpress(
        date_str=date_str,
        sources_cfg=sources_cfg,
        max_age_hours=max_age_hours,
    )

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"Wrote {out_path} ({len(payload.get('items') or [])} items)")
    if payload.get("errors"):
        log(f"  {len(payload['errors'])} feed(s) had errors (see file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
