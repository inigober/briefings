#!/usr/bin/env python3
"""Dedicated music pre-fetch pass for Berlin culture — runs when music is thin."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any

from briefing_paths import load_briefing_type
from culture_calendar import culture_openai_min, programme_counts
from culture_dates import culture_week_window, format_week_range, normalize_tuesday_run_date
from fetch_culture_research import (
    COMBINED_RESULT_SCHEMA,
    build_structure_phase_prompt,
    enrich_candidate,
    load_calendar_items,
    section_counts,
    section_min_items,
)
from fetch_openai_research import (
    DEFAULT_MODEL,
    fetch_structured,
    fetch_web_research,
    load_yaml,
    log,
    make_client,
    resolve_model,
    topic_by_id,
)
from openai_spend import (
    DailySpendLedger,
    SpendCapExceeded,
    count_web_search_calls,
    usage_from_response,
)

MUSIC_SEARCH_MAX_TOOL_CALLS = 2
MUSIC_SUPPLEMENT_MIN_ITEMS = 3


def build_music_search_prompt(
    *,
    date_str: str,
    week_label: str,
    topics_cfg: dict,
    sources_cfg: dict,
    search_domains: list[str],
    calendar_items: list[dict],
    existing_music_titles: list[str],
) -> str:
    programme_block = ""
    entries = (sources_cfg.get("programme_urls") or {}).get("music") or []
    if entries:
        programme_block = "## Music programme pages (web_search REQUIRED)\n"
        for entry in entries:
            venue = entry.get("venue") or "Venue"
            url = entry.get("url") or ""
            programme_block += f"- {venue}: {url}\n"

    avoid = ", ".join(existing_music_titles[:12]) or "(none yet)"
    interests = topics_cfg.get("interests") or {}
    music_tags = (interests.get("music_primary") or []) + (interests.get("music_secondary") or [])

    return f"""You are researching Berlin **music** events for a weekly culture briefing. PHASE 1: web research only.

Briefing run date (Tuesday): {date_str}
Event window: {week_label}
Target: at least {MUSIC_SUPPLEMENT_MIN_ITEMS} **atomic** music events with artist names and concrete dates.

## Reader music interests
{", ".join(music_tags[:12])}

{programme_block}
## Already collected (do not duplicate)
{avoid}

## Your task (web_search REQUIRED — at least 2 searches)
Search **different** music programme URLs above. Prefer KM28, Silent Green, MONOM, Morphine Raum, Ausland, Arkaoda, A-Trane, Pierre Boulez Saal.

For each qualifying concert / listening session / DJ set in the event window, record:
- title, venue, dates, times, artists
- official_url (specific event page)
- series_id when part of a festival (slug); event_kind: single or festival_event
- one-line why it fits

## Tuesday rule
Events Wed through following Mon/Tue, or ongoing exhibitions do not belong here — **dated music only**.

