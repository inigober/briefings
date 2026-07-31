#!/usr/bin/env python3
"""Pre-fetch Berlin culture events via required web_search, then JSON structuring.

RSS/WordPress calendars merge first; venue programme URLs and events index steer novelty.
HTTP URL verification runs via verify_culture_urls.py before slim.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from briefing_paths import REPO_ROOT, load_briefing_type
from culture_calendar import (
    SECTIONS_REQUIRING_WEB_SEARCH,
    build_novelty_block,
    build_press_warehouse_block,
    build_programme_urls_block,
    build_programme_warehouse_block,
    culture_openai_min,
    enrich_culture_metadata,
    mark_item_verified,
    press_counts,
    programme_counts,
)
from culture_dates import culture_week_window, format_week_range, normalize_tuesday_run_date
from fetch_openai_research import (
    DEFAULT_MODEL,
    fetch_structured,
    fetch_web_research,
    load_yaml,
    log,
    make_client,
    normalize_url,
    resolve_model,
    topic_by_id,
)
from openai_spend import (
    CULTURE_FETCH_BUDGET_RESERVE_USD,
    DailySpendLedger,
    SpendCapExceeded,
    count_web_search_calls,
    handle_cap_abort,
    resolve_daily_cap,
    usage_from_response,
)

CULTURE_OPENAI_MIN_FLOOR = 2

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
        "series_id": {"type": "string"},
        "event_kind": {
            "type": "string",
            "enum": ["single", "festival_overview", "festival_event"],
        },
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
        "series_id",
        "event_kind",
    ],
    "additionalProperties": False,
}

COMBINED_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": CULTURE_ITEM_SCHEMA},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "search_notes": {"type": "string"},
    },
    "required": ["items", "gaps", "search_notes"],
    "additionalProperties": False,
}


def section_min_items(topic: dict) -> int:
    return int(topic.get("prefetch_min") or 5)


def build_compact_interests_block(topics_cfg: dict) -> str:
    interests = topics_cfg.get("interests") or {}
    parts = [f"{key.replace('_', ' ')}: {', '.join(values[:4])}" for key, values in interests.items()]
    avoid = topics_cfg.get("avoid") or []
    lines = ["## Reader interests (compact)", "; ".join(parts)]
    if avoid:
        lines.append(f"Avoid: {', '.join(avoid[:8])}")
    return "\n".join(lines)


def build_compact_themes_block(topics_cfg: dict) -> str:
    themes = topics_cfg.get("thematic_priorities") or {}
    parts = [f"{group}: {', '.join(values[:5])}" for group, values in themes.items()]
    return "## Thematic priorities\n" + "; ".join(parts)


def build_section_requirements(
    topics_cfg: dict,
    *,
    programme_coverage: dict[str, int] | None = None,
) -> str:
    programme_coverage = programme_coverage or {}
    lines = ["## Section targets (assign each candidate to one primary topic_id)"]
    for topic in topics_cfg.get("topics") or []:
        if not topic.get("enabled", True):
            continue
        sid = topic.get("id", "")
        if sid == "top_picks":
            continue
        base_min = section_min_items(topic)
        openai_min = culture_openai_min(sid, programme_coverage.get(sid, 0), base_min)
        optional = " (optional — include only if genuinely relevant)" if topic.get("optional") else ""
        prog_count = programme_coverage.get(sid, 0)
        if prog_count > 0 and openai_min < base_min:
            min_note = (
                f"at least {openai_min} new candidates (reduced from {base_min} — "
                f"{prog_count} venue-programme warehouse items)"
            )
        else:
            min_note = f"at least {openai_min} candidates"
        desc = str(topic.get("description", "")).strip()
        if len(desc) > 180:
            desc = desc[:177] + "..."
        lines.append(
            f"- **{topic.get('name')}** (`{sid}`): {min_note}{optional}\n  {desc}"
        )
    return "\n".join(lines)


CULTURE_SEARCH_MAX_TOOL_CALLS = 3
CULTURE_SEARCH_MIN_CALLS = 4
CULTURE_CORE_SEARCH_SECTIONS = ("music", "exhibitions", "film", "performing_arts")


def build_section_programme_block(sources_cfg: dict, section_id: str) -> str:
    entries = (sources_cfg.get("programme_urls") or {}).get(section_id) or []
    if not entries:
        return ""
    label = section_id.replace("_", " ")
    lines = [f"### Programme pages ({label})"]
    for entry in entries:
        venue = entry.get("venue") or "Venue"
        url = entry.get("url") or ""
        note = entry.get("note") or ""
        suffix = f" — {note}" if note else ""
        lines.append(f"- {venue}: {url}{suffix}")
    return "\n".join(lines) + "\n\n"


def build_section_search_prompt(
    *,
    section_id: str,
    date_str: str,
    week_label: str,
    topics_cfg: dict,
    sources_cfg: dict,
    search_domains: list[str],
    calendar_items: list[dict] | None = None,
    state_dir: Path | None = None,
) -> str:
    calendar_items = calendar_items or []
    ctx = _culture_prompt_context(
        date_str=date_str,
        week_label=week_label,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        calendar_items=calendar_items,
        state_dir=state_dir,
    )
    topics = topic_by_id(topics_cfg)
    topic = topics.get(section_id) or {}
    topic_name = topic.get("name") or section_id
    base_min = section_min_items(topic)
    prog_count = ctx["prog_counts"].get(section_id, 0)
    openai_min = culture_openai_min(section_id, prog_count, base_min)

    return f"""You are researching Berlin culture events for ONE section. PHASE 1: web research only.

