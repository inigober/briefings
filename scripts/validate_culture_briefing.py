#!/usr/bin/env python3
"""Validate a Berlin culture briefing for duplicate events and thin sections."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from culture_calendar import (  # noqa: E402
    UMBRELLA_TITLE_RE,
    infer_series_id,
    normalize_event_key,
    normalize_text_key,
    normalize_venue_key,
)

SECTION_HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)
ENTRY_HEADING_RE = re.compile(r"^### (.+)$", re.MULTILINE)
VENUE_RE = re.compile(r"^\*\*Venue:\*\*\s*(.+)$", re.MULTILINE)
LINK_RE = re.compile(r"^\*\*Official Link:\*\*\s*\[[^\]]*\]\(([^)]+)\)", re.MULTILINE)

SECTION_ID_BY_HEADING = {
    "top picks": "top_picks",
    "exhibitions radar": "exhibitions",
    "film & screenings": "film",
    "performing arts": "performing_arts",
    "music": "music",
    "wildcards": "wildcards",
    "advance radar": "advance_radar",
}

# Style-rule minimums (topics.yaml max_items is an upper bound).
SECTION_MINIMUMS = {
    "exhibitions": 4,
    "film": 2,
    "performing_arts": 2,
    "music": 3,
    "wildcards": 1,
}


def normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    path = parsed.path.rstrip("/").lower()
    host = parsed.netloc.lower().removeprefix("www.")
    return f"{host}{path}"


def parse_entries(text: str) -> list[dict]:
    entries: list[dict] = []
    current_section = ""
    current_title = ""
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        if not current_title:
            return
        body = "\n".join(current_lines)
        venue_match = VENUE_RE.search(body)
        link_match = LINK_RE.search(body)
        venue = venue_match.group(1).strip() if venue_match else ""
        official_url = link_match.group(1).strip() if link_match else ""
        item = {
            "section": current_section,
            "title": current_title,
            "venue": venue,
            "official_url": official_url,
        }
        item["event_key"] = normalize_event_key(item)
        item["series_id"] = infer_series_id(item)
        entries.append(item)
        current_title = ""
        current_lines = []

    for line in text.splitlines():
        section_match = SECTION_HEADING_RE.match(line)
        if section_match:
            flush()
            heading = section_match.group(1).strip().lower()
            current_section = SECTION_ID_BY_HEADING.get(heading, heading)
            continue
        entry_match = ENTRY_HEADING_RE.match(line)
        if entry_match:
            flush()
            current_title = entry_match.group(1).strip()
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)
    flush()
    return entries


def validate_briefing(text: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    entries = parse_entries(text)
    if not entries:
        errors.append("No ### event entries found in briefing.")
        return errors, warnings

    seen_event_keys: dict[str, str] = {}
    seen_urls: dict[str, str] = {}
    seen_series: dict[str, str] = {}
    venue_counts: dict[str, int] = {}
    section_counts: dict[str, int] = {}

    for entry in entries:
        sid = entry["section"]
        section_counts[sid] = section_counts.get(sid, 0) + 1

        event_key = entry["event_key"]
        if event_key in seen_event_keys:
            errors.append(
                f"Duplicate event '{entry['title']}' @ {entry['venue']} "
                f"(also in {seen_event_keys[event_key]})."
            )
        else:
            seen_event_keys[event_key] = sid or "?"

        url = entry["official_url"]
        if url:
            norm = normalize_url(url)
            if norm in seen_urls:
                errors.append(
                    f"Duplicate official link for '{entry['title']}' "
                    f"(same URL as '{seen_urls[norm]}')."
                )
            else:
                seen_urls[norm] = entry["title"]

        series_id = entry.get("series_id") or ""
        if series_id:
            if series_id in seen_series:
                errors.append(
                    f"Festival/series '{series_id}' listed twice "
                    f"('{entry['title']}' and '{seen_series[series_id]}')."
                )
            else:
                seen_series[series_id] = entry["title"]

        venue_key = normalize_venue_key(entry["venue"])
        if venue_key:
            venue_counts[venue_key] = venue_counts.get(venue_key, 0) + 1

    for venue_key, count in sorted(venue_counts.items()):
        if count > 2:
            warnings.append(f"Venue '{venue_key}' appears {count} times (cap is 2).")

    for sid, minimum in SECTION_MINIMUMS.items():
        count = section_counts.get(sid, 0)
        if count < minimum:
            warnings.append(
                f"Section '{sid}' has {count} entries (style minimum {minimum}). "
                "Note in last_run.json; do not pad with duplicates."
            )

    top_titles = {
        normalize_text_key(e["title"])
        for e in entries
        if e["section"] == "top_picks"
    }
    for entry in entries:
        if entry["section"] == "top_picks":
            continue
        title_key = normalize_text_key(entry["title"])
        if title_key in top_titles and "**Short Context:**" in text:
            # Full duplicate block likely present if title matches top pick exactly
            errors.append(
                f"'{entry['title']}' appears in Top Picks and again in "
                f"{entry['section']} — use a one-line cross-reference only."
            )

    umbrella_titles = [e for e in entries if UMBRELLA_TITLE_RE.search(e["title"] or "")]
    if len(umbrella_titles) > 1:
        hosts = {normalize_url(e["official_url"]) for e in umbrella_titles if e["official_url"]}
        if len(hosts) < len(umbrella_titles):
            warnings.append(
                "Multiple festival-umbrella titles share URLs — consider merging into one entry."
            )

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Berlin culture briefing markdown.")
    parser.add_argument("--path", required=True, help="Path to briefing markdown file")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on warnings too")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    errors, warnings = validate_briefing(text)

    for msg in warnings:
        print(f"WARN: {msg}")
    for msg in errors:
        print(f"ERROR: {msg}", file=sys.stderr)

    if errors:
        print(f"\nValidation failed: {len(errors)} error(s), {len(warnings)} warning(s).", file=sys.stderr)
        return 1
    if warnings:
        print(f"\nValidation passed with {len(warnings)} warning(s).")
        return 1 if args.strict else 0
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
