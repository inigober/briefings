#!/usr/bin/env python3
"""Pre-fetch Berlin culture events via one OpenAI Responses API call + web_search.

Optional RSS calendar feeds (fetch_rss.py) are merged first to reduce OpenAI minimums.
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
from urllib.parse import urlparse

from briefing_paths import load_briefing_type
from culture_dates import normalize_tuesday_run_date
from fetch_openai_research import (
    DEFAULT_MODEL,
    fetch_structured,
    load_yaml,
    log,
    make_client,
    normalize_url,
    resolve_model,
    topic_by_id,
)
from openai_spend import (
    COMBINED_FETCH_BUDGET_RESERVE_USD,
    DailySpendLedger,
    SpendCapExceeded,
    handle_cap_abort,
    resolve_daily_cap,
    usage_from_response,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

CULTURE_OPENAI_MIN_FLOOR = 2
CULTURE_RSS_SATURATION_HIGH = 6
CULTURE_RSS_SATURATION_MID = 3

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


def section_min_items(topic: dict) -> int:
    return int(topic.get("prefetch_min") or 5)


def culture_openai_min(section_id: str, rss_count: int, base_min: int) -> int:
    floor = CULTURE_OPENAI_MIN_FLOOR
    if topic_is_optional(section_id):
        floor = 1
    if rss_count == 0:
        return base_min
    if rss_count >= CULTURE_RSS_SATURATION_HIGH:
        return floor
    if rss_count >= CULTURE_RSS_SATURATION_MID:
        return max(floor, (base_min + floor) // 2)
    reduction = min(rss_count, base_min - floor)
    return max(floor, base_min - reduction)


def topic_is_optional(section_id: str) -> bool:
    return section_id == "advance_radar"


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


def build_compact_venues_block(sources_cfg: dict) -> str:
    lines = ["## Priority venues (search venue sites directly)"]
    for discipline, venues in (sources_cfg.get("priority_venues") or {}).items():
        lines.append(f"- {discipline}: {', '.join(venues)}")
    festivals = sources_cfg.get("festivals_to_monitor") or []
    if festivals:
        lines.append(f"- Festivals: {', '.join(festivals[:8])}")
    return "\n".join(lines)


def build_compact_calendars_block(sources_cfg: dict) -> str:
    calendars = sources_cfg.get("primary_calendars") or []
    names = [cal.get("name") for cal in calendars if cal.get("name")]
    if not names:
        return ""
    return "## Primary calendars (cross-reference first)\n" + ", ".join(names)


def build_section_requirements(
    topics_cfg: dict,
    *,
    rss_counts: dict[str, int] | None = None,
) -> str:
    rss_counts = rss_counts or {}
    lines = ["## Section targets (assign each candidate to one primary topic_id)"]
    for topic in topics_cfg.get("topics") or []:
        if not topic.get("enabled", True):
            continue
        sid = topic.get("id", "")
        if sid == "top_picks":
            continue
        base_min = section_min_items(topic)
        openai_min = culture_openai_min(sid, rss_counts.get(sid, 0), base_min)
        optional = " (optional — include only if genuinely relevant)" if topic.get("optional") else ""
        min_note = (
            f"at least {openai_min} new candidates (reduced from {base_min} — RSS already covers this section)"
            if rss_counts.get(sid, 0) > 0 and openai_min < base_min
            else f"at least {openai_min} candidates"
        )
        desc = str(topic.get("description", "")).strip()
        if len(desc) > 180:
            desc = desc[:177] + "..."
        lines.append(
            f"- **{topic.get('name')}** (`{sid}`): {min_note}{optional}\n  {desc}"
        )
    return "\n".join(lines)


def build_calendar_warehouse_block(
    *,
    calendar_items: list[dict],
    topics_cfg: dict,
) -> str:
    if not calendar_items:
        return ""

    topics = topic_by_id(topics_cfg)
    section_ids = [
        t["id"]
        for t in topics_cfg.get("topics") or []
        if t.get("enabled", True) and t.get("id") not in ("top_picks",)
    ]
    counts = {sid: 0 for sid in section_ids}
    samples: dict[str, list[str]] = {sid: [] for sid in section_ids}
    source_counts: dict[str, int] = {}

    for item in calendar_items:
        sid = (item.get("topic_ids") or ["exhibitions"])[0]
        source = item.get("ingestion_source") or "calendar"
        source_counts[source] = source_counts.get(source, 0) + 1
        if sid not in counts:
            continue
        counts[sid] += 1
        title = (item.get("title") or "").strip()
        if title and len(samples[sid]) < 4:
            samples[sid].append(title)

    source_summary = ", ".join(f"{k}={v}" for k, v in sorted(source_counts.items()))
    lines = [
        "## Calendar warehouse (already collected — do not duplicate)",
        f"- {len(calendar_items)} items already ingested via RSS/WordPress ({source_summary}).",
        "- OpenAI targets above are reduced per section — search for **gaps only**.",
        "- Prefer venue programme pages and calendars the warehouse missed; do not re-list feed headlines.",
    ]
    for sid in section_ids:
        if counts[sid] == 0:
            continue
        sample_text = "; ".join(samples[sid][:3])
        lines.append(
            f"- {sid}: {counts[sid]} warehouse items"
            + (f" (e.g. {sample_text})" if sample_text else "")
        )
    return "\n".join(lines) + "\n\n"


def build_combined_prompt(
    *,
    date_str: str,
    week_label: str,
    topics_cfg: dict,
    sources_cfg: dict,
    search_domains: list[str],
    calendar_items: list[dict] | None = None,
) -> str:
    calendar_items = calendar_items or []
    calendar_counts: dict[str, int] = {}
    for item in calendar_items:
        sid = (item.get("topic_ids") or ["exhibitions"])[0]
        calendar_counts[sid] = calendar_counts.get(sid, 0) + 1

    calendars = build_compact_calendars_block(sources_cfg)
    warehouse_block = build_calendar_warehouse_block(
        calendar_items=calendar_items,
        topics_cfg=topics_cfg,
    )

    return f"""You are pre-fetching candidates for a weekly Berlin culture briefing in ONE combined pass.