Section: **{topic_name}** (`{section_id}`)
Briefing run date (Tuesday): {date_str}
Event window: {week_label}
Target: find at least {openai_min} qualifying events for this section.

{ctx["interests_block"]}

{ctx["themes_block"]}

{ctx["novelty_block"]}{build_section_programme_block(sources_cfg, section_id)}
## Your task (web_search REQUIRED)
You MUST call web_search at least once before answering. Search the programme pages above for `{section_id}` events in the event window.

1. Use site-specific queries (e.g. for film: "site:arsenal-berlin.de cinema June 2026").
2. For each event, record: title, venue, dates, times, artists (if known),
   **official_url copied exactly from search** (specific event page — never a homepage, /en, or listing).
   For festivals: prefer **atomic dated events** (single concerts, openings, performances) over umbrella listings.
3. **Year / archive discipline (strict):**
   - Prefer event URLs that include the briefing year in the path when venues publish year-specific pages
     (e.g. `…/the-pressing-2026/` over an older `…/the-pressing-dani-brown/` archive slug).
   - Reject archive / past-edition pages whose on-page dates are a prior year (still-live 2022 pages are not 2026 events).
   - Copy dates/times from the **matched** event page only — never invent or shift dates to fit the Tuesday week window.
4. Skip events in the novelty index unless materially new (opening week, closing within 10 days).
5. If no in-window events exist, say so — do not invent placeholders.

## Tuesday rule
Include only events occurring Wednesday through the following Monday/Tuesday of the briefing week,
OR exhibitions open through at least Wednesday of that week.

Return research notes in plain text — **NOT JSON**. web_search domains: {len(search_domains)} allowed."""


def _culture_prompt_context(
    *,
    date_str: str,
    week_label: str,
    topics_cfg: dict,
    sources_cfg: dict,
    calendar_items: list[dict],
    state_dir: Path | None,
) -> dict[str, Any]:
    prog_counts = programme_counts(calendar_items, sources_cfg)
    sections_needing_search = set(SECTIONS_REQUIRING_WEB_SEARCH)
    return {
        "prog_counts": prog_counts,
        "sections_needing_search": sections_needing_search,
        "novelty_block": build_novelty_block(
            state_dir=state_dir or REPO_ROOT / "state" / "berlin-culture",
            run_date=date_str,
            topics_cfg=topics_cfg,
        ),
        "programme_block": build_programme_urls_block(
            sources_cfg,
            sections_needing_search=sections_needing_search,
        ),
        "press_block": build_press_warehouse_block(
            calendar_items=calendar_items,
            sources_cfg=sources_cfg,
        ),
        "warehouse_block": build_programme_warehouse_block(
            calendar_items=calendar_items,
            sources_cfg=sources_cfg,
            topics_cfg=topics_cfg,
        ),
        "section_requirements": build_section_requirements(
            topics_cfg,
            programme_coverage=prog_counts,
        ),
        "interests_block": build_compact_interests_block(topics_cfg),
        "themes_block": build_compact_themes_block(topics_cfg),
        "week_label": week_label,
        "date_str": date_str,
    }


def build_search_phase_prompt(
    *,
    date_str: str,
    week_label: str,
    topics_cfg: dict,
    sources_cfg: dict,
    search_domains: list[str],
    calendar_items: list[dict] | None = None,
    state_dir: Path | None = None,
) -> str:
    calendar_items = calendar_items or []
    ctx = _culture_prompt_context(
        date_str=date_str,
        week_label=week_label,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        calendar_items=calendar_items,
        state_dir=state_dir,
    )

    return f"""You are researching Berlin culture events for a weekly briefing. This is PHASE 1: web research only.

