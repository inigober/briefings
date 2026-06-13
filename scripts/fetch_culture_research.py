#!/usr/bin/env python3
"""Pre-fetch Berlin culture events via OpenAI Responses API + web_search."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from briefing_paths import load_briefing_type
from fetch_openai_research import (
    DEFAULT_MODEL,
    PARALLEL_WORKERS,
    fetch_structured,
    load_yaml,
    log,
    make_client,
    resolve_model,
    topic_by_id,
)
from openai_spend import (
    DailySpendLedger,
    SpendCapExceeded,
    handle_cap_abort,
    resolve_daily_cap,
    usage_from_response,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

CULTURE_SECTION_MIN: dict[str, int] = {
    "exhibitions": 10,
    "film": 6,
    "performing_arts": 5,
    "music": 8,
    "wildcards": 3,
    "advance_radar": 4,
}

CULTURE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "topic_ids": {"type": "array", "items": {"type": "string"}},
        "title": {"type": "string"},
        "venue": {"type": "string"},
        "dates": {"type": "string"},
        "times": {"type": "string"},
        "artists": {"type": "array", "items": {"type": "string"}},
        "official_url": {"type": "string"},
        "closing_soon": {"type": "boolean"},
        "why_candidate": {"type": "string"},
    },
    "required": [
        "id",
        "topic_ids",
        "title",
        "venue",
        "dates",
        "times",
        "artists",
        "official_url",
        "closing_soon",
        "why_candidate",
    ],
    "additionalProperties": False,
}

EVENT_PATH_KEYWORDS = (
    "event",
    "exhibition",
    "exhibitions",
    "stueck",
    "festival",
    "film-screening",
    "programm",
    "program",
    "fair",
    "konzert",
    "concert",
    "ticket",
)

VAGUE_SCHEDULE_MARKERS = ("tba", "various", "check website", "see website", "uhrzeit folgt", "time tbd")


def is_deep_event_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower().rstrip("/")
    if not path:
        return False
    segments = [s for s in path.split("/") if s]
    if not segments or segments in (["en"], ["de"]):
        return False
    if len(segments) == 1 and segments[0] in ("en", "de"):
        return False
    if any(kw in path for kw in EVENT_PATH_KEYWORDS):
        return True
    if len(segments) >= 3:
        return True
    if len(segments) >= 2 and any(ch.isdigit() for ch in segments[-1]):
        return True
    return False


def has_concrete_schedule(dates: str, times: str, *, section_id: str) -> bool:
    d = (dates or "").strip().lower()
    t = (times or "").strip().lower()
    if not d or any(m in d for m in VAGUE_SCHEDULE_MARKERS):
        return False
    if section_id == "exhibitions":
        return True
    if not t or any(m in t for m in VAGUE_SCHEDULE_MARKERS):
        return False
    return True


def mark_item_verified(item: dict) -> None:
    section_id = (item.get("topic_ids") or ["exhibitions"])[0]
    item["verified"] = (
        is_deep_event_url(item.get("official_url") or "")
        and has_concrete_schedule(
            item.get("dates") or "",
            item.get("times") or "",
            section_id=section_id,
        )
    )


SECTION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": CULTURE_ITEM_SCHEMA},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "search_notes": {"type": "string"},
    },
    "required": ["items", "gaps", "search_notes"],
    "additionalProperties": False,
}


from culture_dates import normalize_tuesday_run_date


def culture_week_window(run_date: datetime) -> tuple[datetime, datetime]:
    """Tuesday run → events Wed through following Tue."""
    week_start = run_date + timedelta(days=1)
    week_end = run_date + timedelta(days=7)
    return week_start, week_end


def format_week_range(week_start: datetime, week_end: datetime) -> str:
    if week_start.month == week_end.month:
        return f"{week_start.strftime('%B')} {week_start.day}–{week_end.day}, {week_end.year}"
    return (
        f"{week_start.strftime('%B')} {week_start.day}–"
        f"{week_end.strftime('%B')} {week_end.day}, {week_end.year}"
    )


def build_interests_block(topics_cfg: dict) -> str:
    interests = topics_cfg.get("interests") or {}
    lines = ["## User interests"]
    for key, values in interests.items():
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: {', '.join(values)}")
    avoid = topics_cfg.get("avoid") or []
    if avoid:
        lines.append(f"- Avoid: {', '.join(avoid)}")
    return "\n".join(lines)


def build_thematic_block(topics_cfg: dict) -> str:
    themes = topics_cfg.get("thematic_priorities") or {}
    lines = ["## Thematic priorities"]
    for group, values in themes.items():
        lines.append(f"- {group.replace('_', ' ')}: {', '.join(values)}")
    return "\n".join(lines)


def build_venues_block(sources_cfg: dict) -> str:
    lines = ["## Priority venues"]
    for discipline, venues in (sources_cfg.get("priority_venues") or {}).items():
        lines.append(f"- {discipline}: {', '.join(venues)}")
    festivals = sources_cfg.get("festivals_to_monitor") or []
    if festivals:
        lines.append(f"- Festivals to monitor: {', '.join(festivals)}")
    calendars = sources_cfg.get("primary_calendars") or []
    if calendars:
        lines.append("## Primary calendars (cross-reference)")
        for cal in calendars:
            lines.append(f"- {cal.get('name')}: {cal.get('url')}")
    return "\n".join(lines)


def build_section_prompt(
    *,
    section_id: str,
    topic: dict,
    date_str: str,
    week_label: str,
    min_items: int,
    topics_cfg: dict,
    sources_cfg: dict,
    search_domains: list[str],
) -> str:
    domains = "\n".join(f"- {d}" for d in search_domains)
    return f"""You are pre-fetching candidates for a weekly Berlin culture briefing.

