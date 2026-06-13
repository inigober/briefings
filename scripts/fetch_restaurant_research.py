#!/usr/bin/env python3
"""Pre-fetch Berlin restaurant candidates via a single OpenAI call + web_search.

Google Maps verification runs afterward via ``verify_restaurant_maps.py`` (Places API).
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
from datetime import datetime, timezone

from briefing_paths import load_briefing_type
from fetch_openai_research import (
    DEFAULT_MODEL,
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
from restaurant_dates import normalize_thursday_run_date

REPO_ROOT = Path(__file__).resolve().parent.parent

# Minimum candidates per section in the single combined fetch (synthesis picks fewer).
DEFAULT_SECTION_MIN = 3
FINE_DINING_SECTION_MIN = 2

RESTAURANT_CANDIDATE_SCHEMA = {
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
        "source_urls",
    ],
    "additionalProperties": False,
}

COMBINED_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": RESTAURANT_CANDIDATE_SCHEMA},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "search_notes": {"type": "string"},
    },
    "required": ["items", "gaps", "search_notes"],
    "additionalProperties": False,
}


def section_min_items(topic: dict) -> int:
    if topic.get("optional"):
        return FINE_DINING_SECTION_MIN
    return int(topic.get("prefetch_min") or DEFAULT_SECTION_MIN)


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


def build_section_requirements(topics_cfg: dict) -> str:
    lines = ["## Section targets (assign each candidate to one primary topic_id)"]
    for topic in topics_cfg.get("topics") or []:
        if not topic.get("enabled", True):
            continue
        sid = topic.get("id", "")
        min_items = section_min_items(topic)
        optional = " (optional section — include only if genuinely strong)" if topic.get("optional") else ""
        lines.append(
            f"- **{topic.get('name')}** (`{sid}`): at least {min_items} candidates{optional}\n"
            f"  {str(topic.get('description', '')).strip()}"
        )
    return "\n".join(lines)


def build_combined_prompt(
    *,
    date_str: str,
    topics_cfg: dict,
    sources_cfg: dict,
    search_domains: list[str],
) -> str:
    domains = "\n".join(f"- {d}" for d in search_domains)
    neighborhoods = sources_cfg.get("neighborhoods_to_diversify") or []
    neighborhood_line = (
        f"- Actively diversify neighborhoods: {', '.join(neighborhoods)}"
        if neighborhoods
        else ""
    )
    return f"""You are pre-fetching candidates for a weekly Berlin restaurant briefing in ONE combined pass.

Briefing week date: {date_str}

Audience:
- Serious Berlin food enthusiast
- Values flavor, technique, craft, regional identity, and execution over aesthetics or hype
- Generally prefers affordable and mid-range restaurants, with at most one fine dining pick in synthesis
- Likes restaurants such as Liu Nudelhaus, Nini e Petirosso, Adana Grillhaus, Euro Imbiss 2, Jemenitisches Restaurant on Karl-Marx-Strasse, Gotxa, Alaska Bar, Asia Farmhouse, Myxa, St. Bart, Bottega N.6, Ma-Makan, Larb Koi, Khao Taan, Taqueria El Oso, Dan Thai Food, Ming Dynastie, and Tian Fu

{build_preferences_block(topics_cfg)}

{build_section_requirements(topics_cfg)}

## Discovery rules (no Google Maps in this step)
- Use food press, guides, and editorial sources only — **do not** open Google Maps or fill Maps URLs/ratings/hours.
- A separate Google Places step verifies existence, closure status, and Maps metadata after this run.
- Include **name**, **neighborhood**, and **street address** (or cross-street) so Places can match the venue.
- Exclude candidates you strongly believe are permanently closed based on recent press, but do not spend searches on Maps verification.
- Prefer restaurants with clear culinary identity, specialization, strong value, or regional authenticity.
- Include both strengths and weaknesses; avoid generic praise.
- Prefer neighborhood diversity; avoid over-concentrating Mitte.
- Price tiers: € under roughly 15 EUR, €€ roughly 15-35 EUR, €€€ roughly 35-70 EUR, €€€€ 70 EUR+
- value_label must be null unless "good value" or "potentially overpriced" is genuinely noteworthy
{neighborhood_line}

web_search allowed domains:
{domains}

