#!/usr/bin/env python3
"""Verify berlin-restaurants Maps URLs appear in the synthesis inbox (post-synthesis guard)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
from datetime import datetime, timezone

from briefing_paths import load_briefing_type

MAPS_LINE_RE = re.compile(r"^\*\*Maps:\*\*\s+(https?://\S+)", re.MULTILINE)


def log(message: str) -> None:
    print(message, flush=True)


def maps_url_key(url: str) -> str:
    """Stable key for Google Maps place URLs (cid / place_id / full URL)."""
    raw = (url or "").strip()
    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)
    if "cid" in qs and qs["cid"]:
        return f"cid:{qs['cid'][0]}"
    if "q" in qs and qs["q"] and str(qs["q"][0]).startswith("place_id:"):
        return str(qs["q"][0])
    # maps/place URLs often embed place id in path
    path = parsed.path.rstrip("/")
    if "/maps/place/" in path or path.startswith("/maps/place"):
        return f"{parsed.netloc.lower()}{path}"
    return raw


def extract_maps_urls(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in MAPS_LINE_RE.finditer(text or ""):
        raw = match.group(1).strip().rstrip(".,;")
        key = maps_url_key(raw)
        if key in seen:
            continue
        seen.add(key)
        urls.append(raw)
    return urls


def collect_inbox_maps_keys(payload: dict) -> set[str]:
    keys: set[str] = set()
    for item in payload.get("items") or []:
        url = (item.get("google_maps_url") or "").strip()
        if url.startswith("http"):
            keys.add(maps_url_key(url))
    return keys


def verify_restaurant_maps(
    *,
    briefing_text: str,
    inbox_payload: dict,
) -> tuple[list[str], list[str]]:
    cited = extract_maps_urls(briefing_text)
    allowed = collect_inbox_maps_keys(inbox_payload)
    unknown = [url for url in cited if maps_url_key(url) not in allowed]
    return cited, unknown


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify restaurant Maps URLs exist in synthesis inbox"
    )
    parser.add_argument("--type", default="berlin-restaurants")
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
    except (FileNotFoundError, ValueError) as exc:
        log(str(exc))
        return 1

    briefing_text = briefing_path.read_text(encoding="utf-8")
    inbox_payload = json.loads(inbox_path.read_text(encoding="utf-8"))
    cited, unknown = verify_restaurant_maps(
        briefing_text=briefing_text,
        inbox_payload=inbox_payload,
    )

    if not cited:
        log(f"FAIL: no **Maps:** URLs found in {briefing_path.name}")
        return 1

    if unknown:
        log(
            f"FAIL: {len(unknown)} Maps URL(s) in {briefing_path.name} "
            f"not found in {inbox_path.name}:"
        )
        for url in unknown:
            log(f"  - {url}")
        log("Copy google_maps_url verbatim from the verified inbox — do not invent Maps links.")
        return 1

    log(
        f"OK: {len(cited)} Maps URL(s) in {briefing_path.name} all present in "
        f"{inbox_path.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
