#!/usr/bin/env python3
"""Pre-fetch daily research via OpenAI Responses API + web_search."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# gpt-4.1: cheaper than gpt-5.5, still strong for web_search orchestration.
# Override via OPENAI_RESEARCH_MODEL (e.g. gpt-5.5) if quality drops.
DEFAULT_MODEL = "gpt-4.1"
API_TIMEOUT_SECONDS = 600.0
PARALLEL_WORKERS = 5

SECTION_MIN_ITEMS: dict[str, int] = {
    "spain": 7,
    "germany": 7,
    "berlin": 6,
    "world": 12,
}

SOURCE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "url": {"type": "string"},
        "publisher": {"type": "string"},
        "published_at": {"type": ["string", "null"]},
    },
    "required": ["title", "url", "publisher", "published_at"],
    "additionalProperties": False,
}

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "topic_ids": {"type": "array", "items": {"type": "string"}},
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "broader_context": {"type": "string"},
        "region": {"type": "string"},
        "country": {"type": "string"},
        "is_structural": {"type": "boolean"},
        "is_follow_up": {"type": "boolean"},
        "material_development": {"type": "boolean"},
        "sources": {"type": "array", "items": SOURCE_SCHEMA},
    },
    "required": [
        "id",
        "topic_ids",
        "headline",
        "summary",
        "why_it_matters",
        "broader_context",
        "region",
        "country",
        "is_structural",
        "is_follow_up",
        "material_development",
        "sources",
    ],
    "additionalProperties": False,
}

SECTION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": ITEM_SCHEMA},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "search_notes": {"type": "string"},
    },
    "required": ["items", "gaps", "search_notes"],
    "additionalProperties": False,
}


def log(message: str) -> None:
    print(message, flush=True)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def topic_by_id(topics_cfg: dict) -> dict[str, dict]:
    return {t["id"]: t for t in topics_cfg.get("topics", []) if t.get("id")}


def resolve_preferred_sources(section_id: str, sources_cfg: dict) -> list[str]:
    priorities = sources_cfg.get("source_priorities") or {}
    if section_id == "world":
        return priorities.get("world") or priorities.get("international") or []
    return priorities.get(section_id) or []


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def build_diversity_rules(section_id: str, sources_cfg: dict) -> str:
    if section_id == "germany":
        news = ", ".join(sources_cfg.get("germany_news_outlets") or [])
        research = ", ".join(sources_cfg.get("germany_research_outlets") or [])
        return f"""
Germany publisher diversity (strict):
- At least 5 items must be news articles from newspapers: {news}
- At most 2 items from research institutes: {research}
- Max 2 items from any single publisher
- Run separate web searches per outlet (e.g. "site:zeit.de Germany", "site:tagesspiegel.de")
- Prefer coalition politics, labour, industry, healthcare NEWS over survey roundups
"""

    if section_id == "berlin":
        return """
Berlin publisher diversity (strict):
- Max 3 items from rbb24; at least 2 from tagesspiegel.de
- At least 1 from berliner-zeitung.de or the-berliner.com
- Run explicit searches: "site:tagesspiegel.de Berlin", "site:berliner-zeitung.de"
- Local Berlin news ONLY — not generic Germany or Brandenburg unless directly affecting Berlin
"""

    if section_id == "world":
        return """
World publisher diversity (strict):
- Max 3 items from any single publisher
- At least 2 items from ft.com, economist.com, or theguardian.com combined
- At least 1 item from asia.nikkei.com or foreignaffairs.com
- Use separate searches per region AND per outlet
- Geographic balance: at least 2 items each in Americas, East Asia, South Asia, Middle East, Africa
- Do NOT mirror Spain/Germany stories already covered elsewhere
"""

    if section_id == "spain":
        return """