Briefing run date (Tuesday): {date_str}
Event window: {week_label}

{ctx["interests_block"]}

{ctx["themes_block"]}

{ctx["novelty_block"]}{ctx["programme_block"]}{ctx["press_block"]}{ctx["warehouse_block"]}{ctx["section_requirements"]}

## Your task (web_search REQUIRED — minimum {CULTURE_SEARCH_MIN_CALLS} searches)
You MUST use the web_search tool before writing your answer.

**Minimum {CULTURE_SEARCH_MIN_CALLS} separate web_search calls**, at least one per core section:
{", ".join(CULTURE_CORE_SEARCH_SECTIONS)}

Do not stop after a single venue (e.g. do not only search HKW). Each core section needs its own search on programme URLs listed above.

For each section — exhibitions, film, performing_arts, music (and wildcards/advance_radar if relevant):
1. Run web_search on **different** programme URLs for that section (site-specific queries encouraged, e.g. "site:arsenal-berlin.de cinema June 2026", "site:km28.de program June 2026").
2. For each qualifying event in the event window, record:
   - section id
   - title, venue, dates, times, artists (if known)
   - **official_url copied exactly from search results** (specific event page — never a homepage, /en, or /programme listing)
   - one-line why it fits the reader interests
   - **series_id** (stable slug, e.g. `polish-art-week-2026`) when the event belongs to a festival or recurring series
   - **event_kind**: `single` (default), `festival_overview` (one umbrella per festival max), or `festival_event` (one dated event inside a festival)
3. **Year / archive discipline (strict):**
   - Prefer event URLs that include the briefing year in the path when venues publish year-specific pages
     (e.g. `…/the-pressing-2026/` over an older `…/the-pressing-dani-brown/` archive slug).
   - Reject archive / past-edition pages whose on-page dates are a prior year (still-live 2022 pages are not 2026 events).
   - Copy dates/times from the **matched** event page only — never invent or shift dates to fit the Tuesday week window.
   - If the correct page is outside this week (e.g. early August revival), list it under advance_radar with the page's real dates — do not drag it into the main week.
4. **Festival / series handling (strict):**
   - Prefer **atomic events** with their own venue, dates, and deep URL over umbrella festival pages.
   - At most **one** `festival_overview` per festival in the entire output.
   - For multi-venue festivals, return individual `festival_event` items for standout gigs — share the same `series_id`.
5. Skip events already in the novelty index unless materially new (opening week, closing within 10 days).
6. If a venue page has no in-window events, say so — do not invent placeholders.

## Tuesday rule
Include only events occurring Wednesday through the following Monday/Tuesday of the briefing week,
OR exhibitions open through at least Wednesday of that week.

## Output format
Return detailed research notes in plain text or markdown — **NOT JSON**.
Every event MUST include the exact official_url string from web_search results.
web_search is domain-filtered ({len(search_domains)} allowed domains)."""


def build_structure_phase_prompt(
    *,
    date_str: str,
    week_label: str,
    topics_cfg: dict,
    sources_cfg: dict,
    calendar_items: list[dict] | None = None,
    state_dir: Path | None = None,
    research_notes: str,
) -> str:
    calendar_items = calendar_items or []
    ctx = _culture_prompt_context(
        date_str=date_str,
        week_label=week_label,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        calendar_items=calendar_items,
        state_dir=state_dir,
    )

    return f"""You are pre-fetching candidates for a weekly Berlin culture briefing. This is PHASE 2: JSON only.

Briefing run date (Tuesday): {date_str}
Event window: {week_label}

{ctx["section_requirements"]}

## Rules (strict)
- Convert ONLY events documented in the web research notes below into JSON items.
- Copy official_url values **verbatim** from the research notes — do not modify, guess, or construct URLs.
- Do NOT use web_search in this step. Do NOT add events missing from the research notes.
- If a section has fewer candidates than the target, list gaps — never invent filler.
- topic_ids: primary section id first, then optional theme tags
- For exhibitions: set closing_soon true if closing within 10 days
- **series_id**: stable slug for festivals/recurring series (shared across related items); empty string for one-offs
- **event_kind**: `single` | `festival_overview` | `festival_event` — at most one `festival_overview` per series_id
- Prefer atomic `single` / `festival_event` items; use `festival_overview` only when no atomic events were found
- **Year / archive:** Prefer year-in-path URLs for the briefing year; drop archive/past-edition pages; copy dates from the matched page — never invent in-week dates to force a fit

