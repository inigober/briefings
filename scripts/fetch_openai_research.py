#!/usr/bin/env python3
"""Pre-fetch daily research via OpenAI Responses API + web_search."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from briefing_paths import load_briefing_type
from openai_spend import (
    DailySpendLedger,
    SpendCapExceeded,
    handle_cap_abort,
    resolve_daily_cap,
    usage_from_response,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

NEWS_SECTION_IDS = ("spain", "germany", "berlin", "world")

# gpt-4.1: cheaper than gpt-5.5, still strong for web_search orchestration.
# Override via OPENAI_RESEARCH_MODEL (e.g. gpt-5.5) if quality drops.
DEFAULT_MODEL = "gpt-4.1"
API_TIMEOUT_SECONDS = 600.0
PARALLEL_WORKERS = 5

# Base OpenAI targets when RSS is empty. Reduced dynamically when RSS covers a section.
SECTION_MIN_ITEMS: dict[str, int] = {
    "spain": 7,
    "germany": 7,
    "berlin": 6,
    "world": 12,
}

OPENAI_MIN_FLOOR = 3
RSS_SATURATION_HIGH = 10  # RSS items → OpenAI asks for floor minimum only
RSS_SATURATION_MID = 6  # RSS items → OpenAI asks for ~half of base
RSS_DOMAIN_SKIP_THRESHOLD = 3  # Skip domain in web_search if RSS has this many

# Always keep in web_search filters — licensing/paywall value RSS headlines alone can't replace.
PREMIUM_DOMAINS: frozenset[str] = frozenset(
    {
        "ft.com",
        "economist.com",
        "bloomberg.com",
        "nytimes.com",
        "politico.eu",
        "politico.com",
        "theinformation.com",
        "foreignaffairs.com",
        "elconfidencial.com",
        "handelsblatt.com",
        "asia.nikkei.com",
    }
)

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


def resolve_model(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    env = (os.environ.get("OPENAI_RESEARCH_MODEL") or "").strip()
    return env or DEFAULT_MODEL


def host_to_allowed_domain(host: str, allowed_domains: list[str]) -> str | None:
    host = host.lower().removeprefix("www.")
    for domain in allowed_domains:
        if host == domain or host.endswith(f".{domain}"):
            return domain
    return None


@dataclass
class SectionRssContext:
    section_id: str
    item_count: int = 0
    publishers: dict[str, int] = field(default_factory=dict)
    domains: dict[str, int] = field(default_factory=dict)
    headlines: list[str] = field(default_factory=list)


def group_rss_by_section(rss_items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {sid: [] for sid in SECTION_MIN_ITEMS}
    for item in rss_items:
        section_id = (item.get("topic_ids") or ["world"])[0]
        if section_id in groups:
            groups[section_id].append(item)
    return groups


def analyze_rss_section(
    section_id: str,
    items: list[dict],
    allowed_domains: list[str],
) -> SectionRssContext:
    ctx = SectionRssContext(section_id=section_id, item_count=len(items))
    for item in items:
        headline = (item.get("headline") or "").strip()
        if headline and len(ctx.headlines) < 8:
            ctx.headlines.append(headline)

        for src in item.get("sources") or []:
            publisher = (src.get("publisher") or "unknown").strip()
            ctx.publishers[publisher] = ctx.publishers.get(publisher, 0) + 1

            url = src.get("url") or ""
            if not url:
                continue
            host = urlparse(url).netloc
            domain = host_to_allowed_domain(host, allowed_domains)
            if domain:
                ctx.domains[domain] = ctx.domains.get(domain, 0) + 1

    return ctx


def openai_prefetch_cfg(sources_cfg: dict) -> dict:
    cfg = sources_cfg.get("openai_prefetch") or {}
    return {
        "enabled": cfg.get("enabled", True),
        "skip_when_section_rss_at_least": int(cfg.get("skip_when_section_rss_at_least", 8)),
    }


def should_skip_openai_section(section_id: str, rss_count: int, sources_cfg: dict) -> bool:
    cfg = openai_prefetch_cfg(sources_cfg)
    if not cfg["enabled"]:
        return True
    threshold = cfg["skip_when_section_rss_at_least"]
    if threshold <= 0:
        return False
    return rss_count >= threshold


def openai_min_for_section(section_id: str, rss_count: int) -> int:
    base = SECTION_MIN_ITEMS[section_id]
    floor = OPENAI_MIN_FLOOR
    if rss_count == 0:
        return base
    if rss_count >= RSS_SATURATION_HIGH:
        return floor
    if rss_count >= RSS_SATURATION_MID:
        return max(floor, (base + floor) // 2)
    reduction = min(rss_count, base - floor)
    return max(floor, base - reduction)


def narrow_domains_for_openai(
    *,
    allowed_domains: list[str],
    preferred_sources: list[str],
    rss_domains: dict[str, int],
) -> list[str]:
    narrowed: list[str] = []
    for domain in allowed_domains:
        rss_hits = rss_domains.get(domain, 0)
        if domain in PREMIUM_DOMAINS or rss_hits < RSS_DOMAIN_SKIP_THRESHOLD:
            narrowed.append(domain)

    for domain in preferred_sources:
        if domain in allowed_domains and domain not in narrowed:
            narrowed.append(domain)

    return narrowed or list(allowed_domains)


def build_rss_prompt_block(
    ctx: SectionRssContext,
    *,
    base_min: int,
    openai_min: int,
    skipped_domains: list[str],
) -> str:
    if ctx.item_count == 0:
        return ""

    pub_summary = ", ".join(
        f"{name} ({count})"
        for name, count in sorted(ctx.publishers.items(), key=lambda x: -x[1])[:8]
    )
    lines = [
        "## RSS warehouse (already collected — do not duplicate)",
        f"- {ctx.item_count} headlines already ingested for this section via RSS (free feeds).",
        f"- Publishers covered: {pub_summary or 'n/a'}",
        f"- OpenAI minimum reduced from {base_min} to {openai_min} — search for **gaps only**.",
        "- Prioritise: paywalled/licensed outlets, structural trends, underreported stories RSS missed.",
        "- Do NOT re-search outlets RSS already saturated unless you add a distinct paywalled angle.",
    ]
    if skipped_domains:
        lines.append(f"- Domains excluded from this web_search (RSS-saturated): {', '.join(skipped_domains)}")
    if ctx.headlines:
        lines.append("- Sample RSS headlines already in warehouse:")
        lines.extend(f"  • {h}" for h in ctx.headlines[:6])
    return "\n".join(lines) + "\n\n"


def build_diversity_rules(section_id: str, sources_cfg: dict, *, rss_count: int = 0) -> str:
    light = rss_count >= RSS_SATURATION_MID
    if section_id == "germany":
        news = ", ".join(sources_cfg.get("germany_news_outlets") or [])
        research = ", ".join(sources_cfg.get("germany_research_outlets") or [])
        if light:
            return f"""