Spain publisher diversity:
- Max 3 items from any single publisher
- Include at least 1 from eldiario.es and 1 from elconfidencial.com if material exists
- Mix national and regional (Catalonia, Basque Country, Andalusia) where relevant
"""

    return ""


def extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        return json.loads(fence.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("Could not parse JSON from model response")


def collect_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            if getattr(content, "type", None) == "output_text":
                parts.append(content.text)
    return "\n".join(parts).strip()


def build_section_prompt(
    *,
    date_str: str,
    topic: dict,
    min_items: int,
    preferred_sources: list[str],
    allowed_domains: list[str],
    sources_cfg: dict,
) -> str:
    name = topic.get("name", topic.get("id", ""))
    desc = (topic.get("description") or "").strip()
    priorities = ", ".join(topic.get("priority_categories") or [])
    avoid = ", ".join(topic.get("avoid_unless_material") or [])
    preferred = ", ".join(preferred_sources) or "(see allowed domains)"
    domains = "\n".join(f"- {d}" for d in allowed_domains[:40])

    section_id = topic.get("id", "")
    diversity = build_diversity_rules(section_id, sources_cfg)

    return f"""Gather raw research for ONE section of a personal daily briefing. Today is {date_str}.

Section: {name} (id: {section_id})
Minimum items: {min_items}
Description: {desc}
Priority categories: {priorities}
Avoid unless material development: {avoid or "none"}
Preferred publishers (search each outlet separately — do not rely on one domain): {preferred}
{diversity}
Allowed domains:
{domains}

Rules:
- Full article URLs only (never homepages, never truncated URLs)
- Material developments over commentary
- Include structural / underreported stories
- topic_ids MUST start with the section id ("{section_id}") as the first element, then optional theme tags
- Cast a wide net within the minimum; synthesis will trim to 3 items later
- RSS headlines may already cover some outlets — prioritise paywalled / licensed sources and gaps
- In search_notes, report item count per publisher