## Web research notes (from Phase 1 web_search)
{research_notes}

Return JSON: items (all sections combined), gaps, search_notes."""


def build_combined_prompt(
    *,
    date_str: str,
    week_label: str,
    topics_cfg: dict,
    sources_cfg: dict,
    search_domains: list[str],
    calendar_items: list[dict] | None = None,
    state_dir: Path | None = None,
) -> str:
    """Legacy single-pass prompt (dry-run). Production uses search + structure phases."""
    calendar_items = calendar_items or []
    ctx = _culture_prompt_context(
        date_str=date_str,
        week_label=week_label,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        calendar_items=calendar_items,
        state_dir=state_dir,
    )
    return (
        build_search_phase_prompt(
            date_str=date_str,
            week_label=week_label,
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
            search_domains=search_domains,
            calendar_items=calendar_items,
            state_dir=state_dir,
        )
        + "\n\n--- PHASE 2 (structure) would follow with research notes ---\n"
    )


def enrich_candidate(item: dict) -> dict:
    topic_ids = [t for t in (item.get("topic_ids") or []) if t]
    section_id = topic_ids[0] if topic_ids else "exhibitions"
    extra = [t for t in topic_ids if t != section_id]
    item["topic_ids"] = [section_id, *extra]
    item["ingestion_source"] = item.get("ingestion_source") or "openai"
    if item["ingestion_source"] == "openai" and "url_live" not in item:
        item["url_live"] = None
    enrich_culture_metadata(item)
    mark_item_verified(item, require_url_live=True)
    return item


def section_counts(items: list[dict], topics_cfg: dict) -> dict[str, int]:
    enabled = {
        t["id"]
        for t in topics_cfg.get("topics") or []
        if t.get("enabled", True) and t.get("id") not in ("top_picks",)
    }
    counts = {sid: 0 for sid in enabled}
    for item in items:
        topic_ids = item.get("topic_ids") or []
        if topic_ids and topic_ids[0] in counts:
            counts[topic_ids[0]] += 1
    return counts


def load_rss_items(inbox_dir: Path, date_str: str) -> list[dict]:
    rss_path = inbox_dir / f"{date_str}-rss.json"
    if not rss_path.is_file():
        return []
    try:
        payload = json.loads(rss_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"  Warning: could not read {rss_path.name}: {exc}")
        return []
    return payload.get("items") or []


def load_wordpress_items(inbox_dir: Path, date_str: str) -> list[dict]:
    wp_path = inbox_dir / f"{date_str}-wordpress.json"
    if not wp_path.is_file():
        return []
    try:
        payload = json.loads(wp_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"  Warning: could not read {wp_path.name}: {exc}")
        return []
    return payload.get("items") or []


def load_wordpress_event_items(inbox_dir: Path, date_str: str) -> list[dict]:
    path = inbox_dir / f"{date_str}-wordpress-events.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"  Warning: could not read {path.name}: {exc}")
        return []
    return payload.get("items") or []


def load_ics_items(inbox_dir: Path, date_str: str) -> list[dict]:
    path = inbox_dir / f"{date_str}-ics.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"  Warning: could not read {path.name}: {exc}")
        return []
    return payload.get("items") or []


def load_html_calendar_items(inbox_dir: Path, date_str: str) -> list[dict]:
    path = inbox_dir / f"{date_str}-html-calendars.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log(f"  Warning: could not read {path.name}: {exc}")
        return []
    return payload.get("items") or []


def load_calendar_items(inbox_dir: Path, date_str: str) -> list[dict]:
    return (
        load_rss_items(inbox_dir, date_str)
        + load_wordpress_items(inbox_dir, date_str)
        + load_wordpress_event_items(inbox_dir, date_str)
        + load_ics_items(inbox_dir, date_str)
        + load_html_calendar_items(inbox_dir, date_str)
    )


def merge_calendar_items(openai_items: list[dict], calendar_items: list[dict]) -> tuple[list[dict], int]:
    seen: set[str] = set()
    merged: list[dict] = []

    for item in openai_items:
        url = normalize_url(item.get("official_url") or "")
        if url:
            seen.add(url)
        merged.append(item)

    added = 0
    for item in calendar_items:
        url = normalize_url(item.get("official_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(item)
        added += 1

    return merged, added


def fetch_all_culture(
    *,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
    calendar_items: list[dict] | None = None,
    spend_ledger: DailySpendLedger | None = None,
    state_dir: Path | None = None,
) -> dict:
    date_str, run_dt = normalize_tuesday_run_date(date_str)
    week_start, week_end = culture_week_window(run_dt)
    week_label = format_week_range(week_start, week_end)
    allowed = sources_cfg.get("allowed_domains") or []
    calendar_items = calendar_items or []

    prog_counts = programme_counts(calendar_items, sources_cfg)
    editorial_counts = press_counts(calendar_items, sources_cfg)

    if spend_ledger and spend_ledger.cap_enabled():
        log(
            f"  Daily spend cap: ${spend_ledger.cap_usd:.2f} "
            f"(already spent today: ${spend_ledger.spent_usd:.4f})"
        )
        spend_ledger.assert_not_over_cap()

    log(f"  Running culture research (week: {week_label}) — phase 1 web_search per section...")
    if calendar_items:
        log(
            f"  Calendar warehouse: {len(calendar_items)} items "
            f"(programme={sum(prog_counts.values())}, press={sum(editorial_counts.values())})"
        )

    if spend_ledger and not spend_ledger.try_reserve_section_budget(
        reserve_usd=CULTURE_FETCH_BUDGET_RESERVE_USD
    ):
        raise RuntimeError("Insufficient daily OpenAI budget remaining")

    client = make_client()
    research_parts: list[str] = []
    web_search_calls = 0
    for section_id in CULTURE_CORE_SEARCH_SECTIONS:
        section_prompt = build_section_search_prompt(
            section_id=section_id,
            date_str=date_str,
            week_label=week_label,
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
            search_domains=allowed,
            calendar_items=calendar_items,
            state_dir=state_dir,
        )
        log(f"  Phase 1 [{section_id}]: web_search...")
        notes, search_response = fetch_web_research(
            client=client,
            model=model,
            prompt=section_prompt,
            domains=allowed,
            require_web_search=True,
            max_tool_calls=CULTURE_SEARCH_MAX_TOOL_CALLS,
            search_context_size="low",
        )
        calls = count_web_search_calls(search_response)
        web_search_calls += calls
        log(f"    {section_id}: {calls} web_search call(s), {len(notes)} chars")
        if calls == 0:
            raise RuntimeError(
                f"Culture pre-fetch aborted: 0 web_search calls for section '{section_id}'."
            )
        research_parts.append(f"## Section: {section_id}\n{notes}")
        if spend_ledger:
            usage = usage_from_response(
                response=search_response,
                model=model,
                section=f"culture_search_{section_id}",
            )
            spend_ledger.record_usage(usage)
            spend_ledger.assert_not_over_cap()

    research_notes = "\n\n".join(research_parts)
    log(
        f"  Phase 1 done: {web_search_calls} total web_search call(s), "
        f"{len(research_notes)} chars of notes"
    )
    if web_search_calls < CULTURE_SEARCH_MIN_CALLS:
        raise RuntimeError(
            f"Culture pre-fetch aborted: {web_search_calls} total web_search calls "
            f"(minimum {CULTURE_SEARCH_MIN_CALLS} required)."
        )

    structure_prompt = build_structure_phase_prompt(
        date_str=date_str,
        week_label=week_label,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        calendar_items=calendar_items,
        state_dir=state_dir,
        research_notes=research_notes,
    )
    log("  Phase 2: structuring research into JSON (web_search disabled)...")
    result, structure_response = fetch_structured(
        client=client,
        model=model,
        prompt=structure_prompt,
        schema=COMBINED_RESULT_SCHEMA,
        schema_name="culture_combined",
        domains=[],
        enable_web_search=False,
    )
    if spend_ledger:
        usage = usage_from_response(response=structure_response, model=model, section="culture_structure")
        spend_ledger.record_usage(usage)
        if spend_ledger.is_over_cap():
            spend_ledger.mark_cap_exceeded()
            raise SpendCapExceeded(
                f"Daily OpenAI spend cap reached (${spend_ledger.spent_usd:.4f} "
                f">= ${spend_ledger.cap_usd:.2f})"
            )

    raw_items = result.get("items") or []
    openai_items = [enrich_candidate(dict(item)) for item in raw_items]
    items = openai_items
    calendar_merged = 0
    if calendar_items:
        items, calendar_merged = merge_calendar_items(openai_items, calendar_items)
        if calendar_merged:
            log(f"  Merged {calendar_merged} calendar items (deduped against OpenAI)")

    counts = section_counts(items, topics_cfg)
    verified_count = sum(1 for item in items if item.get("verified"))
    log(f"  Combined fetch done ({len(items)} items, {verified_count} pre-URL-check verified) — {counts}")

    music_supplement_meta: dict[str, Any] = {}
    music_topic = topic_by_id(topics_cfg).get("music") or {}
    music_target = culture_openai_min(
        "music",
        prog_counts.get("music", 0),
        section_min_items(music_topic),
    )
    if counts.get("music", 0) < music_target:
        try:
            from fetch_culture_music import run_music_supplement

            supplement = run_music_supplement(
                date_str=date_str,
                model=model,
                topics_cfg=topics_cfg,
                sources_cfg=sources_cfg,
                calendar_items=calendar_items,
                existing_items=items,
                spend_ledger=spend_ledger,
            )
            web_search_calls += int(supplement.get("web_search_calls") or 0)
            added = 0
            seen_urls = {
                normalize_url(i.get("official_url") or "")
                for i in items
                if i.get("official_url")
            }
            for si in supplement.get("items") or []:
                url = normalize_url(si.get("official_url") or "")
                if url and url not in seen_urls:
                    items.append(si)
                    seen_urls.add(url)
                    added += 1
            if added:
                counts = section_counts(items, topics_cfg)
                verified_count = sum(1 for item in items if item.get("verified"))
                log(f"  Music supplement added {added} items — music now {counts.get('music', 0)}")
            music_supplement_meta = {
                "items_added": added,
                "web_search_calls": supplement.get("web_search_calls"),
                "skipped": supplement.get("skipped"),
            }
        except Exception as exc:
            log(f"  Music supplement failed: {exc}")
            music_supplement_meta = {"error": str(exc)}

    openai_targets = {
        sid: culture_openai_min(
            sid,
            prog_counts.get(sid, 0),
            section_min_items(topic_by_id(topics_cfg).get(sid) or {}),
        )
        for sid in counts
    }

    return {
        "briefing_type": "berlin-culture",
        "date": date_str,
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": week_end.strftime("%Y-%m-%d"),
        "week_label": week_label,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "fetch_mode": "search_per_section_then_structure",
        "web_search_calls": web_search_calls,
        "research_notes_chars": len(research_notes),
        "items": items,
        "gaps": result.get("gaps") or [],
        "section_counts": counts,
        "programme_counts": prog_counts,
        "press_counts": editorial_counts,
        "calendar_counts": {**prog_counts},
        "rss_counts": prog_counts,
        "openai_targets": openai_targets,
        "calendar_merged": calendar_merged,
        "music_supplement": music_supplement_meta,
        "search_notes": (
            f"Phase 1 web_search_calls={web_search_calls}. "
            f"Programme counts: {prog_counts}. Press counts: {editorial_counts}. "
            f"OpenAI targets: {openai_targets}. Calendar merged: {calendar_merged}. "
            f"{result.get('search_notes') or ''}"
        ).strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Berlin culture research via web_search (phase 1) + JSON structuring (phase 2)"
    )
    parser.add_argument("--type", default="berlin-culture", help="Briefing type (default: berlin-culture)")
    parser.add_argument("--date", help="YYYY-MM-DD Tuesday run date (default: today UTC)")
    parser.add_argument("--model", default=None, help=f"Override model (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--no-calendar-merge",
        action="store_true",
        help="Do not merge inbox RSS/WordPress files even if present",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print combined prompt only")
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

    calendar_items: list[dict] = []
    if not args.no_calendar_merge:
        calendar_items = load_calendar_items(briefing.inbox_dir, date_str)

    if args.dry_run:
        log(
            build_combined_prompt(
                date_str=date_str,
                week_label=week_label,
                topics_cfg=topics_cfg,
                sources_cfg=sources_cfg,
                search_domains=allowed,
                calendar_items=calendar_items,
                state_dir=briefing.state_dir,
            )
        )
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
            calendar_items=calendar_items,
            spend_ledger=spend_ledger,
            state_dir=briefing.state_dir,
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
    log("  Next: python scripts/verify_culture_urls.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
