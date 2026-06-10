#!/usr/bin/env python3
"""Pre-fetch daily research via OpenAI Responses API + web_search."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_topics_summary(topics_cfg: dict) -> str:
    lines: list[str] = []
    for topic in topics_cfg.get("topics", []):
        if not topic.get("enabled", True):
            continue
        name = topic.get("name", topic.get("id", "unknown"))
        desc = (topic.get("description") or "").strip()
        max_items = topic.get("max_items")
        lines.append(f"- **{name}** ({topic.get('id')}, target {max_items}): {desc}")

        priorities = topic.get("priority_categories") or topic.get("keywords") or []
        if priorities:
            lines.append(f"  Priorities: {', '.join(priorities)}")

        avoid = topic.get("avoid_unless_material") or []
        if avoid:
            lines.append(f"  Avoid unless material: {', '.join(avoid)}")

        if topic.get("min_non_european_regions"):
            lines.append(
                f"  World rule: ≥{topic['min_non_european_regions']} non-European regions; "
                f"prefer {', '.join(topic.get('prefer_countries') or [])}"
            )
    return "\n".join(lines) or "- (no topics configured)"


def render_research_prompt(template: str, date_str: str, topics_summary: str, domains: list[str]) -> str:
    domain_block = "\n".join(f"- {d}" for d in domains) or "- (none configured)"
    return (
        template.replace("{date}", date_str)
        .replace("{topics_summary}", topics_summary)
        .replace("{allowed_domains}", domain_block)
    )


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


def fetch_research(prompt: str, model: str, domains: list[str]) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    tools: list[dict] = [{"type": "web_search"}]
    if domains:
        tools[0]["filters"] = {"allowed_domains": domains}

    response = client.responses.create(
        model=model,
        tools=tools,
        input=prompt,
    )

    output_text = getattr(response, "output_text", None)
    if not output_text:
        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "output_text":
                    parts.append(content.text)
        output_text = "\n".join(parts)

    if not output_text:
        raise RuntimeError("Empty response from OpenAI")

    return extract_json(output_text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch daily briefing research via OpenAI web_search")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--model", default=os.environ.get("OPENAI_RESEARCH_MODEL", "gpt-4.1"))
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only; do not call API")
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    topics_cfg = load_yaml(REPO_ROOT / "config" / "topics.yaml")
    sources_cfg = load_yaml(REPO_ROOT / "config" / "sources.yaml")
    template = (REPO_ROOT / "prompts" / "research_brief.md").read_text(encoding="utf-8")

    topics_summary = build_topics_summary(topics_cfg)
    domains = sources_cfg.get("allowed_domains") or []

    prompt = render_research_prompt(template, date_str, topics_summary, domains)

    if args.dry_run:
        print(prompt)
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        return 1

    inbox_dir = REPO_ROOT / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-raw.json"

    print(f"Fetching research for {date_str} with model {args.model}...")
    payload = fetch_research(prompt, args.model, domains)
    payload.setdefault("date", date_str)
    payload.setdefault("fetched_at", datetime.now(timezone.utc).isoformat())

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
