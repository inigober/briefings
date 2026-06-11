#!/usr/bin/env python3
"""Pre-fetch Berlin restaurant candidates via OpenAI Responses API + web_search."""

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
from typing import Any

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

RESTAURANT_SECTION_MIN: dict[str, int] = {
    "regional_chinese": 6,
    "southeast_asian": 6,
    "turkish_middle_eastern_caucasus": 6,
    "mediterranean_european": 6,
    "specialist_neighborhood": 6,
    "fine_dining": 3,
}

RESTAURANT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "topic_ids": {"type": "array", "items": {"type": "string"}},
        "name": {"type": "string"},
        "neighborhood": {"type": "string"},
        "address": {"type": "string"},
        "cuisine": {"type": "string"},
        "price_tier": {"type": "string", "enum": ["€", "€€", "€€€", "€€€€"]},
        "value_label": {
            "type": ["string", "null"],
            "enum": ["good value", "potentially overpriced", None],
        },
        "fine_dining": {"type": "boolean"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "comparative_context": {"type": "string"},
        "critical_assessment": {"type": "string"},
        "google_maps_name": {"type": "string"},
        "google_maps_url": {"type": "string"},
        "google_maps_address": {"type": "string"},
        "google_maps_rating": {"type": ["number", "null"]},
        "google_maps_review_count": {"type": ["integer", "null"]},
        "google_maps_hours_compact": {"type": ["string", "null"]},
        "exists_in_berlin": {"type": "boolean"},
        "permanently_closed": {"type": "boolean"},
        "temporarily_closed": {"type": "boolean"},
        "verification_notes": {"type": "string"},
        "source_urls": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "id",
        "topic_ids",
        "name",
        "neighborhood",
        "address",
        "cuisine",
        "price_tier",
        "value_label",
        "fine_dining",
        "strengths",
        "weaknesses",
        "comparative_context",
        "critical_assessment",
        "google_maps_name",
        "google_maps_url",
        "google_maps_address",
        "google_maps_rating",
        "google_maps_review_count",
        "google_maps_hours_compact",
        "exists_in_berlin",
        "permanently_closed",
        "temporarily_closed",
        "verification_notes",
        "source_urls",
    ],
    "additionalProperties": False,
}

SECTION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": RESTAURANT_ITEM_SCHEMA},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "search_notes": {"type": "string"},
    },
    "required": ["items", "gaps", "search_notes"],
    "additionalProperties": False,
}


def normalize_thursday_run_date(date_str: str) -> tuple[str, datetime]:
    """Restaurant briefings use the Thursday run date as the week key."""
    run_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if run_dt.weekday() != 3:
        # Monday=0 … Sunday=6; distance back to previous Thursday (never 0 here).
        days_since_thursday = (run_dt.weekday() - 3) % 7 or 7
        snapped = run_dt - timedelta(days=days_since_thursday)
        log(
            f"  Warning: {date_str} is not a Thursday — using previous Thursday "
            f"{snapped.strftime('%Y-%m-%d')} for file naming"
        )
        run_dt = snapped
        date_str = run_dt.strftime("%Y-%m-%d")
    return date_str, run_dt


def build_preferences_block(topics_cfg: dict) -> str:
    prefs = topics_cfg.get("preferences") or {}
    lines = ["## Reader preferences"]
    for key, values in prefs.items():
        label = key.replace("_", " ")
        if isinstance(values, list):
            lines.append(f"- {label}: {', '.join(str(v) for v in values)}")
        else:
            lines.append(f"- {label}: {values}")
    return "\n".join(lines)


def build_sources_block(sources_cfg: dict, section_id: str) -> str:
    priorities = (sources_cfg.get("source_priorities") or {}).get(section_id) or []
    neighborhoods = sources_cfg.get("neighborhoods_to_diversify") or []
    lines = ["## Search guidance"]
    if priorities:
        lines.append(f"- Priority sources for this section: {', '.join(priorities)}")
    if neighborhoods:
        lines.append(f"- Actively diversify neighborhoods: {', '.join(neighborhoods)}")
    lines.append("- Google Maps is mandatory for verification; other sources are candidate discovery only.")
    return "\n".join(lines)


