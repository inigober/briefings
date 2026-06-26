#!/usr/bin/env python3
"""Fetch venue ICS calendars into typed inbox/."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import requests
import yaml

from briefing_paths import load_briefing_type
from culture_ics import is_ics_calendar, parse_ics_events, ics_event_url
from culture_schedule import extract_schedule_from_text
from fetch_rss import DEFAULT_CULTURE_MAX_AGE_HOURS, is_blocked, normalize_url

DEFAULT_MAX_ITEMS = 20


def log(message: str) -> None:
    print(message, flush=True)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def make_item_id(url: str, section_id: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"ics-{section_id}-{digest}"


def fetch_ics_feed(
    feed_cfg: dict,
    *,
    cutoff: datetime,
    blocklist: list[str],
) -> tuple[list[dict], str | None]:
    url = (feed_cfg.get("url") or "").strip()
    if not url:
        return [], "missing url"

    section_ids = feed_cfg.get("section_ids") or ["music"]
    section_id = section_ids[0]
    venue = feed_cfg.get("venue") or feed_cfg.get("publisher") or urlparse(url).netloc
    max_items = int(feed_cfg.get("max_items") or DEFAULT_MAX_ITEMS)

    headers = {"User-Agent": "Mozilla/5.0 (compatible; BriefingBot/1.0)"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        body = response.text
    except requests.RequestException as exc:
        return [], str(exc)

    if not is_ics_calendar(body):
        return [], "not an ICS calendar"

    items: list[dict] = []
    seen: set[str] = set()
    for event in parse_ics_events(body):
        if len(items) >= max_items:
            break

        start_raw = event.get("dtstart") or ""
        if start_raw:
            try:
                start_dt = datetime.fromisoformat(start_raw)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                if start_dt < cutoff:
                    continue
            except ValueError:
                pass

        link = ics_event_url(event, url)
        if not link.startswith("http") or is_blocked(link, blocklist):
            continue
        norm = normalize_url(link)
        if norm in seen:
            continue
        seen.add(norm)

        title = (event.get("title") or "").strip()
        dates = (event.get("dates") or "").strip()
        times = (event.get("times") or "").strip()
        if not dates:
            dates, inferred_time = extract_schedule_from_text(
                f"{title} {event.get('description') or ''}",
                reference_year=cutoff.year,
            )
            times = times or inferred_time

        event_venue = (event.get("venue") or "").strip() or venue
        why = (event.get("description") or title)[:300]

        items.append(
            {
                "id": make_item_id(norm, section_id),
                "topic_ids": [section_id],
                "title": title,
                "venue": event_venue,
                "dates": dates,
                "times": times,
                "artists": [],
                "official_url": link,
                "closing_soon": False,
                "why_candidate": why,
                "ingestion_source": "ics",
                "programme_feed": True,
                "verified": False,
            }
        )

    return items, None


def fetch_all_ics(
    *,
    date_str: str,
    sources_cfg: dict,
    max_age_hours: int = DEFAULT_CULTURE_MAX_AGE_HOURS,
) -> dict:
    feeds = sources_cfg.get("ics_feeds") or []
    blocklist = sources_cfg.get("blocklist_domains") or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    all_items: list[dict] = []
    feed_notes: list[str] = []
    errors: list[str] = []

    for feed_cfg in feeds:
        label = feed_cfg.get("publisher") or feed_cfg.get("venue") or feed_cfg.get("url", "unknown")
        items, err = fetch_ics_feed(feed_cfg, cutoff=cutoff, blocklist=blocklist)
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
        norm = normalize_url(item.get("official_url") or "")
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append(item)

    return {
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "ics",
        "item_format": "culture",
        "items": deduped,
        "feed_counts": feed_notes,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch ICS venue calendars into typed inbox/")
    parser.add_argument("--type", default="berlin-culture", help="Briefing type")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sources_cfg = load_yaml(briefing.sources_path)
    feeds = sources_cfg.get("ics_feeds") or []

    inbox_dir = briefing.inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-ics.json"

    if not feeds:
        log(f"No ics_feeds configured in {briefing.sources_path} — writing empty inbox file")
        payload = {
            "date": date_str,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "ics",
            "item_format": "culture",
            "items": [],
            "feed_counts": [],
            "errors": [],
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0

    max_age = int(sources_cfg.get("rss_max_age_hours") or DEFAULT_CULTURE_MAX_AGE_HOURS)
    log(f"Fetching ICS for {date_str} ({len(feeds)} feeds, max age {max_age}h)...")
    payload = fetch_all_ics(date_str=date_str, sources_cfg=sources_cfg, max_age_hours=max_age)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"Wrote {out_path} ({len(payload.get('items') or [])} items)")
    if payload.get("errors"):
        log(f"  {len(payload['errors'])} feed(s) had errors (see file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
