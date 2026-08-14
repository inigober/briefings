#!/usr/bin/env python3
"""HTTP-verify music-discovery raw inbox Listen / cover / Dig URLs (post-fetch, pre-slim).

OpenAI often invents bcbits cover paths. We only require a live Bandcamp album page,
then copy ``og:image`` from that HTML for the cover.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import html as html_lib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from briefing_paths import load_briefing_type
from fetch_openai_research import log
from music_dates import normalize_friday_run_date

MIN_VERIFIED_CANDIDATES = 10
DEFAULT_SLEEP_MS = 200
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_BODY_MAX_BYTES = 80_000
OPTIONAL_FIELDS = ("youtube_url", "writeup_url", "dig_url")

# Browser-like UA — Bandcamp/GitHub runners often 403 the BriefingBot UA on bursts.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,*/*;q=0.8",
}

OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
OG_IMAGE_RE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']',
    re.IGNORECASE,
)


def is_http_url(value: str | None) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_og_image(html: str) -> str | None:
    """Return og:image URL from HTML, or None."""
    for pattern in (OG_IMAGE_RE, OG_IMAGE_RE_REV):
        match = pattern.search(html or "")
        if not match:
            continue
        url = html_lib.unescape(match.group(1).strip())
        if is_http_url(url):
            return url
    return None


def fetch_html(
    url: str,
    *,
    session: requests.Session,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_BODY_MAX_BYTES,
) -> tuple[int | None, str, str]:
    """GET a URL. Returns (status_code, body, error_note)."""
    try:
        response = session.get(
            url,
            timeout=timeout,
            headers=HEADERS,
            allow_redirects=True,
            stream=True,
        )
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=4096):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_bytes:
                break
        body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
        return response.status_code, body, ""
    except requests.RequestException as exc:
        return None, "", str(exc)[:160]


def check_music_url_live(
    url: str,
    *,
    session: requests.Session,
) -> tuple[bool, str]:
    """GET-only live check (skip HEAD — Bandcamp/CDN often 403 it)."""
    status, _body, err = fetch_html(url, session=session, max_bytes=2048)
    if err:
        return False, err
    if status is None:
        return False, "unreachable"
    if status < 400:
        return True, ""
    return False, f"HTTP {status}"


def verify_music_item(
    item: dict,
    *,
    session: requests.Session | None = None,
    sleep_ms: int = DEFAULT_SLEEP_MS,
) -> dict:
    sess = session or requests.Session()
    notes: list[str] = []
    live_fields: dict[str, str] = {}

    bandcamp = str(item.get("bandcamp_url") or "").strip()
    if not is_http_url(bandcamp):
        notes.append("bandcamp_url: missing or invalid")
        live_fields["bandcamp_url"] = "dead"
        item["url_live"] = "dead"
        item["url_field_status"] = live_fields
        item["url_verify_notes"] = "; ".join(notes)
        item["verified"] = False
        return item

    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    status, html, err = fetch_html(bandcamp, session=sess)
    if err or status is None or status >= 400:
        note = err or f"HTTP {status}"
        notes.append(f"bandcamp_url: {note}")
        live_fields["bandcamp_url"] = "dead"
        item["url_live"] = "dead"
        item["url_field_status"] = live_fields
        item["url_verify_notes"] = "; ".join(notes)
        item["verified"] = False
        return item

    live_fields["bandcamp_url"] = "live"
    og_cover = extract_og_image(html)
    model_cover = str(item.get("cover_url") or "").strip()
    if og_cover:
        if model_cover and model_cover != og_cover:
            notes.append("cover_url: replaced with Bandcamp og:image")
        item["cover_url"] = og_cover
        live_fields["cover_url"] = "from_og_image"
    elif is_http_url(model_cover):
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        ok, note = check_music_url_live(model_cover, session=sess)
        if ok:
            live_fields["cover_url"] = "live"
        else:
            notes.append(f"cover_url: {note} (kept Bandcamp page anyway)")
            live_fields["cover_url"] = "dead"
    else:
        notes.append("cover_url: missing (no og:image on Bandcamp page)")
        live_fields["cover_url"] = "missing"

    for field in OPTIONAL_FIELDS:
        raw = item.get(field)
        if raw is None or str(raw).strip() in ("", "null"):
            item[field] = None if field != "dig_url" else ""
            continue
        url = str(raw).strip()
        if not is_http_url(url):
            notes.append(f"{field}: invalid URL, cleared")
            item[field] = None if field != "dig_url" else ""
            continue
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        ok, note = check_music_url_live(url, session=sess)
        if ok:
            live_fields[field] = "live"
        else:
            live_fields[field] = "dead"
            notes.append(f"{field}: {note}, cleared")
            item[field] = None if field != "dig_url" else ""

    item["url_live"] = "live"
    item["url_field_status"] = live_fields
    item["url_verify_notes"] = "; ".join(notes) if notes else "ok"
    item["verified"] = bool(item.get("artist") and item.get("release"))
    return item


def verify_music_items(
    items: list[dict],
    *,
    sleep_ms: int = DEFAULT_SLEEP_MS,
) -> dict[str, int]:
    session = requests.Session()
    checked = live = dead = 0
    for item in items:
        verify_music_item(item, session=session, sleep_ms=sleep_ms)
        checked += 1
        if item.get("verified"):
            live += 1
        else:
            dead += 1
            artist = item.get("artist") or "?"
            release = item.get("release") or "?"
            log(f"  unverified: {artist} — {release}")
            log(f"    {item.get('bandcamp_url')}")
            log(f"    {item.get('url_verify_notes')}")
    return {
        "checked": checked,
        "live": live,
        "dead": dead,
        "verified_after": live,
        "skipped": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HTTP-verify music-discovery raw inbox Bandcamp/cover/Dig URLs"
    )
    parser.add_argument("--type", default="music-discovery")
    parser.add_argument("--date", help="YYYY-MM-DD Friday run date (default: today UTC)")
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=DEFAULT_SLEEP_MS,
        help="Delay between HTTP checks (default: 200ms)",
    )
    parser.add_argument(
        "--min-verified",
        type=int,
        default=MIN_VERIFIED_CANDIDATES,
        help="Fail if fewer verified candidates remain (default: 10)",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    original = date_str
    date_str, _ = normalize_friday_run_date(date_str)
    if date_str != original:
        log(f"  Note: {original} is not a Friday — using week key {date_str}")

    briefing = load_briefing_type(args.type)
    raw_path = briefing.inbox_dir / f"{date_str}-raw.json"
    if not raw_path.is_file():
        log(f"Missing {raw_path} — run fetch_music_research.py first")
        return 1

    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    if not items:
        log("No items to verify")
        return 1

    log(f"HTTP-checking Bandcamp pages for {len(items)} music items...")
    stats = verify_music_items(items, sleep_ms=args.sleep_ms)
    payload["items"] = items
    payload["url_verified_at"] = datetime.now(timezone.utc).isoformat()
    payload["url_verify_stats"] = stats
    payload["verified_count"] = stats["verified_after"]
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    log(
        f"  URL verify: checked={stats['checked']} live={stats['live']} "
        f"dead={stats['dead']} verified_after={stats['verified_after']}"
    )
    if stats["verified_after"] < args.min_verified:
        log(
            f"FAIL: only {stats['verified_after']} verified music candidates "
            f"(need {args.min_verified}). Bandcamp pages must return HTTP < 400."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
