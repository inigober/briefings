#!/usr/bin/env python3
"""Verify briefing citation URLs appear in the synthesis inbox (post-synthesis guard)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
from datetime import datetime, timezone

from briefing_paths import load_briefing_type
from fetch_openai_research import normalize_url

REPO_ROOT = Path(__file__).resolve().parent.parent

FOOTNOTE_URL_RE = re.compile(r'^\[\d+\]:\s+(\S+)', re.MULTILINE)
MARKDOWN_LINK_RE = re.compile(r'\[[^\]]*\]\((https?://[^)\s]+)\)')


def log(message: str) -> None:
    print(message, flush=True)


def extract_briefing_urls(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for match in FOOTNOTE_URL_RE.finditer(text):
        raw = match.group(1).strip().strip('"').strip("'")
        if raw.startswith("http"):
            norm = normalize_url(raw)
            if norm not in seen:
                seen.add(norm)
                urls.append(raw)

    for match in MARKDOWN_LINK_RE.finditer(text):
        raw = match.group(1).strip()
        norm = normalize_url(raw)
        if norm not in seen:
            seen.add(norm)
            urls.append(raw)

    return urls


def item_source_urls(item: dict) -> list[str]:
    urls: list[str] = []
    for src in item.get("sources") or []:
        url = (src.get("url") or "").strip()
        if url.startswith("http"):
            urls.append(url)
    official = (item.get("official_url") or "").strip()
    if official.startswith("http"):
        urls.append(official)
    for url in item.get("source_urls") or []:
        if isinstance(url, str) and url.startswith("http"):
            urls.append(url)
    maps_url = (item.get("google_maps_url") or "").strip()
    if maps_url.startswith("http"):
        urls.append(maps_url)
    return urls


def collect_inbox_urls(payload: dict) -> set[str]:
    allowed: set[str] = set()
    pools: list[dict] = list(payload.get("items") or [])
    pools.extend(payload.get("selected_read_candidates") or [])

    for item in pools:
        for url in item_source_urls(item):
            allowed.add(normalize_url(url))
    return allowed


def load_inbox_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_paths(
    *,
    briefing_type: str,
    briefing_path: Path | None,
    inbox_path: Path | None,
    date_str: str | None,
) -> tuple[Path, Path]:
    briefing = load_briefing_type(briefing_type)
    resolved_date = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    resolved_briefing = briefing_path or briefing.briefing_path(resolved_date)
    if not resolved_briefing.is_file():
        raise FileNotFoundError(f"Briefing not found: {resolved_briefing}")

    if inbox_path:
        resolved_inbox = inbox_path
    else:
        resolved_inbox = briefing.inbox_path(resolved_date, "synthesis")
        if not resolved_inbox.is_file():
            resolved_inbox = briefing.inbox_path(resolved_date, "raw")
    if not resolved_inbox.is_file():
        raise FileNotFoundError(f"Inbox not found for {resolved_date}")

    return resolved_briefing, resolved_inbox


def verify_briefing_sources(
    *,
    briefing_text: str,
    inbox_payload: dict,
) -> tuple[list[str], list[str]]:
    cited = extract_briefing_urls(briefing_text)
    allowed = collect_inbox_urls(inbox_payload)
    unknown = [url for url in cited if normalize_url(url) not in allowed]
    return cited, unknown


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify briefing URLs are present in synthesis inbox (no invented links)"
    )
    parser.add_argument("--type", default="news", help="Briefing type (default: news)")
    parser.add_argument("--date", help="YYYY-MM-DD briefing/inbox date")
    parser.add_argument("--briefing", type=Path, help="Path to briefing markdown")
    parser.add_argument("--inbox", type=Path, help="Path to synthesis or raw inbox JSON")
    args = parser.parse_args()

    try:
        briefing_path, inbox_path = resolve_paths(
            briefing_type=args.type,
            briefing_path=args.briefing,
            inbox_path=args.inbox,
            date_str=args.date,
        )
    except FileNotFoundError as exc:
        log(str(exc))
        return 1

    briefing_text = briefing_path.read_text(encoding="utf-8")
    inbox_payload = load_inbox_payload(inbox_path)
    cited, unknown = verify_briefing_sources(
        briefing_text=briefing_text,
        inbox_payload=inbox_payload,
    )

    if not cited:
        log(f"No URLs found in {briefing_path.name} — nothing to verify")
        return 0

    if unknown:
        log(f"FAIL: {len(unknown)} URL(s) in briefing not found in {inbox_path.name}:")
        for url in unknown:
            log(f"  - {url}")
        log("Fix footnotes / Selected Reads to copy URLs verbatim from the inbox.")
        return 1

    log(
        f"OK: {len(cited)} URL(s) in {briefing_path.name} all present in "
        f"{inbox_path.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