Return JSON: items (all sections combined), gaps, search_notes."""


def enrich_candidate(item: dict) -> dict:
    """Add Places placeholders — verification runs in verify_restaurant_maps.py."""
    topic_ids = [t for t in (item.get("topic_ids") or []) if t]
    section_id = topic_ids[0] if topic_ids else "specialist_neighborhood"
    extra = [t for t in topic_ids if t != section_id]
    item["topic_ids"] = [section_id, *extra]
    item["ingestion_source"] = "openai"
    name = (item.get("name") or "").strip()
    address = (item.get("address") or "").strip()
    item["google_maps_name"] = name
    item["google_maps_address"] = address
    item["google_maps_url"] = ""
    item["google_maps_place_id"] = None
    item["google_maps_rating"] = None
    item["google_maps_review_count"] = None
    item["google_maps_hours_compact"] = None
    item["exists_in_berlin"] = False
    item["permanently_closed"] = False
    item["temporarily_closed"] = False
    item["maps_api_verified"] = False
    item["verification_notes"] = "Pending Google Places verification"
    item["verified"] = False
    return item


def section_counts(items: list[dict], topics_cfg: dict) -> dict[str, int]:
    enabled = {
        t["id"]
        for t in topics_cfg.get("topics") or []
        if t.get("enabled", True) and t.get("id")
    }
    counts = {sid: 0 for sid in enabled}
    for item in items:
        topic_ids = item.get("topic_ids") or []
        if topic_ids and topic_ids[0] in counts:
            counts[topic_ids[0]] += 1
    return counts


def fetch_all_restaurants(
    *,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
    spend_ledger: DailySpendLedger | None = None,
) -> dict:
    date_str, _ = normalize_thursday_run_date(date_str)
    allowed = sources_cfg.get("allowed_domains") or []

    if spend_ledger and spend_ledger.cap_enabled():
        log(
            f"  Daily spend cap: ${spend_ledger.cap_usd:.2f} "
            f"(already spent today: ${spend_ledger.spent_usd:.4f})"
        )
        spend_ledger.assert_not_over_cap()

    prompt = build_combined_prompt(
        date_str=date_str,
        topics_cfg=topics_cfg,
        sources_cfg=sources_cfg,
        search_domains=allowed,
    )
    log("  Running single combined restaurant research fetch...")

    if spend_ledger and not spend_ledger.try_reserve_section_budget():
        raise RuntimeError("Insufficient daily OpenAI budget remaining")

    client = make_client()
    result, response = fetch_structured(
        client=client,
        model=model,
        prompt=prompt,
        schema=COMBINED_RESULT_SCHEMA,
        schema_name="restaurant_combined",
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
    items = [enrich_candidate(dict(item)) for item in raw_items]
    counts = section_counts(items, topics_cfg)
    log(
        f"  Combined fetch done ({len(items)} candidates; "
        f"Places verification next) — {counts}"
    )

    return {
        "briefing_type": "berlin-restaurants",
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "fetch_mode": "combined",
        "items": items,
        "gaps": result.get("gaps") or [],
        "section_counts": counts,
        "verified_count": 0,
        "search_notes": result.get("search_notes") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Berlin restaurant research via one OpenAI web_search call"
    )
    parser.add_argument("--type", default="berlin-restaurants")
    parser.add_argument("--date", help="YYYY-MM-DD run date (default: today UTC)")
    parser.add_argument("--model", default=None, help=f"Override model (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="Print combined prompt only")
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    original = date_str
    date_str, _ = normalize_thursday_run_date(date_str)
    if date_str != original:
        log(
            f"  Warning: {original} is not a Thursday — using previous Thursday "
            f"{date_str} for file naming"
        )

    topics_cfg = load_yaml(briefing.topics_path)
    sources_cfg = load_yaml(briefing.sources_path)
    allowed = sources_cfg.get("allowed_domains") or []

    if args.dry_run:
        log(
            build_combined_prompt(
                date_str=date_str,
                topics_cfg=topics_cfg,
                sources_cfg=sources_cfg,
                search_domains=allowed,
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
    spend_ledger = DailySpendLedger.load_or_create(
        spend_path, date_str=date_str, cap_usd=cap_usd
    )

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
        f"Wrote {out_path} ({len(payload.get('items') or [])} candidates; "
        "run verify_restaurant_maps.py next)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
