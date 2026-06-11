#!/usr/bin/env python3
"""Build a token-light inbox slice for Cursor synthesis from the full pre-fetch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

SECTION_CAPS: dict[str, int] = {
    "spain": 12,
    "germany": 12,
    "berlin": 10,
    "world": 15,
}

SELECTED_READS_CAP = 8

SLIM_ITEM_KEYS = (
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


def log(message: str) -> None:
    print(message, flush=True)


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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
    return None


def matches_domain(host: str, allowed: set[str]) -> bool:
    return any(host == d or host.endswith(f".{d}") for d in allowed)


def score_item(item: dict) -> int:
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


def section_id(item: dict) -> str:
    tags = item.get("topic_ids") or []
    for sid in ("spain", "germany", "berlin", "world"):
        if sid in tags:
            return sid
    return tags[0] if tags else "world"


def slim_item(item: dict) -> dict:
    slim = {k: item[k] for k in SLIM_ITEM_KEYS if k in item}
    if "ingestion_source" not in slim:
        slim["ingestion_source"] = "openai"
    return slim


def pick_top(items: list[dict], cap: int) -> list[dict]:
    ranked = sorted(items, key=score_item, reverse=True)
    return [slim_item(i) for i in ranked[:cap]]


def build_synthesis_inbox(
    raw: dict,
    *,
    sources_cfg: dict,
) -> dict:
    items = raw.get("items") or []
    by_section: dict[str, list[dict]] = {sid: [] for sid in SECTION_CAPS}
    read_domains = selected_read_domains(sources_cfg)
    read_pool: list[dict] = []

    for item in items:
        sid = section_id(item)
        if sid in by_section:
            by_section[sid].append(item)
        domain = item_domain(item)
        if domain and matches_domain(domain, read_domains):
            read_pool.append(item)

    section_items: list[dict] = []
    section_counts: dict[str, int] = {}
    for sid, cap in SECTION_CAPS.items():
        picked = pick_top(by_section[sid], cap)
        section_counts[sid] = len(picked)
        section_items.extend(picked)

    selected_reads = pick_top(read_pool, SELECTED_READS_CAP)

    return {
        "date": raw.get("date"),
        "source_raw": f"inbox/{raw.get('date')}-raw.json",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Slim inbox JSON for Cursor synthesis")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    inbox_dir = REPO_ROOT / "inbox"
    raw_path = inbox_dir / f"{date_str}-raw.json"
    out_path = inbox_dir / f"{date_str}-synthesis.json"

    if not raw_path.is_file():
        log(f"Missing {raw_path} — run pre-fetch first")
        return 1

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    sources_cfg = load_yaml(REPO_ROOT / "config" / "sources.yaml")
    payload = build_synthesis_inbox(raw, sources_cfg=sources_cfg)

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = payload["section_counts"]
    log(
        f"Wrote {out_path} — {payload['raw_item_count']} raw → "
        f"{len(payload['items'])} news + {len(payload['selected_read_candidates'])} read candidates "
        f"({counts})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
