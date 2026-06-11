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
    "why_candidate",
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
    if item.get("ingestion_source") != "rss":
        score += 20
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


def score_culture_item(item: dict, priority_venues: set[str]) -> int:
    score = 0
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


def slim_item(item: dict, keys: tuple[str, ...]) -> dict:
    slim = {k: item[k] for k in keys if k in item}
    if "ingestion_source" not in slim:
        slim["ingestion_source"] = "openai"
    return slim


def pick_top_news(items: list[dict], cap: int) -> list[dict]:
    ranked = sorted(items, key=score_news_item, reverse=True)
    return [slim_item(i, NEWS_SLIM_ITEM_KEYS) for i in ranked[:cap]]


def pick_top_culture(items: list[dict], cap: int, priority_venues: set[str]) -> list[dict]:
    ranked = sorted(
        items,
        key=lambda i: score_culture_item(i, priority_venues),
        reverse=True,
    )
    return [slim_item(i, CULTURE_SLIM_ITEM_KEYS) for i in ranked[:cap]]


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
            "Prefer OpenAI-sourced items with why_it_matters/broader_context filled."
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
        picked = pick_top_culture(by_section[sid], cap, priority_venues)
        section_counts[sid] = len(picked)
        section_items.extend(picked)

    rel_inbox = str(raw.get("inbox_dir") or "inbox/berlin-culture")
    return {
        "briefing_type": "berlin-culture",
        "date": raw.get("date"),
        "week_start": raw.get("week_start"),
        "week_end": raw.get("week_end"),
        "source_raw": f"{rel_inbox}/{raw.get('date')}-raw.json",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "model": raw.get("model"),
        "raw_item_count": len(items),
        "section_counts": section_counts,
        "items": section_items,
        "note": (
            "Token-light culture slice for synthesis. Synthesis must verify official_url "
            "for each shortlisted pick before including."
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
    else:
        payload = build_news_synthesis_inbox(raw, sources_cfg=sources_cfg, topics_cfg=topics_cfg)

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = payload["section_counts"]
    if args.type == "berlin-culture":
        log(
            f"Wrote {out_path} — {payload['raw_item_count']} raw → "
            f"{len(payload['items'])} culture items ({counts})"
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
