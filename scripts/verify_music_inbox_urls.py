#!/usr/bin/env python3
"""HTTP-verify music-discovery raw inbox Listen / cover / Dig URLs (post-fetch, pre-slim).

OpenAI often invents bcbits cover paths. We require a live Bandcamp album page
and copy the cover from that HTML (og:image / image_src / bcbits art id).
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
DEFAULT_TIMEOUT_SECONDS = 20
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
IMAGE_SRC_RE = re.compile(
    r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
IMAGE_SRC_RE_REV = re.compile(
    r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']image_src["\']',
    re.IGNORECASE,
)
BCBITS_ART_RE = re.compile(
    r"https://f\d+\.bcbits\.com/img/a(\d+)_\d+\.(?:jpg|jpeg|png)",
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


def normalize_bcbits_cover(url: str) -> str:
    """Prefer the _10.jpg Bandcamp size used in past briefings."""
    return re.sub(r"(a\d+)_\d+\.(?:jpg|jpeg|png)$", r"\1_10.jpg", url, count=1, flags=re.I)


def extract_bandcamp_cover(html: str) -> str | None:
    """Cover URL from og:image, link rel=image_src, or any bcbits art path."""
    body = html or ""
    candidates: list[str] = []
    og = extract_og_image(body)
    if og:
        candidates.append(og)
    for pattern in (IMAGE_SRC_RE, IMAGE_SRC_RE_REV):
        match = pattern.search(body)
        if match:
            candidates.append(html_lib.unescape(match.group(1).strip()))
    for url in candidates:
        if is_http_url(url):
            return normalize_bcbits_cover(url)
    match = BCBITS_ART_RE.search(body)
    if match:
        return f"https://f4.bcbits.com/img/a{match.group(1)}_10.jpg"
    return None


def fetch_html(
    url: str,
    *,
    session: requests.Session,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int | None, str, str]:
    """GET the full URL body. Returns (status_code, body, error_note).

    Do not truncate: Bandcamp album HTML is often 200KB+, and GitHub-hosted
    runners can see a larger head before og:image than a laptop fetch.
    """
    try:
        response = session.get(
            url,
            timeout=timeout,
            headers=HEADERS,
            allow_redirects=True,
        )
        return response.status_code, response.text or "", ""
    except requests.RequestException as exc:
        return None, "", str(exc)[:160]


def check_music_url_live(
    url: str,
    *,
    session: requests.Session,
) -> tuple[bool, str]:
    """GET-only live check (skip HEAD — Bandcamp/CDN often 403 it)."""
    status, _body, err = fetch_html(url, session=session)
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
    cover = extract_bandcamp_cover(html)
    model_cover = str(item.get("cover_url") or "").strip()
    if cover:
        if model_cover and model_cover != cover:
            notes.append("cover_url: replaced from Bandcamp HTML")
        item["cover_url"] = cover
        live_fields["cover_url"] = "from_bandcamp_html"
    elif is_http_url(model_cover):
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        ok, note = check_music_url_live(model_cover, session=sess)
        if ok:
            live_fields["cover_url"] = "live"
        else:
            notes.append(f"cover_url: {note}")
            live_fields["cover_url"] = "dead"
            item["cover_url"] = ""
    else:
        has_og = "og:image" in (html or "").lower()
        has_bcbits = "bcbits.com/img" in (html or "").lower()
        notes.append(
            f"cover_url: missing (html_len={len(html or '')}, "
            f"og:image={'yes' if has_og else 'no'}, bcbits={'yes' if has_bcbits else 'no'})"
        )
        live_fields["cover_url"] = "missing"
        item["cover_url"] = ""

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

    has_cover = is_http_url(str(item.get("cover_url") or ""))
    item["url_live"] = "live" if has_cover else "dead"
    item["url_field_status"] = live_fields
    item["url_verify_notes"] = "; ".join(notes) if notes else "ok"
    item["verified"] = bool(has_cover and item.get("artist") and item.get("release"))
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
            f"(need {args.min_verified}). Each needs a live Bandcamp page and a cover image."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