Return JSON matching the schema with keys: items, gaps, search_notes."""


def make_client() -> Any:
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=API_TIMEOUT_SECONDS,
    )


def fetch_structured(
    *,
    client: Any,
    model: str,
    prompt: str,
    schema: dict,
    schema_name: str,
    domains: list[str],
) -> dict:
    tools: list[dict] = [{"type": "web_search"}]
    if domains:
        tools[0]["filters"] = {"allowed_domains": domains}

    response = client.responses.create(
        model=model,
        tools=tools,
        input=prompt,
        reasoning={"effort": "low"},
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    )

    output_text = collect_output_text(response)
    if not output_text:
        raise RuntimeError("Empty response from OpenAI")

    try:
        return extract_json(output_text)
    except ValueError as exc:
        raise ValueError(f"{exc}\n\nRaw output:\n{output_text[:4000]}") from exc


def fetch_section(
    *,
    section_id: str,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
) -> tuple[str, dict]:
    topics = topic_by_id(topics_cfg)
    allowed_domains = sources_cfg.get("allowed_domains") or []

    topic = topics.get(section_id)
    if not topic or not topic.get("enabled", True):
        return section_id, {"items": [], "gaps": [], "search_notes": ""}

    min_items = SECTION_MIN_ITEMS[section_id]
    preferred = resolve_preferred_sources(section_id, sources_cfg)
    prompt = build_section_prompt(
        date_str=date_str,
        topic=topic,
        min_items=min_items,
        preferred_sources=preferred,
        allowed_domains=allowed_domains,
        sources_cfg=sources_cfg,
    )

    started = time.monotonic()
    log(f"  [{section_id}] started (min {min_items} items)...")
    client = make_client()
    result = fetch_structured(
        client=client,
        model=model,
        prompt=prompt,
        schema=SECTION_RESULT_SCHEMA,
        schema_name=f"briefing_section_{section_id}",
        domains=allowed_domains,
    )
    items = result.get("items") or []
    for item in items:
        tags = [t for t in (item.get("topic_ids") or []) if t != section_id]
        item["topic_ids"] = [section_id, *tags]
    elapsed = time.monotonic() - started
    log(f"  [{section_id}] done in {elapsed:.0f}s ({len(items)} items)")
    return section_id, result


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


def merge_rss_items(openai_items: list[dict], rss_items: list[dict]) -> tuple[list[dict], int]:
    """Merge RSS headlines; OpenAI items win on URL collision (richer fields)."""
    seen: set[str] = set()
    merged: list[dict] = []

    for item in openai_items:
        for src in item.get("sources") or []:
            url = src.get("url") or ""
            if url:
                seen.add(normalize_url(url))
        merged.append(item)

    added = 0
    for item in rss_items:
        urls = [normalize_url(s.get("url") or "") for s in (item.get("sources") or [])]
        urls = [u for u in urls if u]
        if not urls or any(u in seen for u in urls):
            continue
        for u in urls:
            seen.add(u)
        merged.append(item)
        added += 1

    return merged, added


def fetch_all_research(
    *,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
    rss_items: list[dict] | None = None,
) -> dict:
    topics = topic_by_id(topics_cfg)
    section_ids = [
        section_id
        for section_id in ("spain", "germany", "berlin", "world")
        if (topics.get(section_id) or {}).get("enabled", True)
    ]

    all_items: list[dict] = []
    all_gaps: list[str] = []
    notes: list[str] = []
    section_counts: dict[str, int] = {}

    started = time.monotonic()
    log(f"  Launching {len(section_ids)} section fetches in parallel...")

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(
                fetch_section,
                section_id=section_id,
                date_str=date_str,
                model=model,
                topics_cfg=topics_cfg,
                sources_cfg=sources_cfg,
            ): section_id
            for section_id in section_ids
        }

        for future in as_completed(futures):
            section_id = futures[future]
            section_id, result = future.result()
            items = result.get("items") or []
            all_items.extend(items)
            section_counts[section_id] = len(items)
            all_gaps.extend(result.get("gaps") or [])
            if result.get("search_notes"):
                notes.append(f"{section_id}: {result['search_notes']}")

    elapsed = time.monotonic() - started
    log(f"  All OpenAI fetches finished in {elapsed:.0f}s")

    rss_merged = 0
    if rss_items:
        all_items, rss_merged = merge_rss_items(all_items, rss_items)
        if rss_merged:
            log(f"  Merged {rss_merged} RSS items (deduped against OpenAI)")

    publishers: dict[str, int] = {}
    ingestion: dict[str, int] = {"openai": 0, "rss": 0}
    for item in all_items:
        source = item.get("ingestion_source") or "openai"
        ingestion[source] = ingestion.get(source, 0) + 1
        for src in item.get("sources") or []:
            pub = src.get("publisher") or "unknown"
            publishers[pub] = publishers.get(pub, 0) + 1

    return {
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "items": all_items,
        "gaps": all_gaps,
        "search_notes": (
            f"Section counts (OpenAI): {section_counts}. "
            f"Ingestion: {ingestion}. "
            f"RSS merged: {rss_merged}. "
            f"Publisher mix: {publishers}. "
            + " ".join(notes)
        ).strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch daily briefing research via OpenAI web_search")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--model", default=os.environ.get("OPENAI_RESEARCH_MODEL", DEFAULT_MODEL))
    parser.add_argument("--dry-run", action="store_true", help="Print first section prompt only; do not call API")
    parser.add_argument(
        "--no-rss-merge",
        action="store_true",
        help="Do not merge inbox/YYYY-MM-DD-rss.json even if present",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    topics_cfg = load_yaml(REPO_ROOT / "config" / "topics.yaml")
    sources_cfg = load_yaml(REPO_ROOT / "config" / "sources.yaml")

    if args.dry_run:
        topic = topic_by_id(topics_cfg)["spain"]
        prompt = build_section_prompt(
            date_str=date_str,
            topic=topic,
            min_items=SECTION_MIN_ITEMS["spain"],
            preferred_sources=resolve_preferred_sources("spain", sources_cfg),
            allowed_domains=sources_cfg.get("allowed_domains") or [],
            sources_cfg=sources_cfg,
        )
        log(prompt)
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        log("OPENAI_API_KEY is not set")
        return 1

    inbox_dir = REPO_ROOT / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-raw.json"

    rss_items: list[dict] = []
    if not args.no_rss_merge:
        rss_items = load_rss_items(inbox_dir, date_str)
        if rss_items:
            log(f"  Found {len(rss_items)} RSS items to merge")

    log(f"Fetching research for {date_str} with model {args.model}...")
    try:
        payload = fetch_all_research(
            date_str=date_str,
            model=args.model,
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
            rss_items=rss_items,
        )
    except Exception as exc:
        err_path = inbox_dir / f"{date_str}-raw.error.txt"
        err_path.write_text(str(exc) + "\n", encoding="utf-8")
        log(str(exc))
        return 1

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"Wrote {out_path} ({len(payload.get('items') or [])} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
