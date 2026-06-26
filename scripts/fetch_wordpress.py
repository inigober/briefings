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

from fetch_rss import REGION_DEFAULTS, resolve_news_section_id
from culture_schedule import extract_schedule_from_text

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MAX_AGE_HOURS = 336  # 14 days — weekly culture window
DEFAULT_NEWS_MAX_AGE_HOURS = 72
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


def post_to_news_item(
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
    if len(excerpt) > 600:
        excerpt = excerpt[:597] + "..."

    publisher = feed_cfg.get("publisher") or urlparse(link).netloc
    published_at: str | None = None
    post_dt = parse_post_date(post)
    if post_dt:
        published_at = post_dt.date().isoformat()

    geo = REGION_DEFAULTS.get(section_id, REGION_DEFAULTS["world"])

    return {
        "id": make_item_id(link, section_id),
        "topic_ids": [section_id],
        "headline": title,
        "summary": excerpt or title,
        "why_it_matters": "",
        "broader_context": "",
        "region": feed_cfg.get("region") or geo["region"],
        "country": feed_cfg.get("country") or geo["country"],
        "is_structural": False,
        "is_follow_up": False,
        "material_development": True,
        "ingestion_source": "wordpress",
        "sources": [
            {
                "title": title,
                "url": link,
                "publisher": publisher,
                "published_at": published_at,
            }
        ],
    }


def make_event_item_id(url: str, section_id: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"wpe-{section_id}-{digest}"


def tribe_event_to_culture_item(
    event: dict,
    *,
    feed_cfg: dict,
    section_id: str,
    blocklist: list[str],
) -> dict | None:
    url = (event.get("url") or event.get("website") or "").strip()
    if not url.startswith("http") or is_blocked(url, blocklist):
        return None
    title = strip_html(event.get("title") or "")
    if not title:
        return None
    venue = feed_cfg.get("venue") or (event.get("venue") or {}).get("venue") or feed_cfg.get("publisher") or ""
    if isinstance(venue, dict):
        venue = venue.get("venue") or ""
    dates = (event.get("start_date") or "")[:10]
    if event.get("end_date") and event.get("end_date") != event.get("start_date"):
        dates = f"{event.get('start_date', '')[:10]} – {event.get('end_date', '')[:10]}"
    times = (event.get("start_time") or "").strip()
    desc = strip_html(event.get("description") or "")[:300]
    if not dates:
        dates, inferred = extract_schedule_from_text(f"{title} {desc}")
        times = times or inferred
    return {
        "id": make_event_item_id(url, section_id),
        "topic_ids": [section_id],
        "title": title,
        "venue": str(venue).strip() or urlparse(url).netloc,
        "dates": dates,
        "times": times,
        "artists": [],
        "official_url": url,
        "closing_soon": False,
        "why_candidate": desc or title,
        "ingestion_source": "wordpress_events",
        "programme_feed": True,
        "verified": False,
    }


def wp_rest_event_to_culture_item(
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
    venue = feed_cfg.get("venue") or feed_cfg.get("publisher") or urlparse(link).netloc
    post_dt = parse_post_date(post)
    dates = post_dt.strftime("%d %B %Y") if post_dt else ""
    dates_hint, times = extract_schedule_from_text(
        f"{title} {excerpt}",
        reference_year=post_dt.year if post_dt else None,
    )
    if dates_hint:
        dates = dates_hint
    return {
        "id": make_event_item_id(link, section_id),
        "topic_ids": [section_id],
        "title": title,
        "venue": venue,
        "dates": dates,
        "times": times,
        "artists": [],
        "official_url": link,
        "closing_soon": False,
        "why_candidate": (excerpt or title)[:300],
        "ingestion_source": "wordpress_events",
        "programme_feed": True,
        "verified": False,
    }


def fetch_wordpress_event_feed(
    feed_cfg: dict,
    *,
    cutoff: datetime,
    blocklist: list[str],
) -> tuple[list[dict], str | None]:
    api_kind = (feed_cfg.get("api_kind") or "wp_rest").strip().lower()
    api_url = (feed_cfg.get("url") or "").strip()
    if not api_url:
        return [], "missing url"

    section_ids = feed_cfg.get("section_ids") or ["performing_arts"]
    section_id = section_ids[0]
    max_items = int(feed_cfg.get("max_items") or DEFAULT_MAX_ITEMS)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BriefingBot/1.0)"}
    params: dict[str, str | int] = {"per_page": min(max_items, 100)}

    if api_kind == "wp_rest":
        params["_fields"] = "id,link,title,excerpt,date,date_gmt"
    elif api_kind == "tribe_rest":
        params["per_page"] = min(max_items, 50)

    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        records = response.json()
    except requests.RequestException as exc:
        return [], str(exc)
    except ValueError as exc:
        return [], f"invalid JSON: {exc}"

    if api_kind == "tribe_rest":
        if isinstance(records, dict):
            records = records.get("events") or []
    if not isinstance(records, list):
        return [], "unexpected API response"

    items: list[dict] = []
    seen: set[str] = set()

    for record in records:
        if len(items) >= max_items:
            break
        if not isinstance(record, dict):
            continue

        if api_kind == "tribe_rest":
            start_raw = record.get("start_date") or ""
            try:
                if start_raw:
                    start_dt = datetime.strptime(start_raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    if start_dt < cutoff:
                        continue
            except ValueError:
                pass
            item = tribe_event_to_culture_item(
                record, feed_cfg=feed_cfg, section_id=section_id, blocklist=blocklist
            )
        else:
            post_dt = parse_post_date(record)
            if post_dt and post_dt < cutoff:
                continue
            item = wp_rest_event_to_culture_item(
                record, feed_cfg=feed_cfg, section_id=section_id, blocklist=blocklist
            )
        if not item:
            continue
        norm = normalize_url(item["official_url"])
        if not norm or norm in seen:
            continue
        seen.add(norm)
        items.append(item)

    return items, None


def fetch_all_wordpress_events(
    *,
    date_str: str,
    sources_cfg: dict,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
) -> dict:
    feeds = sources_cfg.get("wordpress_event_feeds") or []
    blocklist = sources_cfg.get("blocklist_domains") or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    all_items: list[dict] = []
    feed_notes: list[str] = []
    errors: list[str] = []

    for feed_cfg in feeds:
        label = feed_cfg.get("publisher") or feed_cfg.get("url", "unknown")
        items, err = fetch_wordpress_event_feed(
            feed_cfg,
            cutoff=cutoff,
            blocklist=blocklist,
        )
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
        "source": "wordpress_events",
        "item_format": "culture",
        "items": deduped,
        "feed_counts": feed_notes,
        "errors": errors,
    }


def fetch_wordpress_feed(
    feed_cfg: dict,
    *,
    cutoff: datetime,
    blocklist: list[str],
    item_format: str = "culture",
) -> tuple[list[dict], str | None]:
    api_url = (feed_cfg.get("url") or "").strip()
    if not api_url:
        return [], "missing url"

    section_ids = feed_cfg.get("section_ids") or (["world"] if item_format == "news" else ["wildcards"])
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

        link = (post.get("link") or "").strip()
        section_id = (
            resolve_news_section_id(feed_cfg, link)
            if item_format == "news"
            else section_ids[0]
        )

        if item_format == "news":
            item = post_to_news_item(
                post,
                feed_cfg=feed_cfg,
                section_id=section_id,
                blocklist=blocklist,
            )
        else:
            item = post_to_culture_item(
                post,
                feed_cfg=feed_cfg,
                section_id=section_id,
                blocklist=blocklist,
            )
        if not item:
            continue

        if item_format == "news":
            norm = normalize_url(item["sources"][0]["url"])
        else:
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
    item_format: str = "culture",
) -> dict:
    feeds = sources_cfg.get("wordpress_feeds") or []
    blocklist = sources_cfg.get("blocklist_domains") or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    all_items: list[dict] = []
    feed_notes: list[str] = []
    errors: list[str] = []

    for feed_cfg in feeds:
        label = feed_cfg.get("publisher") or feed_cfg.get("url", "unknown")
        items, err = fetch_wordpress_feed(
            feed_cfg,
            cutoff=cutoff,
            blocklist=blocklist,
            item_format=item_format,
        )
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
        if item_format == "news":
            url = normalize_url(item["sources"][0]["url"])
        else:
            url = normalize_url(item.get("official_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)

    return {
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "wordpress",
        "item_format": item_format,
        "items": deduped,
        "feed_counts": feed_notes,
        "errors": errors,
    }


def resolve_max_age_hours(sources_cfg: dict, *, briefing_type: str) -> int:
    if sources_cfg.get("wordpress_max_age_hours") is not None:
        return int(sources_cfg["wordpress_max_age_hours"])
    if sources_cfg.get("rss_max_age_hours") is not None:
        return int(sources_cfg["rss_max_age_hours"])
    if briefing_type == "news":
        return DEFAULT_NEWS_MAX_AGE_HOURS
    return DEFAULT_MAX_AGE_HOURS


def resolve_item_format(briefing_type: str) -> str:
    if briefing_type == "news":
        return "news"
    return "culture"


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
    item_format = resolve_item_format(args.type)
    max_age_hours = args.max_age_hours or resolve_max_age_hours(sources_cfg, briefing_type=args.type)

    inbox_dir = briefing.inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-wordpress.json"
    events_path = inbox_dir / f"{date_str}-wordpress-events.json"

    if not feeds:
        log(f"No wordpress_feeds configured in {briefing.sources_path} — writing empty inbox file")
        payload = {
            "date": date_str,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "wordpress",
            "item_format": item_format,
            "items": [],
            "feed_counts": [],
            "errors": [],
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        log(f"Fetching WordPress for {date_str} ({len(feeds)} feeds, max age {max_age_hours}h)...")
        payload = fetch_all_wordpress(
            date_str=date_str,
            sources_cfg=sources_cfg,
            max_age_hours=max_age_hours,
            item_format=item_format,
        )
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"Wrote {out_path} ({len(payload.get('items') or [])} items)")
        if payload.get("errors"):
            log(f"  {len(payload['errors'])} feed(s) had errors (see file)")

    event_feeds = sources_cfg.get("wordpress_event_feeds") or []
    if item_format == "culture" and event_feeds:
        log(f"Fetching WordPress events for {date_str} ({len(event_feeds)} feeds)...")
        events_payload = fetch_all_wordpress_events(
            date_str=date_str,
            sources_cfg=sources_cfg,
            max_age_hours=max_age_hours,
        )
        events_path.write_text(
            json.dumps(events_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        log(f"Wrote {events_path} ({len(events_payload.get('items') or [])} items)")
        if events_payload.get("errors"):
            log(f"  {len(events_payload['errors'])} event feed(s) had errors (see file)")
    elif item_format == "culture":
        events_path.write_text(
            json.dumps(
                {
                    "date": date_str,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "source": "wordpress_events",
                    "item_format": "culture",
                    "items": [],
                    "feed_counts": [],
                    "errors": [],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
