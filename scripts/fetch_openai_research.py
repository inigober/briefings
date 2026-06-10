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

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MODEL = "gpt-5.5"
API_TIMEOUT_SECONDS = 600.0
PARALLEL_WORKERS = 5

SECTION_MIN_ITEMS: dict[str, int] = {
    "spain": 15,
    "germany": 15,
    "berlin": 12,
    "world": 25,
}

SELECTED_READS_MIN = 15

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

SELECTED_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "url": {"type": "string"},
        "publisher": {"type": "string"},
        "type": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["title", "url", "publisher", "type", "summary"],
    "additionalProperties": False,
}

SELECTED_READS_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_read_candidates": {"type": "array", "items": SELECTED_READ_SCHEMA},
        "search_notes": {"type": "string"},
    },
    "required": ["selected_read_candidates", "search_notes"],
    "additionalProperties": False,
}


def log(message: str) -> None:
    print(message, flush=True)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def topic_by_id(topics_cfg: dict) -> dict[str, dict]:
    return {t["id"]: t for t in topics_cfg.get("topics", []) if t.get("id")}


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
) -> str:
    name = topic.get("name", topic.get("id", ""))
    desc = (topic.get("description") or "").strip()
    priorities = ", ".join(topic.get("priority_categories") or [])
    avoid = ", ".join(topic.get("avoid_unless_material") or [])
    preferred = ", ".join(preferred_sources) or "(see allowed domains)"
    domains = "\n".join(f"- {d}" for d in allowed_domains[:40])

    world_extra = ""
    if topic.get("id") == "world":
        world_extra = """
World-specific requirements:
- At least 5 items each from non-European regions (Americas, East Asia, South Asia, Middle East, Africa)
- Prefer: India, China, Brazil, Mexico, Nigeria, Indonesia, Japan, South Korea, United States, South Africa
- Do NOT mirror Spain/Germany stories
- Run separate searches per region if needed
"""

    berlin_extra = ""
    if topic.get("id") == "berlin":
        berlin_extra = """
Berlin-specific requirements:
- Local Berlin news ONLY (not generic Germany)
- Prioritize Tagesspiegel, Berliner Zeitung, rbb24, The Berliner
"""

    return f"""Gather raw research for ONE section of a personal daily briefing. Today is {date_str}.

Section: {name} (id: {topic.get("id")})
Minimum items: {min_items}
Description: {desc}
Priority categories: {priorities}
Avoid unless material development: {avoid or "none"}
Preferred publishers (weight heavily — diversify, do not use one outlet for all items): {preferred}

Allowed domains:
{domains}
{world_extra}{berlin_extra}

Rules:
- Full article URLs only (never homepages, never truncated URLs)
- Material developments over commentary
- Include structural / underreported stories
- Vary publishers — never return all items from a single outlet
- Cast a wide net; synthesis will trim to 3 items later

Return JSON matching the schema with keys: items, gaps, search_notes."""


