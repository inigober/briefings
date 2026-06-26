#!/usr/bin/env python3
"""Fetch venue programme data from HTML listings and per-event ICS (Index Berlin, Silent Green)."""

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
from datetime import date, datetime, timedelta, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests
import yaml

from culture_dates import culture_programme_months, culture_week_date_bounds, normalize_tuesday_run_date
from culture_schedule import extract_schedule_from_text, item_in_briefing_window
from briefing_paths import load_briefing_type
from culture_ics import is_ics_calendar, parse_ics_events
from fetch_rss import DEFAULT_CULTURE_MAX_AGE_HOURS, is_blocked, normalize_url

BASE_INDEX = "https://www.indexberlin.com"
BASE_SILENT_GREEN = "https://www.silent-green.net"
USER_AGENT = "Mozilla/5.0 (compatible; BriefingBot/1.0)"


def log(message: str) -> None:
    print(message, flush=True)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", unescape(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def make_item_id(url: str, section_id: str, prefix: str = "html") -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"{prefix}-{section_id}-{digest}"


def culture_item(
    *,
    section_id: str,
    title: str,
    venue: str,
    dates: str,
    times: str,
    official_url: str,
    why: str,
    ingestion_source: str,
) -> dict:
    return {
        "id": make_item_id(official_url, section_id, prefix=ingestion_source.replace("_", "-")),
        "topic_ids": [section_id],
        "title": title,
        "venue": venue,
        "dates": dates,
        "times": times,
        "artists": [],
        "official_url": official_url,
        "closing_soon": False,
        "why_candidate": why[:300],
        "ingestion_source": ingestion_source,
        "programme_feed": True,
        "verified": False,
    }


def http_get(url: str, *, timeout: int = 30) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_index_berlin_events(
    *,
    blocklist: list[str],
    max_items: int,
    cutoff: datetime,
) -> list[dict]:
    html = http_get(f"{BASE_INDEX}/events/list/")
    ics_paths = list(dict.fromkeys(re.findall(r'href="(/events/list/\d+/[^"]+\.ics)"', html)))
    items: list[dict] = []
    seen: set[str] = set()

    for path in ics_paths:
        if len(items) >= max_items:
            break
        ics_url = f"{BASE_INDEX}{path}"
        page_url = ics_url[:-4]
        if is_blocked(page_url, blocklist):
            continue
        try:
            body = http_get(ics_url)
        except requests.RequestException:
            continue
        if not is_ics_calendar(body):
            continue
        for event in parse_ics_events(body):
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
            title = strip_html(event.get("title") or "")
            if title.lower().startswith("index berlin:"):
                title = title.split(":", 1)[1].strip()
            venue = strip_html(event.get("venue") or "INDEX Berlin event")
            norm = normalize_url(page_url)
            if norm in seen:
                continue
            seen.add(norm)
            items.append(
                culture_item(
                    section_id="wildcards",
                    title=title,
                    venue=venue,
                    dates=event.get("dates") or "",
                    times=event.get("times") or "",
                    official_url=page_url,
                    why=event.get("description") or title,
                    ingestion_source="index_berlin_ics",
                )
            )
            break  # one item per ICS file
    return items


def parse_index_exhibition_detail(html: str, page_url: str) -> dict[str, str] | None:
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    title = strip_html(title_match.group(1)) if title_match else ""
    if not title:
        return None

    text = strip_html(html)
    venue = ""
    venue_match = re.search(
        r"(?:at|@)\s+([A-Z][^|•]{3,80}?)(?:\s+until|\s+Open|\s+Closed|\s+\d{1,2}\.)",
        text,
        re.I,
    )
    if venue_match:
        venue = venue_match.group(1).strip()
    if not venue:
        link_match = re.search(r'href="(/venues/list/\d+/[^"]+)"', html)
        if link_match:
            venue = link_match.group(1).rsplit("/", 1)[-1].replace("-", " ").title()

    dates = ""
    until = re.search(
        r"until\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        text,
        re.I,
    )
    if until:
        dates = f"until {until.group(1)}"
    else:
        open_match = re.search(
            r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\s*[–-]\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})",
            text,
            re.I,
        )
        if open_match:
            dates = f"{open_match.group(1)} – {open_match.group(2)}"
        else:
            dates, _ = extract_schedule_from_text(text)

    return {"title": title, "venue": venue or "Berlin", "dates": dates}