def build_section_prompt(
    *,
    section_id: str,
    topic: dict,
    date_str: str,
    min_items: int,
    topics_cfg: dict,
    sources_cfg: dict,
    search_domains: list[str],
) -> str:
    domains = "\n".join(f"- {d}" for d in search_domains)
    return f"""You are pre-fetching candidates for a weekly Berlin restaurant briefing.

Briefing week date: {date_str}
Section: {topic.get('name')} ({section_id})
Minimum candidates: {min_items}

Audience:
- Serious Berlin food enthusiast
- Values flavor, technique, craft, regional identity, and execution over aesthetics or hype
- Generally prefers affordable and mid-range restaurants, with at most one fine dining pick later
- Likes restaurants such as Liu Nudelhaus, Nini e Petirosso, Adana Grillhaus, Euro Imbiss 2, Jemenitisches Restaurant on Karl-Marx-Strasse, Gotxa, Alaska Bar, Asia Farmhouse, Myxa, St. Bart, Bottega N.6, Ma-Makan, Larb Koi, Khao Taan, Taqueria El Oso, Dan Thai Food, Ming Dynastie, and Tian Fu

{build_preferences_block(topics_cfg)}

{build_sources_block(sources_cfg, section_id)}

## Section focus
{topic.get('description', '')}

## Mandatory Google Maps verification
For every candidate, search Google Maps or a Google local profile and fill the Google Maps fields.
Only return candidates where:
- The restaurant exists in Berlin
- Google Maps does not mark it permanently closed
- Google Maps does not mark it temporarily closed

If Google Maps is ambiguous, missing, says closed, or suggests the restaurant relocated outside Berlin, exclude the restaurant entirely. Do not rely on old press, Michelin, social media, websites, or prior knowledge when Google Maps contradicts them.

For every verified candidate, also copy from Google Maps when visible:
- google_maps_rating: star rating as a number (e.g. 4.5), or null if missing
- google_maps_review_count: integer review count, or null if missing
- google_maps_hours_compact: one-line opening hours in compact form (e.g. "Tue–Sun 12:00–22:00 (closed Mon)"), or null if unavailable

## Candidate quality rules
- Prefer restaurants with clear culinary identity, specialization, strong value, technical competence, or regional authenticity
- Do not select restaurants only because they are fashionable
- Include both strengths and weaknesses
- Avoid generic praise; use critical, comparative language
- Prefer neighborhood diversity and avoid over-concentrating Mitte
- Price tiers: € under roughly 15 EUR, €€ roughly 15-35 EUR, €€€ roughly 35-70 EUR, €€€€ 70 EUR+
- value_label must be null unless "good value" or "potentially overpriced" is genuinely noteworthy

web_search allowed domains:
{domains}

Return JSON: items, gaps, search_notes."""


def is_verified(item: dict) -> bool:
    url = (item.get("google_maps_url") or "").strip()
    return (
        url.startswith("http")
        and bool(item.get("exists_in_berlin"))
        and not bool(item.get("permanently_closed"))
        and not bool(item.get("temporarily_closed"))
    )


def fetch_restaurant_section(
    *,
    section_id: str,
    date_str: str,
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

    min_items = RESTAURANT_SECTION_MIN.get(section_id, 5)
    allowed = sources_cfg.get("allowed_domains") or []
    prompt = build_section_prompt(
        section_id=section_id,
        topic=topic,
        date_str=date_str,
        min_items=min_items,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        search_domains=allowed,
    )

    log(f"  [{section_id}] started (min {min_items} candidates)...")

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
        schema_name=f"restaurant_section_{section_id}",
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
        item["verified"] = is_verified(item)
        if item["verified"]:
            verified_count += 1
    log(f"  [{section_id}] done ({len(items)} candidates, {verified_count} verified)")
    return section_id, result


def fetch_all_restaurants(
    *,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
    spend_ledger: DailySpendLedger | None = None,
) -> dict:
    date_str, _ = normalize_thursday_run_date(date_str)
    topics = topic_by_id(topics_cfg)
    section_ids = [
        sid
        for sid, t in topics.items()
        if t.get("enabled", True)
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
    log(f"  Launching {len(section_ids)} restaurant section fetches...")

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(
                fetch_restaurant_section,
                section_id=sid,
                date_str=date_str,
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

    verified_count = sum(1 for item in all_items if item.get("verified"))
    return {
        "briefing_type": "berlin-restaurants",
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "items": all_items,
        "gaps": all_gaps,
        "section_counts": section_counts,
        "verified_count": verified_count,
        "search_notes": " ".join(notes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Berlin restaurant research via OpenAI web_search")
    parser.add_argument("--type", default="berlin-restaurants", help="Briefing type (default: berlin-restaurants)")
    parser.add_argument("--date", help="YYYY-MM-DD Thursday run date (default: today UTC)")
    parser.add_argument("--model", default=None, help=f"Override model (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="Print first section prompt only")
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_str, _ = normalize_thursday_run_date(date_str)
    topics_cfg = load_yaml(briefing.topics_path)
    sources_cfg = load_yaml(briefing.sources_path)
    allowed = sources_cfg.get("allowed_domains") or []

    if args.dry_run:
        topics = topic_by_id(topics_cfg)
        first_section = next(iter(topics))
        topic = topics.get(first_section) or {}
        prompt = build_section_prompt(
            section_id=first_section,
            topic=topic,
            date_str=date_str,
            min_items=RESTAURANT_SECTION_MIN.get(first_section, 5),
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

    log(f"Fetching Berlin restaurant research for {date_str} with model {model}...")
    try:
        payload = fetch_all_restaurants(
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
    log(
        f"Wrote {out_path} ({len(payload.get('items') or [])} candidates, "
        f"{payload.get('verified_count', 0)} verified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
