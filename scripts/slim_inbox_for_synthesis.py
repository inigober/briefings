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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from briefing_paths import load_briefing_type
from culture_calendar import (
    enrich_culture_metadata,
    is_press_item,
    is_publisher_venue_item,
    normalize_event_key,
    normalize_official_url,
    normalize_venue_key,
)
from culture_dates import culture_week_date_bounds, normalize_tuesday_run_date
from culture_schedule import filter_programme_items_by_timing
from news_relevance import (
    item_theme_keys,
    load_dedup_entries,
    relevance_cfg,
    score_news_item_with_context,
)
from restaurant_dates import normalize_thursday_run_date

REPO_ROOT = Path(__file__).resolve().parent.parent

NEWS_SECTION_IDS = ("spain", "germany", "berlin", "world")
SELECTED_READS_CAP = 8
SELECTED_READS_CATEGORY_KEYS = (
    "long_form_features",
    "think_tanks",
    "specialist_publications",
    "news_analysis",
)
DEFAULT_SELECTED_READS_MAX_AGE_DAYS = 30
DEFAULT_SELECTED_READS_MAX_PER_PUBLISHER = 2

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
    "relevance_score",
    "sources",
)

NEWS_DEDUP_INDEX_PATH = REPO_ROOT / "state" / "news" / "dedup_index.md"

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
    "series_id",
    "event_kind",
)

CULTURE_MAX_PER_VENUE = 2
CULTURE_MAX_PER_SERIES = 1

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
    for key in SELECTED_READS_CATEGORY_KEYS:
        domains.update(sources_cfg.get(key) or [])
    return domains


def selected_reads_max_age_days(sources_cfg: dict) -> int:
    value = sources_cfg.get("selected_reads_max_age_days")
    if value is not None:
        return int(value)
    return DEFAULT_SELECTED_READS_MAX_AGE_DAYS


def selected_reads_max_per_publisher(sources_cfg: dict) -> int:
    value = sources_cfg.get("selected_reads_max_per_publisher")
    if value is not None:
        return int(value)
    return DEFAULT_SELECTED_READS_MAX_PER_PUBLISHER


def item_published_date(item: dict) -> date | None:
    for src in item.get("sources") or []:
        published_at = (src.get("published_at") or "").strip()
        if not published_at:
            continue
        try:
            return date.fromisoformat(published_at[:10])
        except ValueError:
            continue
    return None


def item_is_fresh_enough(
    item: dict,
    *,
    reference_date: date,
    max_age_days: int,
) -> bool:
    published = item_published_date(item)
    if published is None:
        return True
    return (reference_date - published).days <= max_age_days


def item_publisher_name(item: dict) -> str:
    for src in item.get("sources") or []:
        publisher = (src.get("publisher") or "").strip()
        if publisher:
            return publisher
    domain = item_domain(item)
    return domain or "unknown"


def item_publisher_key(item: dict) -> str:
    """Stable publisher identity for diversity caps (prefer domain over display name)."""
    domain = item_domain(item)
    if domain:
        return domain.lower()
    return item_publisher_name(item).casefold()


