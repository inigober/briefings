#!/usr/bin/env python3
"""Build a token-light inbox slice for Cursor synthesis from the full pre-fetch."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from briefing_paths import load_briefing_type
from culture_calendar import is_publisher_venue_item
from culture_dates import normalize_tuesday_run_date
from restaurant_dates import normalize_thursday_run_date

REPO_ROOT = Path(__file__).resolve().parent.parent

NEWS_SECTION_IDS = ("spain", "germany", "berlin", "world")
SELECTED_READS_CAP = 8

NEWS_SLIM_ITEM_KEYS = (
    "id",
    "topic_ids",
    "headline",
    "summary",
    "why_it_matters",
    "broader_context",
    "region",
    "country",
    "is_structural",
    "material_development",
    "ingestion_source",
    "verified",
    "url_live",
    "url_verify_notes",
    "sources",
)

CULTURE_SLIM_ITEM_KEYS = (
    "id",
    "topic_ids",
    "title",
    "venue",
    "dates",
    "times",
    "artists",
    "official_url",
    "closing_soon",
    "verified",
    "url_live",
    "why_candidate",
    "ingestion_source",
)

RESTAURANT_SLIM_ITEM_KEYS = (
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
    "google_maps_place_id",
    "google_maps_rating",
    "google_maps_review_count",
    "google_maps_hours_compact",
    "maps_api_verified",
    "exists_in_berlin",
    "permanently_closed",
    "temporarily_closed",
    "verified",
    "verification_notes",
    "source_urls",
    "ingestion_source",
)


def log(message: str) -> None:
    print(message, flush=True)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def topic_by_id(topics_cfg: dict) -> dict[str, dict]:
    return {t["id"]: t for t in topics_cfg.get("topics", []) if t.get("id")}


def host_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host


def selected_read_domains(sources_cfg: dict) -> set[str]:
    domains: set[str] = set()
    for key in (
        "long_form_features",
        "think_tanks",
        "specialist_publications",
        "news_analysis",
    ):
        domains.update(sources_cfg.get(key) or [])
    return domains


def item_domain(item: dict) -> str | None:
    for src in item.get("sources") or []:
        url = src.get("url") or ""
        if url.startswith("http"):
            return host_domain(url)
    official = item.get("official_url") or ""
    if official.startswith("http"):
        return host_domain(official)
    return None


def matches_domain(host: str, allowed: set[str]) -> bool:
    return any(host == d or host.endswith(f".{d}") for d in allowed)


def score_news_item(item: dict) -> int:
    score = 0
    source = item.get("ingestion_source") or "openai"
    url_live = item.get("url_live")

    if source in ("rss", "wordpress"):
        score += 35
    elif url_live == "live":
        score += 18
    elif url_live == "paywalled":
        score += 8
    elif url_live == "dead":
        score -= 80
    elif source == "openai":
        score -= 15

    if item.get("verified") and url_live != "dead":
        score += 12
    elif item.get("verified") is False and source == "openai":
        score -= 20

    if (item.get("why_it_matters") or "").strip():
        score += 8
    if (item.get("broader_context") or "").strip():
        score += 8
    if item.get("is_structural"):
        score += 5
    if item.get("material_development"):
        score += 5
    if item.get("is_follow_up"):
        score += 1
    return score


def score_culture_item(item: dict, priority_venues: set[str], sources_cfg: dict | None = None) -> int:
    score = 0
    source = item.get("ingestion_source") or "openai"
    url_live = item.get("url_live")

    if source == "openai":
        if url_live is True:
            score += 18
        elif url_live is False:
            score -= 25
        else:
            score += 4
    elif source in ("rss", "wordpress"):
        score += 2

    if item.get("verified") and url_live is not False:
        score += 22
    elif item.get("verified") and url_live is False:
        score -= 10

    if sources_cfg and is_publisher_venue_item(item, sources_cfg):
        score -= 18

    if item.get("closing_soon"):
        score += 25
    venue = (item.get("venue") or "").lower()
    for pv in priority_venues:
        if pv.lower() in venue:
            score += 15
            break
    if (item.get("why_candidate") or "").strip():
        score += 8
    artists = item.get("artists") or []
    if artists:
        score += 5
    if (item.get("official_url") or "").startswith("http"):
        score += 6
    if (item.get("dates") or "").strip():
        score += 6
    return score


def score_restaurant_item(item: dict) -> int:
    score = 0
    if item.get("verified"):
        score += 40
    if item.get("maps_api_verified"):
        score += 25
    if item.get("value_label") == "good value":
        score += 8
    if item.get("value_label") == "potentially overpriced":
        score -= 5
    if not item.get("fine_dining"):
        score += 5
    if item.get("strengths"):
        score += min(len(item["strengths"]), 4) * 3
    if item.get("weaknesses"):
        score += 4
    if (item.get("comparative_context") or "").strip():
        score += 8
    if (item.get("critical_assessment") or "").strip():
        score += 8
    if (item.get("google_maps_url") or "").startswith("http"):
        score += 10
    return score


def news_section_id(item: dict) -> str:
    tags = item.get("topic_ids") or []
    for sid in NEWS_SECTION_IDS:
        if sid in tags:
            return sid
    return tags[0] if tags else "world"


def culture_section_id(item: dict) -> str:
    tags = item.get("topic_ids") or []
    return tags[0] if tags else "exhibitions"


def restaurant_section_id(item: dict) -> str:
    tags = item.get("topic_ids") or []
    return tags[0] if tags else "specialist_neighborhood"


def slim_item(item: dict, keys: tuple[str, ...]) -> dict:
    slim = {k: item[k] for k in keys if k in item}
    if "ingestion_source" not in slim:
        slim["ingestion_source"] = "openai"
    return slim


def item_is_citable(item: dict) -> bool:
    if item.get("ingestion_source") in ("rss", "wordpress"):
        return True
    return item.get("url_live") in ("live", "paywalled")


def pick_top_news(items: list[dict], cap: int) -> list[dict]:
    citable = [i for i in items if item_is_citable(i)]
    ranked = sorted(citable, key=score_news_item, reverse=True)
    return [slim_item(i, NEWS_SLIM_ITEM_KEYS) for i in ranked[:cap]]


def culture_item_eligible(item: dict) -> bool:
    """Drop OpenAI candidates whose URL failed HTTP verification."""
    if item.get("ingestion_source") == "openai" and item.get("url_live") is False:
        return False
    return True


def pick_top_culture(items: list[dict], cap: int, priority_venues: set[str], sources_cfg: dict) -> list[dict]:
    eligible = [i for i in items if culture_item_eligible(i)]
    ranked = sorted(
        eligible,
        key=lambda i: score_culture_item(i, priority_venues, sources_cfg),
        reverse=True,
    )
    return [slim_item(i, CULTURE_SLIM_ITEM_KEYS) for i in ranked[:cap]]


def pick_top_restaurants(items: list[dict], cap: int) -> list[dict]:
    verified = [item for item in items if item.get("verified")]
    ranked = sorted(verified, key=score_restaurant_item, reverse=True)
    return [slim_item(i, RESTAURANT_SLIM_ITEM_KEYS) for i in ranked[:cap]]


def news_section_caps(topics_cfg: dict) -> dict[str, int]:
    topics = topic_by_id(topics_cfg)
    caps: dict[str, int] = {}
    for sid in NEWS_SECTION_IDS:
        topic = topics.get(sid) or {}
        caps[sid] = int(topic.get("slim_cap") or (topic.get("max_items", 3) * 4))
    return caps


def culture_section_caps(topics_cfg: dict) -> dict[str, int]:
    topics = topic_by_id(topics_cfg)
    caps: dict[str, int] = {}
    for topic in topics_cfg.get("topics") or []:
        tid = topic.get("id")
        if not tid or not topic.get("enabled", True):
            continue
        caps[tid] = int(topic.get("slim_cap") or (topic.get("max_items", 3) * 2))
    return caps


def restaurant_section_caps(topics_cfg: dict) -> dict[str, int]:
    topics = topic_by_id(topics_cfg)
    caps: dict[str, int] = {}
    for topic in topics_cfg.get("topics") or []:
        tid = topic.get("id")
        if not tid or not topic.get("enabled", True):
            continue
        caps[tid] = int(topic.get("slim_cap") or (topic.get("max_items", 3) * 2))
    if "fine_dining" in topics:
        caps["fine_dining"] = min(caps.get("fine_dining", 4), 4)
    return caps


def culture_priority_venues(sources_cfg: dict) -> set[str]:
    venues: set[str] = set()
    for group in (sources_cfg.get("priority_venues") or {}).values():
        venues.update(group or [])
    return venues


def build_news_synthesis_inbox(raw: dict, *, sources_cfg: dict, topics_cfg: dict) -> dict:
    section_caps = news_section_caps(topics_cfg)
    items = raw.get("items") or []
    by_section: dict[str, list[dict]] = {sid: [] for sid in section_caps}
    read_domains = selected_read_domains(sources_cfg)
    read_pool: list[dict] = []

    for item in items:
        sid = news_section_id(item)
        if sid in by_section:
            by_section[sid].append(item)
        domain = item_domain(item)
        if domain and matches_domain(domain, read_domains):
            read_pool.append(item)

    section_items: list[dict] = []
    section_counts: dict[str, int] = {}
    for sid, cap in section_caps.items():
        picked = pick_top_news(by_section[sid], cap)
        section_counts[sid] = len(picked)
        section_items.extend(picked)

    selected_reads = pick_top_news(read_pool, SELECTED_READS_CAP)

    rel_inbox = str(raw.get("inbox_dir") or "inbox/news")
    return {
        "briefing_type": "news",
        "date": raw.get("date"),
        "source_raw": f"{rel_inbox}/{raw.get('date')}-raw.json",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "model": raw.get("model"),
        "raw_item_count": len(items),
        "section_counts": section_counts,
        "selected_read_candidates": selected_reads,
        "items": section_items,
        "note": (
            "Token-light slice for synthesis. Full warehouse is in -raw.json. "
            "All items come from RSS or WordPress feeds — copy source URLs verbatim."
        ),
    }


def build_culture_synthesis_inbox(raw: dict, *, sources_cfg: dict, topics_cfg: dict) -> dict:
    section_caps = culture_section_caps(topics_cfg)
    priority_venues = culture_priority_venues(sources_cfg)
    items = raw.get("items") or []
    by_section: dict[str, list[dict]] = {sid: [] for sid in section_caps}

    for item in items:
        sid = culture_section_id(item)
        if sid in by_section:
            by_section[sid].append(item)

    section_items: list[dict] = []
    section_counts: dict[str, int] = {}
    for sid, cap in section_caps.items():
        picked = pick_top_culture(by_section[sid], cap, priority_venues, sources_cfg)
        section_counts[sid] = len(picked)
        section_items.extend(picked)

    rel_inbox = str(raw.get("inbox_dir") or "inbox/berlin-culture")
    return {
        "briefing_type": "berlin-culture",
        "date": raw.get("date"),
        "week_start": raw.get("week_start"),
        "week_end": raw.get("week_end"),
        "week_label": raw.get("week_label"),
        "source_raw": f"{rel_inbox}/{raw.get('date')}-raw.json",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "model": raw.get("model"),
        "raw_item_count": len(items),
        "section_counts": section_counts,
        "items": section_items,
        "note": (
            "Token-light culture slice for synthesis. Items with verified:true passed "
            "pre-fetch URL/schedule checks; synthesis spot-checks only unverified Top Picks "
            "and closing-soon items."
        ),
    }


def build_restaurant_synthesis_inbox(raw: dict, *, topics_cfg: dict) -> dict:
    section_caps = restaurant_section_caps(topics_cfg)
    items = raw.get("items") or []
    by_section: dict[str, list[dict]] = {sid: [] for sid in section_caps}

    for item in items:
        sid = restaurant_section_id(item)
        if sid in by_section:
            by_section[sid].append(item)

    section_items: list[dict] = []
    section_counts: dict[str, int] = {}
    for sid, cap in section_caps.items():
        picked = pick_top_restaurants(by_section[sid], cap)
        section_counts[sid] = len(picked)
        section_items.extend(picked)

    rel_inbox = str(raw.get("inbox_dir") or "inbox/berlin-restaurants")
    return {
        "briefing_type": "berlin-restaurants",
        "date": raw.get("date"),
        "source_raw": f"{rel_inbox}/{raw.get('date')}-raw.json",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "model": raw.get("model"),
        "raw_item_count": len(items),
        "verified_count": sum(1 for item in items if item.get("verified")),
        "section_counts": section_counts,
        "items": section_items,
        "note": (
            "Token-light restaurant slice for synthesis. Items included here have verified:true "
            "after Google Places API post-fetch verification when GOOGLE_MAPS_API_KEY is set. "
            "Do not recommend unverified restaurants."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Slim inbox JSON for Cursor synthesis")
    parser.add_argument("--type", default="news", help="Briefing type (default: news)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    if not briefing.prefetch_slim:
        log(f"Briefing type '{args.type}' does not use slim pre-fetch — skipping")
        return 0

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if args.type == "berlin-culture":
        date_str, _ = normalize_tuesday_run_date(date_str)
    elif args.type == "berlin-restaurants":
        date_str, _ = normalize_thursday_run_date(date_str)
    inbox_dir = briefing.inbox_dir
    raw_path = inbox_dir / f"{date_str}-raw.json"
    out_path = inbox_dir / f"{date_str}-synthesis.json"

    if not raw_path.is_file():
        log(f"Missing {raw_path} — run pre-fetch first")
        return 1

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["inbox_dir"] = str(briefing.inbox_dir.relative_to(REPO_ROOT))
    sources_cfg = load_yaml(briefing.sources_path)
    topics_cfg = load_yaml(briefing.topics_path)

    if args.type == "berlin-culture":
        payload = build_culture_synthesis_inbox(raw, sources_cfg=sources_cfg, topics_cfg=topics_cfg)
    elif args.type == "berlin-restaurants":
        payload = build_restaurant_synthesis_inbox(raw, topics_cfg=topics_cfg)
    else:
        payload = build_news_synthesis_inbox(raw, sources_cfg=sources_cfg, topics_cfg=topics_cfg)

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = payload["section_counts"]
    if args.type == "berlin-culture":
        log(
            f"Wrote {out_path} — {payload['raw_item_count']} raw → "
            f"{len(payload['items'])} culture items ({counts})"
        )
    elif args.type == "berlin-restaurants":
        log(
            f"Wrote {out_path} — {payload['raw_item_count']} raw / "
            f"{payload['verified_count']} verified → {len(payload['items'])} restaurant candidates "
            f"({counts})"
        )
    else:
        log(
            f"Wrote {out_path} — {payload['raw_item_count']} raw → "
            f"{len(payload['items'])} news + {len(payload.get('selected_read_candidates') or [])} "
            f"read candidates ({counts})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
