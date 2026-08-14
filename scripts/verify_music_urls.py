#!/usr/bin/env python3
"""HTTP-verify Listen / Dig / cover URLs in a music-discovery briefing (post-synthesis guard)."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from briefing_paths import load_briefing_type
from culture_url_verify import check_url_live

REPO_ROOT = Path(__file__).resolve().parent.parent

# Markdown links and images: [text](url) / ![alt](url)
MARKDOWN_URL_RE = re.compile(r"!?\[[^\]]*\]\((https?://[^)\s]+)\)")
# HTML href / src used for Listen favicon anchors and occasional raw tags
HTML_URL_RE = re.compile(
    r"""(?:href|src)=["'](https?://[^"']+)["']""",
    re.IGNORECASE,
)

# Decorative only — not content links the reader needs
SKIP_URL_SUBSTRINGS = (
    "google.com/s2/favicons",
    "gstatic.com/favicon",
)

FEATURED_HEADING_RE = re.compile(r"^## (?!More listening).+", re.MULTILINE)
MORE_LISTENING_RE = re.compile(r"^## More listening\s*$", re.MULTILINE | re.IGNORECASE)
MORE_LISTENING_BULLET_RE = re.compile(r"^- ", re.MULTILINE)
GAP_PHRASES = (
    "no featured picks",
    "records the gap rather than inventing",
    "candidate shortlist",
    "taste-cache bridge",
    "this run records the gap",
)
MIN_FEATURED = 6
MIN_MORE_LISTENING = 4


def log(message: str) -> None:
    print(message, flush=True)


def should_skip_url(url: str) -> bool:
    lowered = url.lower()
    return any(fragment in lowered for fragment in SKIP_URL_SUBSTRINGS)


def assert_music_briefing_structure(text: str) -> list[str]:
    """Return human-readable errors if the briefing is a gap note or too thin."""
    body = text or ""
    errors: list[str] = []
    lowered = body.lower()
    for phrase in GAP_PHRASES:
        if phrase in lowered:
            errors.append(f"placeholder/gap briefing (matched {phrase!r})")

    featured = FEATURED_HEADING_RE.findall(body)
    if len(featured) < MIN_FEATURED:
        errors.append(
            f"need {MIN_FEATURED} featured ## headings, found {len(featured)}"
        )

    more = MORE_LISTENING_RE.search(body)
    if not more:
        errors.append("missing ## More listening section")
    else:
        tail = body[more.end() :]
        next_h2 = re.search(r"^## ", tail, re.MULTILINE)
        section = tail[: next_h2.start()] if next_h2 else tail
        bullets = MORE_LISTENING_BULLET_RE.findall(section)
        if len(bullets) < MIN_MORE_LISTENING:
            errors.append(
                f"need {MIN_MORE_LISTENING} More listening bullets, found {len(bullets)}"
            )
    return errors


def extract_music_briefing_urls(text: str) -> list[str]:
    """Return unique http(s) content URLs from a music briefing (document order)."""
    body = text or ""
    hits: list[tuple[int, str]] = []
    for pattern in (MARKDOWN_URL_RE, HTML_URL_RE):
        for match in pattern.finditer(body):
            raw = match.group(1).strip().rstrip(".,;]")
            if not raw.startswith("http"):
                continue
            if should_skip_url(raw):
                continue
            parsed = urlparse(raw)
            if parsed.scheme not in ("http", "https"):
                continue
            hits.append((match.start(), raw))

    hits.sort(key=lambda item: item[0])
    urls: list[str] = []
    seen: set[str] = set()
    for _, raw in hits:
        key = raw.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        urls.append(raw)
    return urls


def verify_music_briefing_urls(
    urls: list[str],
    *,
    session: requests.Session | None = None,
    sleep_ms: int = 80,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (live_urls, dead_urls_with_notes)."""
    sess = session or requests.Session()
    live: list[str] = []
    dead: list[tuple[str, str]] = []

    for index, url in enumerate(urls):
        if index and sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        ok, note = check_url_live(url, session=sess)
        if ok:
            live.append(url)
        else:
            dead.append((url, note or "unreachable"))

    return live, dead


def resolve_briefing_path(
    *,
    briefing_type: str,
    briefing_path: Path | None,
    date_str: str | None,
) -> Path:
    briefing = load_briefing_type(briefing_type)
    if briefing_path:
        resolved = briefing_path
    else:
        resolved_date = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resolved = briefing.briefing_path(resolved_date)
    if not resolved.is_file():
        raise FileNotFoundError(f"Briefing not found: {resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HTTP-verify music-discovery briefing Listen/Dig/cover URLs"
    )
    parser.add_argument(
        "--type",
        default="music-discovery",
        help="Briefing type (default: music-discovery)",
    )
    parser.add_argument("--date", help="YYYY-MM-DD briefing date")
    parser.add_argument("--briefing", type=Path, help="Path to briefing markdown")
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=80,
        help="Delay between HTTP checks (default: 80ms)",
    )
    args = parser.parse_args()

    try:
        briefing_path = resolve_briefing_path(
            briefing_type=args.type,
            briefing_path=args.briefing,
            date_str=args.date,
        )
    except FileNotFoundError as exc:
        log(str(exc))
        return 1
    except ValueError as exc:
        log(str(exc))
        return 1

    text = briefing_path.read_text(encoding="utf-8")
    structure_errors = assert_music_briefing_structure(text)
    if structure_errors:
        log(f"FAIL: {briefing_path.name} is not a complete music briefing:")
        for err in structure_errors:
            log(f"  - {err}")
        return 1

    urls = extract_music_briefing_urls(text)
    if not urls:
        log(f"FAIL: No content URLs found in {briefing_path.name}")
        return 1

    log(f"HTTP-checking {len(urls)} URL(s) in {briefing_path}...")
    live, dead = verify_music_briefing_urls(urls, sleep_ms=args.sleep_ms)

    if dead:
        log(f"FAIL: {len(dead)} unreachable URL(s) in {briefing_path.name}:")
        for url, note in dead:
            log(f"  - {url} ({note})")
        log(
            "Fix invented/guessed Bandcamp slugs (or omit the link). "
            "Do not commit until all Listen/Dig/cover URLs are live."
        )
        return 1

    log(f"OK: {len(live)} URL(s) in {briefing_path.name} are reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