def fetch_index_berlin_exhibitions(
    *,
    blocklist: list[str],
    max_items: int,
) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()

    for filter_id in ("fewdays", "recently"):
        if len(items) >= max_items:
            break
        list_url = f"{BASE_INDEX}/exhibitions/list/filter?cu={filter_id}"
        try:
            html = http_get(list_url)
        except requests.RequestException as exc:
            log(f"  Index Berlin exhibitions ({filter_id}) skipped — {exc}")
            continue
        paths = list(dict.fromkeys(re.findall(r'href="(/exhibitions/list/\d+/[^"]+)"', html)))
        for path in paths:
            if len(items) >= max_items:
                break
            page_url = f"{BASE_INDEX}{path}"
            if is_blocked(page_url, blocklist):
                continue
            norm = normalize_url(page_url)
            if norm in seen:
                continue
            try:
                detail_html = http_get(page_url)
            except requests.RequestException:
                continue
            parsed = parse_index_exhibition_detail(detail_html, page_url)
            if not parsed:
                continue
            seen.add(norm)
            items.append(
                culture_item(
                    section_id="exhibitions",
                    title=parsed["title"],
                    venue=parsed["venue"],
                    dates=parsed["dates"],
                    times="",
                    official_url=page_url,
                    why=f"INDEX Berlin listing ({filter_id}) — {parsed['dates'] or 'see venue page'}",
                    ingestion_source="index_berlin_html",
                )
            )
    return items


def parse_silent_green_detail(html: str, page_url: str) -> dict[str, str] | None:
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    title = strip_html(title_match.group(1)) if title_match else ""
    if not title:
        return None
    text = strip_html(html)
    venue = "Silent Green"
    for label in ("Kuppelhalle", "Betonhalle", "Kantine", "Gesamtes Gelände"):
        if label in text:
            venue = f"Silent Green ({label})"
            break
    dates, times = extract_schedule_from_text(text)
    if not dates:
        for pat in (
            r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+\d{1,2}\s+\w+\s+\d{4})",
            r"(\d{1,2}\.\d{1,2}\.\d{4})",
        ):
            m = re.search(pat, text, re.I)
            if m:
                dates = m.group(1)
                break
    return {"title": title, "venue": venue, "dates": dates, "times": times}


def fetch_silent_green_programme(
    *,
    blocklist: list[str],
    max_items: int,
    run_dt: datetime,
    week_start: date,
    week_end: date,
) -> tuple[list[dict], int]:
    items: list[dict] = []
    seen: set[str] = set()
    dropped_out_of_window = 0

    for year, month in culture_programme_months(run_dt):
        month_url = f"{BASE_SILENT_GREEN}/en/programme/{year}/{month}"
        try:
            html = http_get(month_url)
        except requests.RequestException as exc:
            log(f"  Silent Green {year}/{month} skipped — {exc}")
            continue
        detail_paths = list(
            dict.fromkeys(re.findall(r'href="(/en/programme/detail/[^"]+)"', html))
        )
        for path in detail_paths:
            page_url = urljoin(BASE_SILENT_GREEN, path.replace("&amp;", "&"))
            if is_blocked(page_url, blocklist):
                continue
            norm = normalize_url(page_url.split("?")[0])
            if norm in seen:
                continue
            try:
                detail_html = http_get(page_url)
            except requests.RequestException:
                continue
            parsed = parse_silent_green_detail(detail_html, page_url)
            if not parsed:
                continue
            seen.add(norm)
            candidate = culture_item(
                section_id="music",
                title=parsed["title"],
                venue=parsed["venue"],
                dates=parsed["dates"],
                times=parsed["times"],
                official_url=page_url,
                why=f"Silent Green programme — {parsed['dates'] or 'see venue page'}",
                ingestion_source="silent_green_html",
            )
            if not item_in_briefing_window(candidate, week_start, week_end):
                dropped_out_of_window += 1
                continue
            items.append(candidate)
            if len(items) >= max_items:
                break
        if len(items) >= max_items:
            break
    return items, dropped_out_of_window