Briefing run date (Tuesday): {date_str}
Event window: {week_label}

{build_compact_interests_block(topics_cfg)}

{build_compact_themes_block(topics_cfg)}

{calendars}

{build_compact_venues_block(sources_cfg)}

{build_section_requirements(topics_cfg, rss_counts=calendar_counts)}

{warehouse_block}## Tuesday rule
Include only events occurring Wednesday through the following Monday/Tuesday of the briefing week,
OR exhibitions open through at least Wednesday of that week.
Exclude events already finished before Wednesday.

## Output rules
- official_url MUST be the **specific** event/exhibition page (never a homepage or social media)
- dates and times must be concrete (not "TBA") when possible
- For exhibitions: set closing_soon true if closing within 10 days
- topic_ids: primary section id first, then optional theme tags
- why_candidate: one sentence on thematic/artistic fit

## Search scope
web_search is domain-filtered automatically ({len(search_domains)} allowed domains).
Prioritize primary calendars, then venue programme pages for exhibitions, film, performance, and music.

Return JSON: items (all sections combined), gaps, search_notes."""


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


def enrich_candidate(item: dict) -> dict:
    topic_ids = [t for t in (item.get("topic_ids") or []) if t]
    section_id = topic_ids[0] if topic_ids else "exhibitions"
    extra = [t for t in topic_ids if t != section_id]
    item["topic_ids"] = [section_id, *extra]
    item["ingestion_source"] = item.get("ingestion_source") or "openai"
    mark_item_verified(item)
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


def load_calendar_items(inbox_dir: Path, date_str: str) -> list[dict]:
    return load_rss_items(inbox_dir, date_str) + load_wordpress_items(inbox_dir, date_str)


def merge_calendar_items(openai_items: list[dict], calendar_items: list[dict]) -> tuple[list[dict], int]:
    """Merge RSS candidates; OpenAI items win on official_url collision."""
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
    rss_items: list[dict] | None = None,
    calendar_items: list[dict] | None = None,
    spend_ledger: DailySpendLedger | None = None,
) -> dict:
    date_str, run_dt = normalize_tuesday_run_date(date_str)
    week_start, week_end = culture_week_window(run_dt)
    week_label = format_week_range(week_start, week_end)
    allowed = sources_cfg.get("allowed_domains") or []
    if calendar_items is None:
        calendar_items = rss_items or []
    calendar_items = calendar_items or []

    if spend_ledger and spend_ledger.cap_enabled():
        log(
            f"  Daily spend cap: ${spend_ledger.cap_usd:.2f} "
            f"(already spent today: ${spend_ledger.spent_usd:.4f})"
        )
        spend_ledger.assert_not_over_cap()

    prompt = build_combined_prompt(
        date_str=date_str,
        week_label=week_label,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        search_domains=allowed,
        calendar_items=calendar_items,
    )
    log(f"  Running single combined culture research fetch (week: {week_label})...")
    if calendar_items:
        log(f"  Calendar warehouse: {len(calendar_items)} items (RSS + WordPress) merged after OpenAI")

    if spend_ledger and not spend_ledger.try_reserve_section_budget(
        reserve_usd=COMBINED_FETCH_BUDGET_RESERVE_USD
    ):
        raise RuntimeError("Insufficient daily OpenAI budget remaining")

    client = make_client()
    result, response = fetch_structured(
        client=client,
        model=model,
        prompt=prompt,
        schema=COMBINED_RESULT_SCHEMA,
        schema_name="culture_combined",
        domains=allowed,
    )
    if spend_ledger:
        usage = usage_from_response(response=response, model=model, section="combined")
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
    log(f"  Combined fetch done ({len(items)} items, {verified_count} verified) — {counts}")

    calendar_counts = {sid: 0 for sid in counts}
    for item in calendar_items:
        sid = (item.get("topic_ids") or ["exhibitions"])[0]
        if sid in calendar_counts:
            calendar_counts[sid] += 1

    openai_targets = {
        sid: culture_openai_min(
            sid,
            calendar_counts.get(sid, 0),
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
        "fetch_mode": "combined",
        "items": items,
        "gaps": result.get("gaps") or [],
        "section_counts": counts,
        "calendar_counts": calendar_counts,
        "rss_counts": calendar_counts,
        "openai_targets": openai_targets,
        "calendar_merged": calendar_merged,
        "search_notes": (
            f"Calendar counts: {calendar_counts}. OpenAI targets: {openai_targets}. "
            f"Calendar merged: {calendar_merged}. {result.get('search_notes') or ''}"
        ).strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Berlin culture research via one OpenAI web_search call"
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