def build_selected_reads_prompt(*, date_str: str, sources_cfg: dict, allowed_domains: list[str]) -> str:
    long_form = ", ".join(sources_cfg.get("long_form_features") or [])
    think_tanks = ", ".join(sources_cfg.get("think_tanks") or [])
    specialist = ", ".join(sources_cfg.get("specialist_publications") or [])
    news = ", ".join(sources_cfg.get("news_analysis") or [])
    domains = "\n".join(f"- {d}" for d in allowed_domains[:40])

    return f"""Gather {SELECTED_READS_MIN}+ candidate articles for "Selected Reads" for {date_str}.

Mix required:
- Long-form features ({long_form})
- Think-tank / research ({think_tanks})
- Specialist publications ({specialist})
- News analysis ({news})

Allowed domains:
{domains}

Rules:
- Full article URLs only
- Diversify publishers and types
- Max 1 Reuters/AP item in this batch
- type must be one of: long_form_feature, think_tank_research, specialist_publication, news_analysis

Return JSON with keys: selected_read_candidates, search_notes."""


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
    source_priorities = sources_cfg.get("source_priorities") or {}

    topic = topics.get(section_id)
    if not topic or not topic.get("enabled", True):
        return section_id, {"items": [], "gaps": [], "search_notes": ""}

    min_items = SECTION_MIN_ITEMS[section_id]
    preferred = source_priorities.get(section_id) or []
    prompt = build_section_prompt(
        date_str=date_str,
        topic=topic,
        min_items=min_items,
        preferred_sources=preferred,
        allowed_domains=allowed_domains,
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
        item.setdefault("topic_ids", [section_id])
    elapsed = time.monotonic() - started
    log(f"  [{section_id}] done in {elapsed:.0f}s ({len(items)} items)")
    return section_id, result


def fetch_selected_reads(
    *,
    date_str: str,
    model: str,
    sources_cfg: dict,
) -> dict:
    allowed_domains = sources_cfg.get("allowed_domains") or []
    reads_prompt = build_selected_reads_prompt(
        date_str=date_str,
        sources_cfg=sources_cfg,
        allowed_domains=allowed_domains,
    )

    started = time.monotonic()
    log(f"  [selected_reads] started (min {SELECTED_READS_MIN})...")
    client = make_client()
    result = fetch_structured(
        client=client,
        model=model,
        prompt=reads_prompt,
        schema=SELECTED_READS_RESULT_SCHEMA,
        schema_name="briefing_selected_reads",
        domains=allowed_domains,
    )
    count = len(result.get("selected_read_candidates") or [])
    elapsed = time.monotonic() - started
    log(f"  [selected_reads] done in {elapsed:.0f}s ({count} candidates)")
    return result


def fetch_all_research(
    *,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
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
    reads_result: dict = {"selected_read_candidates": [], "search_notes": ""}

    started = time.monotonic()
    log(f"  Launching {len(section_ids) + 1} fetches in parallel...")

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
        futures[
            executor.submit(
                fetch_selected_reads,
                date_str=date_str,
                model=model,
                sources_cfg=sources_cfg,
            )
        ] = "selected_reads"

        for future in as_completed(futures):
            task_name = futures[future]
            if task_name == "selected_reads":
                reads_result = future.result()
                if reads_result.get("search_notes"):
                    notes.append(f"selected_reads: {reads_result['search_notes']}")
                continue

            section_id, result = future.result()
            items = result.get("items") or []
            all_items.extend(items)
            section_counts[section_id] = len(items)
            all_gaps.extend(result.get("gaps") or [])
            if result.get("search_notes"):
                notes.append(f"{section_id}: {result['search_notes']}")

    elapsed = time.monotonic() - started
    log(f"  All fetches finished in {elapsed:.0f}s")

    publishers: dict[str, int] = {}
    for item in all_items:
        for src in item.get("sources") or []:
            pub = src.get("publisher") or "unknown"
            publishers[pub] = publishers.get(pub, 0) + 1

    return {
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "items": all_items,
        "selected_read_candidates": reads_result.get("selected_read_candidates") or [],
        "gaps": all_gaps,
        "search_notes": (
            f"Section counts: {section_counts}. "
            f"Publisher mix: {publishers}. "
            + " ".join(notes)
        ).strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch daily briefing research via OpenAI web_search")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--model", default=os.environ.get("OPENAI_RESEARCH_MODEL", DEFAULT_MODEL))
    parser.add_argument("--dry-run", action="store_true", help="Print first section prompt only; do not call API")
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
            preferred_sources=(sources_cfg.get("source_priorities") or {}).get("spain", []),
            allowed_domains=sources_cfg.get("allowed_domains") or [],
        )
        log(prompt)
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        log("OPENAI_API_KEY is not set")
        return 1

    inbox_dir = REPO_ROOT / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-raw.json"

    log(f"Fetching research for {date_str} with model {args.model}...")
    try:
        payload = fetch_all_research(
            date_str=date_str,
            model=args.model,
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
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
