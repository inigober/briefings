#!/usr/bin/env python3
"""Fetch recent headlines from RSS feeds configured per briefing type."""

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
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urlparse

import feedparser
import yaml

from briefing_paths import load_briefing_type

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MAX_AGE_HOURS = 72
DEFAULT_MAX_ITEMS = 12

REGION_DEFAULTS: dict[str, dict[str, str]] = {
    "spain": {"region": "Spain", "country": "Spain"},
    "germany": {"region": "Germany", "country": "Germany"},
    "berlin": {"region": "Berlin", "country": "Germany"},
    "world": {"region": "International", "country": ""},
}


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


def parse_entry_date(entry: Any) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (TypeError, ValueError, IndexError):
                pass
    return None


def entry_url(entry: Any) -> str | None:
    link = getattr(entry, "link", None)
    if link:
        return link.strip()
    for link_obj in getattr(entry, "links", []) or []:
        href = link_obj.get("href")
        if href:
            return href.strip()
    return None


def make_item_id(url: str, section_id: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"rss-{section_id}-{digest}"


def entry_to_item(
    entry: Any,
    *,
    feed_cfg: dict,
    section_id: str,
    blocklist: list[str],
) -> dict | None:
    url = entry_url(entry)
    if not url or not url.startswith("http"):
        return None
    if is_blocked(url, blocklist):
        return None

    title = strip_html(getattr(entry, "title", "") or "").strip()
    if not title:
        return None

    summary = strip_html(
        getattr(entry, "summary", "")
        or getattr(entry, "description", "")
        or ""
    )
    if len(summary) > 600:
        summary = summary[:597] + "..."

    publisher = feed_cfg.get("publisher") or urlparse(url).netloc
    published_at: str | None = None
    entry_dt = parse_entry_date(entry)
    if entry_dt:
        published_at = entry_dt.date().isoformat()

    geo = REGION_DEFAULTS.get(section_id, REGION_DEFAULTS["world"])

    return {
        "id": make_item_id(url, section_id),
        "topic_ids": [section_id],
        "headline": title,
        "summary": summary or title,
        "why_it_matters": "",
        "broader_context": "",
        "region": feed_cfg.get("region") or geo["region"],
        "country": feed_cfg.get("country") or geo["country"],
        "is_structural": False,
        "is_follow_up": False,
        "material_development": True,
        "ingestion_source": "rss",
        "sources": [
            {
                "title": title,
                "url": url,
                "publisher": publisher,
                "published_at": published_at,
            }
        ],
    }


def fetch_feed(
    feed_cfg: dict,
    *,
    cutoff: datetime,
    blocklist: list[str],
) -> tuple[list[dict], str | None]:
    url = feed_cfg.get("url")
    if not url:
        return [], "missing url"

    section_ids = feed_cfg.get("section_ids") or ["world"]
    section_id = section_ids[0]
    max_items = int(feed_cfg.get("max_items") or DEFAULT_MAX_ITEMS)

    agent = "Mozilla/5.0 (compatible; BriefingBot/1.0)"
    try:
        parsed = feedparser.parse(url, agent=agent)
    except Exception as exc:
        return [], str(exc)

    if getattr(parsed, "bozo", False) and not parsed.entries:
        err = getattr(parsed, "bozo_exception", None)
        return [], str(err) if err else "parse error"

    items: list[dict] = []
    seen_urls: set[str] = set()

    for entry in parsed.entries:
        if len(items) >= max_items:
            break

        entry_dt = parse_entry_date(entry)
        if entry_dt and entry_dt < cutoff:
            continue

        item = entry_to_item(entry, feed_cfg=feed_cfg, section_id=section_id, blocklist=blocklist)
        if not item:
            continue

        norm = normalize_url(item["sources"][0]["url"])
        if norm in seen_urls:
            continue
        seen_urls.add(norm)
        items.append(item)

    return items, None


def fetch_all_rss(
    *,
    date_str: str,
    sources_cfg: dict,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
) -> dict:
    feeds = sources_cfg.get("rss_feeds") or []
    blocklist = sources_cfg.get("blocklist_domains") or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    all_items: list[dict] = []
    feed_notes: list[str] = []
    errors: list[str] = []

    for feed_cfg in feeds:
        label = feed_cfg.get("publisher") or feed_cfg.get("url", "unknown")
        items, err = fetch_feed(feed_cfg, cutoff=cutoff, blocklist=blocklist)
        if err:
            errors.append(f"{label}: {err}")
            log(f"  [{label}] skipped — {err}")
            continue
        all_items.extend(items)
        feed_notes.append(f"{label}: {len(items)}")
        log(f"  [{label}] {len(items)} items")

    # Dedupe across feeds (first wins)
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in all_items:
        url = normalize_url(item["sources"][0]["url"])
        if url in seen:
            continue
        seen.add(url)
        deduped.append(item)

    return {
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "rss",
        "items": deduped,
        "feed_counts": feed_notes,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch RSS headlines into typed inbox/")
    parser.add_argument("--type", default="news", help="Briefing type (default: news)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"Ignore items older than N hours (default: {DEFAULT_MAX_AGE_HOURS})",
    )
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    if not briefing.prefetch_rss:
        log(f"Briefing type '{args.type}' does not use RSS pre-fetch — skipping")
        return 0

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sources_cfg = load_yaml(briefing.sources_path)
    feeds = sources_cfg.get("rss_feeds") or []

    inbox_dir = briefing.inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-rss.json"

    if not feeds:
        log(f"No rss_feeds configured in {briefing.sources_path} — writing empty inbox file")
        payload = {
            "date": date_str,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "rss",
            "items": [],
            "feed_counts": [],
            "errors": [],
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0

    log(f"Fetching RSS for {date_str} ({len(feeds)} feeds, max age {args.max_age_hours}h)...")
    payload = fetch_all_rss(
        date_str=date_str,
        sources_cfg=sources_cfg,
        max_age_hours=args.max_age_hours,
    )

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"Wrote {out_path} ({len(payload.get('items') or [])} items)")
    if payload.get("errors"):
        log(f"  {len(payload['errors'])} feed(s) had errors (see file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