def section_max_per_publisher(cap: int, sources_cfg: dict | None = None) -> int:
    """Max items from one publisher in a section's synthesis slice."""
    cfg = relevance_cfg(sources_cfg or {})
    configured = cfg.get("section_max_per_publisher")
    if configured is not None:
        try:
            return max(1, int(configured))
        except (TypeError, ValueError):
            pass
    # Keep at least half the pool open to other outlets (cap=12 → max 6).
    return max(3, (cap + 1) // 2)


def item_read_categories(domain: str, sources_cfg: dict) -> set[str]:
    categories: set[str] = set()
    for key in SELECTED_READS_CATEGORY_KEYS:
        if matches_domain(domain, set(sources_cfg.get(key) or [])):
            categories.add(key)
    return categories


def pick_diversified_selected_reads(
    items: list[dict],
    cap: int,
    sources_cfg: dict,
    *,
    reference_date: date | None = None,
    topic_cfg: dict | None = None,
    dedup_entries: list[dict] | None = None,
) -> list[dict]:
    """Rank read-pool items, enforce publisher caps, and reserve category diversity."""
    ref = reference_date or datetime.now(timezone.utc).date()
    max_age_days = selected_reads_max_age_days(sources_cfg)
    max_per_publisher = selected_reads_max_per_publisher(sources_cfg)
    world_topic = topic_cfg or {}
    dedup = dedup_entries or []

    eligible = [
        item
        for item in items
        if item_is_citable(item)
        and item_is_fresh_enough(item, reference_date=ref, max_age_days=max_age_days)
    ]
    ranked = sorted(
        eligible,
        key=lambda item: score_news_item(
            item,
            section_id="world",
            topic_cfg=world_topic,
            sources_cfg=sources_cfg,
            dedup_entries=dedup,
        ),
        reverse=True,
    )

    picked: list[dict] = []
    publisher_counts: dict[str, int] = {}

    def can_add(item: dict) -> bool:
        return publisher_counts.get(item_publisher_name(item), 0) < max_per_publisher

    def add(item: dict) -> None:
        picked.append(item)
        publisher = item_publisher_name(item)
        publisher_counts[publisher] = publisher_counts.get(publisher, 0) + 1

    category_buckets: dict[str, list[dict]] = {key: [] for key in SELECTED_READS_CATEGORY_KEYS}
    for item in ranked:
        domain = item_domain(item) or ""
        for category in item_read_categories(domain, sources_cfg):
            category_buckets[category].append(item)

    for category in SELECTED_READS_CATEGORY_KEYS:
        if len(picked) >= cap:
            break
        for item in category_buckets[category]:
            if item in picked or not can_add(item):
                continue
            add(item)
            break

    for item in ranked:
        if len(picked) >= cap:
            break
        if item in picked or not can_add(item):
            continue
        add(item)

    return [slim_item(item, NEWS_SLIM_ITEM_KEYS) for item in picked]


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


def score_news_item(
    item: dict,
    *,
    section_id: str = "world",
    topic_cfg: dict | None = None,
    sources_cfg: dict | None = None,
    dedup_entries: list[dict] | None = None,
) -> int:
    score, _ = score_news_item_with_context(
        item,
        section_id=section_id,
        topic_cfg=topic_cfg or {},
        sources_cfg=sources_cfg or {},
        dedup_entries=dedup_entries or [],
    )
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
    if (item.get("event_kind") or "").strip().lower() == "festival_overview":
        score -= 12
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
    """Include items synthesis may cite; drop URLs that failed verify (dead/suspicious)."""
    if item.get("url_live") == "dead":
        return False
    if item.get("ingestion_source") in ("rss", "wordpress"):
        return True
    return item.get("url_live") in ("live", "paywalled")


def pick_top_news(
    items: list[dict],
    cap: int,
    *,
    section_id: str,
    topic_cfg: dict,
    sources_cfg: dict,
    dedup_entries: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Pick top news items with editorial scoring, theme/publisher de-duplication, and audit trail."""
    cfg = relevance_cfg(sources_cfg)
    citable = [item for item in items if item_is_citable(item)]
    max_per_publisher = section_max_per_publisher(cap, sources_cfg)

    scored: list[tuple[dict, int, list[str], list[str]]] = []
    for item in citable:
        score, notes = score_news_item_with_context(
            item,
            section_id=section_id,
            topic_cfg=topic_cfg,
            sources_cfg=sources_cfg,
            dedup_entries=dedup_entries,
        )
        themes = item_theme_keys(item, cfg)
        scored.append((item, score, notes, themes))

    scored.sort(key=lambda row: row[1], reverse=True)

    picked: list[dict] = []
    used_themes: set[str] = set()
    publisher_counts: dict[str, int] = {}
    rejections: list[dict] = []
    audit_window = cap * int(cfg.get("audit_rank_multiplier") or 2)

    for index, (item, score, notes, themes) in enumerate(scored):
        headline = item.get("headline") or item.get("id") or "unknown"
        item_id = item.get("id") or headline

        if len(picked) >= cap:
            if index < audit_window:
                rejections.append(
                    {
                        "id": item_id,
                        "headline": headline,
                        "section": section_id,
                        "reason": "rank_below_cap",
                        "relevance_score": score,
                        "notes": notes,
                    }
                )
            continue

        theme_conflict = next((theme for theme in themes if theme in used_themes), None)
        if theme_conflict:
            rejections.append(
                {
                    "id": item_id,
                    "headline": headline,
                    "section": section_id,
                    "reason": f"theme_cap:{theme_conflict}",
                    "relevance_score": score,
                    "notes": notes,
                }
            )
            continue

        publisher_key = item_publisher_key(item)
        if publisher_counts.get(publisher_key, 0) >= max_per_publisher:
            rejections.append(
                {
                    "id": item_id,
                    "headline": headline,
                    "section": section_id,
                    "reason": f"publisher_cap:{publisher_key}",
                    "relevance_score": score,
                    "notes": notes,
                }
            )
            continue

        slim = slim_item(item, NEWS_SLIM_ITEM_KEYS)
        slim["relevance_score"] = score
        picked.append(slim)
        used_themes.update(themes)
        publisher_counts[publisher_key] = publisher_counts.get(publisher_key, 0) + 1

    return picked, rejections


def culture_item_eligible(item: dict, *, sources_cfg: dict | None = None) -> bool:
    """Drop dead URLs and editorial press items (not venue programme)."""
    if item.get("url_live") is False:
        return False
    if sources_cfg:
        if is_press_item(item, sources_cfg) or is_publisher_venue_item(item, sources_cfg):
            return False
    return True


class CulturePickState:
    """Cross-section caps when building the culture synthesis slice."""

    def __init__(self) -> None:
        self.used_event_keys: set[str] = set()
        self.used_series_ids: set[str] = set()
        self.used_urls: set[str] = set()
        self.venue_counts: dict[str, int] = {}
        self.rejected: list[dict] = []

    def rejection_reason(self, item: dict) -> str | None:
        event_key = normalize_event_key(item)
        if event_key in self.used_event_keys:
            return "event_duplicate"

        series_id = (item.get("series_id") or "").strip()
        if series_id and series_id in self.used_series_ids:
            return f"series_cap:{series_id}"

        url = normalize_official_url(item.get("official_url") or "")
        if url and url in self.used_urls:
            return "duplicate_url"

        venue_key = normalize_venue_key(item.get("venue") or "")
        if venue_key and self.venue_counts.get(venue_key, 0) >= CULTURE_MAX_PER_VENUE:
            return f"venue_cap:{venue_key}"

        return None

    def accept(self, item: dict) -> None:
        event_key = normalize_event_key(item)
        self.used_event_keys.add(event_key)
        series_id = (item.get("series_id") or "").strip()
        if series_id:
            self.used_series_ids.add(series_id)
        url = normalize_official_url(item.get("official_url") or "")
        if url:
            self.used_urls.add(url)
        venue_key = normalize_venue_key(item.get("venue") or "")
        if venue_key:
            self.venue_counts[venue_key] = self.venue_counts.get(venue_key, 0) + 1


def pick_top_culture(
    items: list[dict],
    cap: int,
    priority_venues: set[str],
    sources_cfg: dict,
    *,
    pick_state: CulturePickState | None = None,
    section_id: str = "",
) -> list[dict]:
    eligible = [i for i in items if culture_item_eligible(i, sources_cfg=sources_cfg)]
    ranked = sorted(
        eligible,
        key=lambda i: score_culture_item(i, priority_venues, sources_cfg),
        reverse=True,
    )

    picked: list[dict] = []
    state = pick_state or CulturePickState()

    for item in ranked:
        if len(picked) >= cap:
            break

        enriched = enrich_culture_metadata(dict(item))
        reason = state.rejection_reason(enriched)
        if reason:
            state.rejected.append(
                {
                    "id": enriched.get("id") or enriched.get("title"),
                    "title": enriched.get("title"),
                    "section": section_id,
                    "reason": reason,
                    "series_id": enriched.get("series_id") or "",
                    "venue": enriched.get("venue") or "",
                }
            )
            continue

        state.accept(enriched)
        picked.append(slim_item(enriched, CULTURE_SLIM_ITEM_KEYS))

    return picked


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


def _parse_briefing_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(str(date_str)[:10])
    except ValueError:
        return None


def build_news_synthesis_inbox(
    raw: dict,
    *,
    sources_cfg: dict,
    topics_cfg: dict,
    dedup_path: Path | None = None,
) -> dict:
    section_caps = news_section_caps(topics_cfg)
    topics = topic_by_id(topics_cfg)
    items = raw.get("items") or []
    by_section: dict[str, list[dict]] = {sid: [] for sid in section_caps}
    read_domains = selected_read_domains(sources_cfg)
    read_pool: list[dict] = []

    reference_date = _parse_briefing_date(raw.get("date")) or datetime.now(timezone.utc).date()
    rel_cfg = relevance_cfg(sources_cfg)
    dedup_entries = load_dedup_entries(
        dedup_path or NEWS_DEDUP_INDEX_PATH,
        reference_date=reference_date,
        lookback_days=int(rel_cfg.get("dedup_lookback_days") or 7),
    )

    for item in items:
        sid = news_section_id(item)
        if sid in by_section:
            by_section[sid].append(item)
        domain = item_domain(item)
        if domain and matches_domain(domain, read_domains):
            read_pool.append(item)

    section_items: list[dict] = []
    section_counts: dict[str, int] = {}
    rejected_candidates: list[dict] = []
    for sid, cap in section_caps.items():
        picked, rejections = pick_top_news(
            by_section[sid],
            cap,
            section_id=sid,
            topic_cfg=topics.get(sid) or {},
            sources_cfg=sources_cfg,
            dedup_entries=dedup_entries,
        )
        section_counts[sid] = len(picked)
        section_items.extend(picked)
        rejected_candidates.extend(rejections)

    selected_reads = pick_diversified_selected_reads(
        read_pool,
        SELECTED_READS_CAP,
        sources_cfg,
        reference_date=reference_date,
        topic_cfg=topics.get("world") or {},
        dedup_entries=dedup_entries,
    )

    recent_topics = [
        {
            "slug": entry["slug"],
            "section": entry["section"],
            "date": entry["date"],
        }
        for entry in dedup_entries
    ]

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
        "editorial_context": {
            "recent_topics": recent_topics,
            "rejected_candidates": rejected_candidates,
            "note": (
                "Pre-ranked with editorial relevance from topics.yaml, dedup_index.md, "
                "and news_relevance rules in sources.yaml. Synthesis must still apply "
                "hard reject rules in news-briefing-style.mdc."
            ),
        },
        "note": (
            "Token-light slice for synthesis. Full warehouse is in -raw.json. "
            "All items come from RSS or WordPress feeds — copy source URLs verbatim."
        ),
    }


def build_culture_synthesis_inbox(raw: dict, *, sources_cfg: dict, topics_cfg: dict) -> dict:
    section_caps = culture_section_caps(topics_cfg)
    priority_venues = culture_priority_venues(sources_cfg)
    items = list(raw.get("items") or [])

    run_date_str = raw.get("date")
    if run_date_str:
        try:
            _, run_dt = normalize_tuesday_run_date(str(run_date_str)[:10])
            week_start, week_end = culture_week_date_bounds(run_dt)
            horizon_days = int(sources_cfg.get("advance_horizon_days") or 14)
            items, dropped, advance_routed = filter_programme_items_by_timing(
                items,
                week_start,
                week_end,
                horizon_days=horizon_days,
            )
            if dropped or advance_routed:
                raw = {
                    **raw,
                    "window_filtered_count": dropped,
                    "window_advance_routed": advance_routed,
                }
        except ValueError:
            pass

    by_section: dict[str, list[dict]] = {sid: [] for sid in section_caps}

    for item in items:
        sid = culture_section_id(item)
        if sid in by_section:
            by_section[sid].append(item)

    section_items: list[dict] = []
    section_counts: dict[str, int] = {}
    pick_state = CulturePickState()

    # Core sections first so cross-section caps favour exhibitions/film/performance/music.
    section_order = [
        t.get("id")
        for t in topics_cfg.get("topics") or []
        if t.get("enabled", True) and t.get("id") in section_caps
    ]
    for sid in section_order:
        cap = section_caps[sid]
        picked = pick_top_culture(
            by_section[sid],
            cap,
            priority_venues,
            sources_cfg,
            pick_state=pick_state,
            section_id=sid,
        )
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
        "editorial_context": {
            "rejected_candidates": pick_state.rejected,
            "diversification_caps": {
                "max_per_venue": CULTURE_MAX_PER_VENUE,
                "max_per_series": CULTURE_MAX_PER_SERIES,
            },
            "note": (
                "Pre-ranked with venue/series/event de-duplication across sections. "
                "Synthesis must still apply one-event-one-slot and Top Picks cross-reference rules."
            ),
        },
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