def fetch_all_html_calendars(
    *,
    date_str: str,
    sources_cfg: dict,
    run_dt: datetime | None = None,
    max_age_hours: int = DEFAULT_CULTURE_MAX_AGE_HOURS,
) -> dict:
    feeds = sources_cfg.get("html_calendar_feeds") or []
    blocklist = sources_cfg.get("blocklist_domains") or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    run_dt = run_dt or datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    week_start, week_end = culture_week_date_bounds(run_dt)

    all_items: list[dict] = []
    feed_notes: list[str] = []
    errors: list[str] = []
    window_dropped: dict[str, int] = {}

    for feed_cfg in feeds:
        fetcher = (feed_cfg.get("fetcher") or "").strip()
        label = feed_cfg.get("publisher") or fetcher or "unknown"
        max_items = int(feed_cfg.get("max_items") or 40)
        try:
            if fetcher == "index_berlin":
                events = fetch_index_berlin_events(
                    blocklist=blocklist,
                    max_items=min(max_items, 60),
                    cutoff=cutoff,
                )
                exhibitions = fetch_index_berlin_exhibitions(
                    blocklist=blocklist,
                    max_items=max_items,
                )
                items = events + exhibitions
            elif fetcher == "silent_green_programme":
                items, dropped = fetch_silent_green_programme(
                    blocklist=blocklist,
                    max_items=max_items,
                    run_dt=run_dt,
                    week_start=week_start,
                    week_end=week_end,
                )
                if dropped:
                    window_dropped[label] = dropped
                    log(f"  [{label}] dropped {dropped} out-of-window item(s)")
            else:
                errors.append(f"{label}: unknown fetcher {fetcher}")
                continue
        except requests.RequestException as exc:
            errors.append(f"{label}: {exc}")
            log(f"  [{label}] skipped — {exc}")
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
        "source": "html_calendars",
        "item_format": "culture",
        "items": deduped,
        "feed_counts": feed_notes,
        "window_dropped": window_dropped,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch HTML venue calendars into typed inbox/")
    parser.add_argument("--type", default="berlin-culture")
    parser.add_argument("--date", help="YYYY-MM-DD Tuesday run date")
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    from culture_dates import normalize_tuesday_run_date

    date_str, run_dt = normalize_tuesday_run_date(date_str)
    sources_cfg = load_yaml(briefing.sources_path)
    feeds = sources_cfg.get("html_calendar_feeds") or []

    inbox_dir = briefing.inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-html-calendars.json"

    if not feeds:
        log(f"No html_calendar_feeds in {briefing.sources_path} — writing empty file")
        payload = {
            "date": date_str,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "html_calendars",
            "item_format": "culture",
            "items": [],
            "feed_counts": [],
            "errors": [],
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0

    max_age = int(sources_cfg.get("rss_max_age_hours") or DEFAULT_CULTURE_MAX_AGE_HOURS)
    log(f"Fetching HTML calendars for {date_str} ({len(feeds)} sources)...")
    payload = fetch_all_html_calendars(
        date_str=date_str,
        sources_cfg=sources_cfg,
        run_dt=run_dt,
        max_age_hours=max_age,
    )
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"Wrote {out_path} ({len(payload.get('items') or [])} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