Germany (RSS-heavy — gap-fill mode):
- RSS already covers major newspapers; focus on paywalled sources and research gaps
- Prefer: Handelsblatt depth, ifo/diw reports, coalition/industry stories RSS missed
- Max 2 items from any single publisher
"""
        return f"""
Germany publisher diversity (strict):
- At least 5 items must be news articles from newspapers: {news}
- At most 2 items from research institutes: {research}
- Max 2 items from any single publisher
- Run separate web searches per outlet (e.g. "site:zeit.de Germany", "site:tagesspiegel.de")
- Prefer coalition politics, labour, industry, healthcare NEWS over survey roundups
"""

    if section_id == "berlin":
        if light:
            return """
Berlin (RSS-heavy — gap-fill mode):
- RSS may cover limited Berlin-local feeds; search tagesspiegel.de Berlin, berliner-zeitung.de, the-berliner.com
- Local Berlin news ONLY — not generic Germany unless directly affecting Berlin
"""
        return """
Berlin publisher diversity (strict):
- Max 3 items from rbb24; at least 2 from tagesspiegel.de
- At least 1 from berliner-zeitung.de or the-berliner.com
- Run explicit searches: "site:tagesspiegel.de Berlin", "site:berliner-zeitung.de"
- Local Berlin news ONLY — not generic Germany or Brandenburg unless directly affecting Berlin
"""

    if section_id == "world":
        if light:
            return """
World (RSS-heavy — gap-fill mode):
- RSS already covers many international headlines; focus on paywalled depth (FT, Economist, Bloomberg, NYT, Nikkei)
- Ensure ≥1 item from a non-European region RSS under-covered
- Do NOT mirror Spain/Germany stories
"""
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
        if light:
            return """