Return plain-text research notes — NOT JSON. web_search domains: {len(search_domains)} allowed."""


def run_music_supplement(
    *,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
    calendar_items: list[dict],
    existing_items: list[dict],
    spend_ledger: DailySpendLedger | None = None,
) -> dict[str, Any]:
    date_str, run_dt = normalize_tuesday_run_date(date_str)
    week_start, week_end = culture_week_window(run_dt)
    week_label = format_week_range(week_start, week_end)
    allowed = sources_cfg.get("allowed_domains") or []

    music_topic = topic_by_id(topics_cfg).get("music") or {}
    base_min = section_min_items(music_topic)
    prog_counts = programme_counts(calendar_items, sources_cfg)
    target = culture_openai_min("music", prog_counts.get("music", 0), base_min)
    target = max(target, MUSIC_SUPPLEMENT_MIN_ITEMS)

    current_music = [
        (item.get("title") or "").strip()
        for item in existing_items
        if (item.get("topic_ids") or ["exhibitions"])[0] == "music"
    ]
    if len(current_music) >= target:
        log(f"  Music supplement skipped — already {len(current_music)} items (target {target})")
        return {"items": [], "web_search_calls": 0, "skipped": True}

    log(f"  Music supplement: {len(current_music)} items, target {target} — running focused web_search...")

    if spend_ledger:
        spend_ledger.assert_not_over_cap()

    client = make_client()
    prompt = build_music_search_prompt(
        date_str=date_str,
        week_label=week_label,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        search_domains=allowed,
        calendar_items=calendar_items,
        existing_music_titles=current_music,
    )
    notes, search_response = fetch_web_research(
        client=client,
        model=model,
        prompt=prompt,
        domains=allowed,
        require_web_search=True,
        max_tool_calls=MUSIC_SEARCH_MAX_TOOL_CALLS,
        search_context_size="low",
    )
    calls = count_web_search_calls(search_response)
    if calls == 0:
        raise RuntimeError("Music supplement aborted: 0 web_search calls.")

    if spend_ledger:
        usage = usage_from_response(response=search_response, model=model, section="culture_music_search")
        spend_ledger.record_usage(usage)
        spend_ledger.assert_not_over_cap()

    structure_prompt = build_structure_phase_prompt(
        date_str=date_str,
        week_label=week_label,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        calendar_items=calendar_items,
        state_dir=None,
        research_notes=f"## Section: music (supplement)\n{notes}",
    )
    result, structure_response = fetch_structured(
        client=client,
        model=model,
        prompt=structure_prompt,
        schema=COMBINED_RESULT_SCHEMA,
        schema_name="culture_music_supplement",
        domains=[],
        enable_web_search=False,
    )
    if spend_ledger:
        usage = usage_from_response(response=structure_response, model=model, section="culture_music_structure")
        spend_ledger.record_usage(usage)

    raw_items = result.get("items") or []
    music_items = []
    for item in raw_items:
        topic_ids = item.get("topic_ids") or []
        if topic_ids and topic_ids[0] != "music":
            continue
        if not topic_ids:
            item["topic_ids"] = ["music"]
        music_items.append(enrich_candidate(dict(item)))

    log(f"  Music supplement done: {calls} web_search call(s), {len(music_items)} music items")
    return {
        "items": music_items,
        "web_search_calls": calls,
        "skipped": False,
        "gaps": result.get("gaps") or [],
        "search_notes": result.get("search_notes") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run focused Berlin culture music pre-fetch")
    parser.add_argument("--type", default="berlin-culture")
    parser.add_argument("--date", help="YYYY-MM-DD Tuesday run date")
    parser.add_argument("--model", default=None)
    parser.add_argument("--merge-raw", action="store_true", help="Merge results into existing -raw.json")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        log("OPENAI_API_KEY is not set")
        return 1

    briefing = load_briefing_type(args.type)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_str, _ = normalize_tuesday_run_date(date_str)
    topics_cfg = load_yaml(briefing.topics_path)
    sources_cfg = load_yaml(briefing.sources_path)
    model = resolve_model(args.model)

    calendar_items = load_calendar_items(briefing.inbox_dir, date_str)
    existing_items: list[dict] = []
    raw_path = briefing.inbox_dir / f"{date_str}-raw.json"
    if raw_path.is_file():
        existing_items = json.loads(raw_path.read_text(encoding="utf-8")).get("items") or []

    try:
        result = run_music_supplement(
            date_str=date_str,
            model=model,
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
            calendar_items=calendar_items,
            existing_items=existing_items,
        )
    except Exception as exc:
        log(str(exc))
        return 1

    if args.merge_raw and result.get("items") and raw_path.is_file():
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        payload["items"] = (payload.get("items") or []) + result["items"]
        payload["section_counts"] = section_counts(payload["items"], topics_cfg)
        payload["music_supplement"] = {
            "web_search_calls": result.get("web_search_calls"),
            "items_added": len(result["items"]),
        }
        raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"Merged {len(result['items'])} music items into {raw_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