Briefing run date (Tuesday): {date_str}
Event window: {week_label}
Section: {topic.get('name')} ({section_id})
Minimum items: {min_items}

{build_interests_block(topics_cfg)}

{build_thematic_block(topics_cfg)}

{build_venues_block(sources_cfg)}

## Section focus
{topic.get('description', '')}

## Tuesday rule
Include only events occurring Wednesday through the following Monday/Tuesday of the briefing week,
OR exhibitions that remain open through at least Wednesday of that week.
Exclude events already finished before Wednesday.

## Output rules
- official_url MUST be the **specific** event/exhibition page URL (never a venue homepage, aggregators, or social media)
- Include artist names where applicable
- dates and times must be concrete (not "TBA" or "check website") — synthesis trusts items with deep URLs + schedules
- For exhibitions: note opening/closing dates; set closing_soon true if closing within 10 days
- topic_ids MUST start with "{section_id}"
- why_candidate: one sentence on thematic/artistic fit
- Prefer priority venues and primary calendars; cross-reference Index Berlin, Cee Cee, Museumsportal

web_search allowed domains:
{domains}

Return JSON: items, gaps, search_notes."""


def fetch_culture_section(
    *,
    section_id: str,
    date_str: str,
    week_label: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
    spend_ledger: DailySpendLedger | None = None,
    cap_abort: threading.Event | None = None,
) -> tuple[str, dict]:
    topics = topic_by_id(topics_cfg)
    topic = topics.get(section_id)
    if not topic or not topic.get("enabled", True):
        return section_id, {"items": [], "gaps": [], "search_notes": ""}

    min_items = CULTURE_SECTION_MIN.get(section_id, 5)
    allowed = sources_cfg.get("allowed_domains") or []
    prompt = build_section_prompt(
        section_id=section_id,
        topic=topic,
        date_str=date_str,
        week_label=week_label,
        min_items=min_items,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        search_domains=allowed,
    )

    log(f"  [{section_id}] started (min {min_items} items)...")

    if cap_abort and cap_abort.is_set():
        log(f"  [{section_id}] skipped — daily spend cap already reached")
        return section_id, {
            "items": [],
            "gaps": [f"Skipped: daily OpenAI spend cap reached before {section_id}"],
            "search_notes": "skipped: spend_cap",
        }

    if spend_ledger and not spend_ledger.try_reserve_section_budget():
        log(f"  [{section_id}] skipped — insufficient daily budget remaining")
        return section_id, {
            "items": [],
            "gaps": [f"Skipped: daily OpenAI budget reservation exhausted before {section_id}"],
            "search_notes": "skipped: spend_cap",
        }

    client = make_client()
    result, response = fetch_structured(
        client=client,
        model=model,
        prompt=prompt,
        schema=SECTION_RESULT_SCHEMA,
        schema_name=f"culture_section_{section_id}",
        domains=allowed,
    )
    if spend_ledger:
        usage = usage_from_response(response=response, model=model, section=section_id)
        spend_ledger.record_usage(usage)
        if spend_ledger.is_over_cap():
            spend_ledger.mark_cap_exceeded()
            if cap_abort:
                cap_abort.set()
            raise SpendCapExceeded(
                f"Daily OpenAI spend cap reached after {section_id} "
                f"(${spend_ledger.spent_usd:.4f} >= ${spend_ledger.cap_usd:.2f})"
            )

    items = result.get("items") or []
    verified_count = 0
    for item in items:
        tags = [t for t in (item.get("topic_ids") or []) if t != section_id]
        item["topic_ids"] = [section_id, *tags]
        item["ingestion_source"] = "openai"
        mark_item_verified(item)
        if item.get("verified"):
            verified_count += 1
    log(f"  [{section_id}] done ({len(items)} items, {verified_count} verified)")
    return section_id, result


def fetch_all_culture(
    *,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
    spend_ledger: DailySpendLedger | None = None,
) -> dict:
    date_str, run_dt = normalize_tuesday_run_date(date_str)
    week_start, week_end = culture_week_window(run_dt)
    week_label = format_week_range(week_start, week_end)

    topics = topic_by_id(topics_cfg)
    section_ids = [
        sid
        for sid, t in topics.items()
        if t.get("enabled", True) and sid not in ("top_picks",)
    ]

    all_items: list[dict] = []
    all_gaps: list[str] = []
    notes: list[str] = []
    section_counts: dict[str, int] = {}

    if spend_ledger and spend_ledger.cap_enabled():
        log(
            f"  Daily spend cap: ${spend_ledger.cap_usd:.2f} "
            f"(already spent today: ${spend_ledger.spent_usd:.4f})"
        )
        spend_ledger.assert_not_over_cap()

    cap_abort = threading.Event()
    log(f"  Launching {len(section_ids)} culture section fetches (week: {week_label})...")

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(
                fetch_culture_section,
                section_id=sid,
                date_str=date_str,
                week_label=week_label,
                model=model,
                topics_cfg=topics_cfg,
                sources_cfg=sources_cfg,
                spend_ledger=spend_ledger,
                cap_abort=cap_abort,
            ): sid
            for sid in section_ids
        }
        for future in as_completed(futures):
            try:
                sid, result = future.result()
            except SpendCapExceeded:
                cap_abort.set()
                raise
            items = result.get("items") or []
            section_counts[sid] = len(items)
            all_items.extend(items)
            all_gaps.extend(result.get("gaps") or [])
            if result.get("search_notes"):
                notes.append(f"{sid}: {result['search_notes']}")

    return {
        "briefing_type": "berlin-culture",
        "date": date_str,
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": week_end.strftime("%Y-%m-%d"),
        "week_label": week_label,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "items": all_items,
        "gaps": all_gaps,
        "section_counts": section_counts,
        "search_notes": " ".join(notes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Berlin culture research via OpenAI web_search")
    parser.add_argument("--type", default="berlin-culture", help="Briefing type (default: berlin-culture)")
    parser.add_argument("--date", help="YYYY-MM-DD Tuesday run date (default: today UTC)")
    parser.add_argument("--model", default=None, help=f"Override model (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="Print first section prompt only")
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    original = date_str
    date_str, run_dt = normalize_tuesday_run_date(date_str)
    if date_str != original:
        log(
            f"  Warning: {original} is not a Tuesday — using previous Tuesday "
            f"{date_str} for week window and file naming"
        )
    topics_cfg = load_yaml(briefing.topics_path)
    sources_cfg = load_yaml(briefing.sources_path)
    allowed = sources_cfg.get("allowed_domains") or []

    week_start, week_end = culture_week_window(run_dt)
    week_label = format_week_range(week_start, week_end)

    if args.dry_run:
        topics = topic_by_id(topics_cfg)
        topic = topics.get("exhibitions") or {}
        prompt = build_section_prompt(
            section_id="exhibitions",
            topic=topic,
            date_str=date_str,
            week_label=week_label,
            min_items=CULTURE_SECTION_MIN["exhibitions"],
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
            search_domains=allowed,
        )
        log(prompt)
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        log("OPENAI_API_KEY is not set")
        return 1

    model = resolve_model(args.model)
    inbox_dir = briefing.inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-raw.json"

    cap_usd = resolve_daily_cap()
    spend_path = inbox_dir / f"{date_str}-spend.json"
    spend_ledger = DailySpendLedger.load_or_create(spend_path, date_str=date_str, cap_usd=cap_usd)

    log(f"Fetching Berlin culture research for {date_str} (week: {week_label}) with model {model}...")
    try:
        payload = fetch_all_culture(
            date_str=date_str,
            model=model,
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
            spend_ledger=spend_ledger,
        )
    except SpendCapExceeded as exc:
        handle_cap_abort(
            ledger=spend_ledger,
            spend_path=spend_path,
            error_path=inbox_dir / f"{date_str}-spend-cap.error.txt",
            briefing_label=briefing.display_name,
            date_str=date_str,
        )
        log(str(exc))
        return 1
    except Exception as exc:
        spend_ledger.save(spend_path)
        err_path = inbox_dir / f"{date_str}-raw.error.txt"
        err_path.write_text(str(exc) + "\n", encoding="utf-8")
        log(str(exc))
        return 1

    spend_ledger.save(spend_path)
    if spend_ledger.cap_enabled():
        log(
            f"  Run spend total: ${spend_ledger.spent_usd:.4f} "
            f"(daily cap ${spend_ledger.cap_usd:.2f})"
        )

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"Wrote {out_path} ({len(payload.get('items') or [])} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