Spain (RSS-heavy — gap-fill mode):
- RSS already covers elpais/eldiario/lavanguardia; focus on elconfidencial.com and paywalled depth
- Mix national and regional where RSS missed material developments
"""
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
    base_min: int,
    preferred_sources: list[str],
    search_domains: list[str],
    sources_cfg: dict,
    rss_block: str = "",
    rss_count: int = 0,
) -> str:
    name = topic.get("name", topic.get("id", ""))
    desc = (topic.get("description") or "").strip()
    priorities = ", ".join(topic.get("priority_categories") or [])
    avoid = ", ".join(topic.get("avoid_unless_material") or [])
    preferred = ", ".join(preferred_sources) or "(see allowed domains)"
    domains = "\n".join(f"- {d}" for d in search_domains[:40])

    section_id = topic.get("id", "")
    diversity = build_diversity_rules(section_id, sources_cfg, rss_count=rss_count)

    min_note = (
        f"Minimum items: {min_items} (reduced from {base_min} because RSS already covers this section)"
        if rss_count > 0 and min_items < base_min
        else f"Minimum items: {min_items}"
    )

    return f"""Gather raw research for ONE section of a personal daily briefing. Today is {date_str}.

Section: {name} (id: {section_id})
{min_note}
Description: {desc}
Priority categories: {priorities}
Avoid unless material development: {avoid or "none"}
Preferred publishers (search each outlet separately — do not rely on one domain): {preferred}
{rss_block}{diversity}
web_search allowed domains (RSS-saturated domains removed):
{domains}

Rules:
- Full article URLs only (never homepages, never truncated URLs)
- Material developments over commentary
- Include structural / underreported stories
- topic_ids MUST start with the section id ("{section_id}") as the first element, then optional theme tags
- Synthesis will trim to 3 items later — quality over quantity
- In search_notes, report item count per publisher and which RSS gaps you filled

Return JSON matching the schema with keys: items, gaps, search_notes."""


def make_client() -> Any:
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        timeout=API_TIMEOUT_SECONDS,
    )


def fetch_web_research(
    *,
    client: Any,
    model: str,
    prompt: str,
    domains: list[str],
    require_web_search: bool = True,
    max_tool_calls: int = 8,
    search_context_size: str = "medium",
) -> tuple[str, Any]:
    """Run a web_search-only Responses call. Returns research text + raw response."""
    tool: dict[str, Any] = {
        "type": "web_search",
        "search_context_size": search_context_size,
    }
    if domains:
        tool["filters"] = {"allowed_domains": domains}

    create_kwargs: dict[str, Any] = {
        "model": model,
        "tools": [tool],
        "input": prompt,
    }
    if require_web_search:
        create_kwargs["tool_choice"] = "required"
    if max_tool_calls > 0:
        create_kwargs["max_tool_calls"] = max_tool_calls

    response = client.responses.create(**create_kwargs)
    output_text = collect_output_text(response)
    if not output_text:
        raise RuntimeError("Empty response from OpenAI web research")
    return output_text, response


def fetch_structured(
    *,
    client: Any,
    model: str,
    prompt: str,
    schema: dict,
    schema_name: str,
    domains: list[str],
    enable_web_search: bool = True,
    require_web_search: bool = False,
    max_tool_calls: int | None = None,
) -> tuple[dict, Any]:
    create_kwargs: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    if enable_web_search:
        tool: dict[str, Any] = {"type": "web_search"}
        if domains:
            tool["filters"] = {"allowed_domains": domains}
        create_kwargs["tools"] = [tool]
        if require_web_search:
            create_kwargs["tool_choice"] = "required"
        if max_tool_calls is not None and max_tool_calls > 0:
            create_kwargs["max_tool_calls"] = max_tool_calls

    response = client.responses.create(**create_kwargs)

    output_text = collect_output_text(response)
    if not output_text:
        raise RuntimeError("Empty response from OpenAI")

    try:
        return extract_json(output_text), response
    except ValueError as exc:
        raise ValueError(f"{exc}\n\nRaw output:\n{output_text[:4000]}") from exc


def fetch_section(
    *,
    section_id: str,
    date_str: str,
    model: str,
    topics_cfg: dict,
    sources_cfg: dict,
    rss_ctx: SectionRssContext | None = None,
    spend_ledger: DailySpendLedger | None = None,
    cap_abort: threading.Event | None = None,
) -> tuple[str, dict]:
    topics = topic_by_id(topics_cfg)
    allowed_domains = sources_cfg.get("allowed_domains") or []

    topic = topics.get(section_id)
    if not topic or not topic.get("enabled", True):
        return section_id, {"items": [], "gaps": [], "search_notes": ""}

    ctx = rss_ctx or SectionRssContext(section_id=section_id)
    base_min = SECTION_MIN_ITEMS[section_id]
    min_items = openai_min_for_section(section_id, ctx.item_count)
    preferred = resolve_preferred_sources(section_id, sources_cfg)
    search_domains = narrow_domains_for_openai(
        allowed_domains=allowed_domains,
        preferred_sources=preferred,
        rss_domains=ctx.domains,
    )
    skipped_domains = sorted(
        d for d in allowed_domains if d in ctx.domains and d not in search_domains
    )
    rss_block = build_rss_prompt_block(
        ctx,
        base_min=base_min,
        openai_min=min_items,
        skipped_domains=skipped_domains,
    )
    prompt = build_section_prompt(
        date_str=date_str,
        topic=topic,
        min_items=min_items,
        base_min=base_min,
        preferred_sources=preferred,
        search_domains=search_domains,
        sources_cfg=sources_cfg,
        rss_block=rss_block,
        rss_count=ctx.item_count,
    )

    started = time.monotonic()
    if ctx.item_count:
        log(
            f"  [{section_id}] started (RSS {ctx.item_count} → OpenAI min {min_items}, "
            f"{len(search_domains)}/{len(allowed_domains)} domains)..."
        )
    else:
        log(f"  [{section_id}] started (min {min_items} items)...")

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
        schema_name=f"briefing_section_{section_id}",
        domains=search_domains,
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
    spend_ledger: DailySpendLedger | None = None,
) -> dict:
    topics = topic_by_id(topics_cfg)
    section_ids = [
        section_id
        for section_id in NEWS_SECTION_IDS
        if (topics.get(section_id) or {}).get("enabled", True)
    ]
    skipped_sections: list[str] = []

    all_items: list[dict] = []
    all_gaps: list[str] = []
    notes: list[str] = []
    section_counts: dict[str, int] = {}

    allowed_domains = sources_cfg.get("allowed_domains") or []
    rss_groups = group_rss_by_section(rss_items or [])
    rss_contexts = {
        sid: analyze_rss_section(sid, rss_groups.get(sid, []), allowed_domains)
        for sid in section_ids
    }
    if rss_items:
        summary = ", ".join(
            f"{sid}: {rss_contexts[sid].item_count} RSS → min {openai_min_for_section(sid, rss_contexts[sid].item_count)}"
            for sid in section_ids
        )
        log(f"  RSS-aware targets: {summary}")
        for sid in section_ids:
            count = rss_contexts[sid].item_count
            if should_skip_openai_section(sid, count, sources_cfg):
                skipped_sections.append(sid)
                log(f"  [{sid}] skipping OpenAI fetch — RSS has {count} items")

    openai_section_ids = [sid for sid in section_ids if sid not in skipped_sections]

    if spend_ledger and spend_ledger.cap_enabled():
        log(
            f"  Daily spend cap: ${spend_ledger.cap_usd:.2f} "
            f"(already spent today: ${spend_ledger.spent_usd:.4f})"
        )
        spend_ledger.assert_not_over_cap()

    cap_abort = threading.Event()
    started = time.monotonic()
    log(f"  Launching {len(openai_section_ids)} section fetches in parallel...")

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(
                fetch_section,
                section_id=section_id,
                date_str=date_str,
                model=model,
                topics_cfg=topics_cfg,
                sources_cfg=sources_cfg,
                rss_ctx=rss_contexts[section_id],
                spend_ledger=spend_ledger,
                cap_abort=cap_abort,
            ): section_id
            for section_id in openai_section_ids
        }

        for future in as_completed(futures):
            section_id = futures[future]
            try:
                section_id, result = future.result()
            except SpendCapExceeded:
                cap_abort.set()
                raise
            items = result.get("items") or []
            all_items.extend(items)
            section_counts[section_id] = len(items)
            all_gaps.extend(result.get("gaps") or [])
            if result.get("search_notes"):
                notes.append(f"{section_id}: {result['search_notes']}")

    elapsed = time.monotonic() - started
    log(f"  All OpenAI fetches finished in {elapsed:.0f}s")

    for sid in skipped_sections:
        section_counts[sid] = 0
        notes.append(f"{sid}: skipped OpenAI — RSS coverage sufficient")

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

    openai_targets = {
        sid: openai_min_for_section(sid, rss_contexts[sid].item_count) for sid in section_ids
    }
    rss_counts = {sid: rss_contexts[sid].item_count for sid in section_ids}

    return {
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "items": all_items,
        "gaps": all_gaps,
        "rss_counts": rss_counts,
        "openai_min_targets": openai_targets,
        "search_notes": (
            f"RSS counts: {rss_counts}. "
            f"OpenAI min targets: {openai_targets}. "
            f"Section counts (OpenAI): {section_counts}. "
            f"Ingestion: {ingestion}. "
            f"RSS merged: {rss_merged}. "
            f"Publisher mix: {publishers}. "
            + " ".join(notes)
        ).strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch news briefing research via OpenAI web_search")
    parser.add_argument("--type", default="news", help="Briefing type (default: news)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--model", default=None, help=f"Override model (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="Print first section prompt only; do not call API")
    parser.add_argument(
        "--no-rss-merge",
        action="store_true",
        help="Do not merge inbox/{type}/YYYY-MM-DD-rss.json even if present",
    )
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    if args.type == "news" and briefing.prefetch_merge_script:
        log(
            "News uses the RSS + WordPress pipeline "
            "(fetch_rss.py → fetch_wordpress.py → merge_news_inbox.py). "
            "fetch_openai_research.py --type news is disabled."
        )
        return 1

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    topics_cfg = load_yaml(briefing.topics_path)
    sources_cfg = load_yaml(briefing.sources_path)

    allowed_domains = sources_cfg.get("allowed_domains") or []
    inbox_dir = briefing.inbox_dir
    dry_rss = [] if args.no_rss_merge else load_rss_items(inbox_dir, date_str)
    dry_ctx = analyze_rss_section("spain", group_rss_by_section(dry_rss).get("spain", []), allowed_domains)
    dry_min = openai_min_for_section("spain", dry_ctx.item_count)
    dry_search = narrow_domains_for_openai(
        allowed_domains=allowed_domains,
        preferred_sources=resolve_preferred_sources("spain", sources_cfg),
        rss_domains=dry_ctx.domains,
    )
    dry_skipped = sorted(d for d in allowed_domains if d in dry_ctx.domains and d not in dry_search)

    if args.dry_run:
        topic = topic_by_id(topics_cfg)["spain"]
        prompt = build_section_prompt(
            date_str=date_str,
            topic=topic,
            min_items=dry_min,
            base_min=SECTION_MIN_ITEMS["spain"],
            preferred_sources=resolve_preferred_sources("spain", sources_cfg),
            search_domains=dry_search,
            sources_cfg=sources_cfg,
            rss_block=build_rss_prompt_block(
                dry_ctx,
                base_min=SECTION_MIN_ITEMS["spain"],
                openai_min=dry_min,
                skipped_domains=dry_skipped,
            ),
            rss_count=dry_ctx.item_count,
        )
        log(prompt)
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        log("OPENAI_API_KEY is not set")
        return 1

    model = resolve_model(args.model)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-raw.json"

    rss_items: list[dict] = []
    if not args.no_rss_merge:
        rss_items = load_rss_items(inbox_dir, date_str)
        if rss_items:
            log(f"  Found {len(rss_items)} RSS items for merge + prompt tuning")

    cap_usd = resolve_daily_cap()
    spend_path = inbox_dir / f"{date_str}-spend.json"
    spend_ledger = DailySpendLedger.load_or_create(spend_path, date_str=date_str, cap_usd=cap_usd)

    log(f"Fetching research for {date_str} with model {model} (build: no-reasoning-param)...")
    try:
        payload = fetch_all_research(
            date_str=date_str,
            model=model,
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
            rss_items=rss_items,
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
