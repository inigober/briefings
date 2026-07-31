#!/usr/bin/env python3
"""HTTP verification helpers for culture pre-fetch official_url fields."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import requests

from culture_calendar import is_deep_event_url, mark_item_verified
from culture_schedule import (
    extract_event_years_from_text,
    extract_schedule_from_text,
    html_to_plain_text,
    is_archive_page_year,
)

DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_SLEEP_MS = 80
DEFAULT_BODY_MAX_BYTES = 120_000
USER_AGENT = "Mozilla/5.0 (compatible; BriefingBot/1.0)"


def check_url_live(url: str, *, session: requests.Session | None = None) -> tuple[bool, str]:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return False, "invalid scheme"

    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}
    try:
        response = sess.head(url, timeout=DEFAULT_TIMEOUT_SECONDS, headers=headers, allow_redirects=True)
        if response.status_code >= 400 or response.status_code == 0:
            response = sess.get(
                url,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                headers=headers,
                allow_redirects=True,
                stream=True,
            )
            next(response.iter_content(chunk_size=256), None)
        if response.status_code >= 400:
            return False, f"HTTP {response.status_code}"
        return True, ""
    except requests.RequestException as exc:
        return False, str(exc)[:120]


def fetch_page_text(
    url: str,
    *,
    session: requests.Session | None = None,
    max_bytes: int = DEFAULT_BODY_MAX_BYTES,
) -> tuple[str, str]:
    """GET page body and return (plain_text, error_note). Empty text on failure."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return "", "invalid scheme"

    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}
    try:
        response = sess.get(
            url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers=headers,
            allow_redirects=True,
            stream=True,
        )
        if response.status_code >= 400:
            return "", f"HTTP {response.status_code}"
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=4096):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_bytes:
                break
        raw = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        try:
            html = raw.decode(encoding, errors="replace")
        except LookupError:
            html = raw.decode("utf-8", errors="replace")
        return html_to_plain_text(html), ""
    except requests.RequestException as exc:
        return "", str(exc)[:120]


def apply_page_year_check(
    item: dict,
    plain_text: str,
    *,
    briefing_year: int,
) -> dict[str, Any]:
    """
    Reject archive pages whose event years are all before briefing_year.
    When the page has current-or-later years, prefer schedule strings parsed from the page.
    """
    years = extract_event_years_from_text(plain_text)
    item["page_event_years"] = sorted(years)
    if is_archive_page_year(years, briefing_year):
        item["url_live"] = False
        item["url_verify_notes"] = f"archive page year={max(years)}"
        return {"archive": True, "years": years}

    if years:
        ref_year = max(years)
        dates, times = extract_schedule_from_text(plain_text, reference_year=ref_year)
        if dates:
            item["dates"] = dates
        if times and (
            not (item.get("times") or "").strip()
            or "not visible" in (item.get("times") or "").lower()
            or "tba" in (item.get("times") or "").lower()
        ):
            item["times"] = times
    return {"archive": False, "years": years}


def verify_culture_item(
    item: dict,
    *,
    session: requests.Session,
    sleep_ms: int = DEFAULT_SLEEP_MS,
    only_openai: bool = True,
    briefing_year: int | None = None,
) -> dict[str, Any]:
    source = item.get("ingestion_source") or "openai"
    if only_openai and source != "openai":
        return {"checked": False, "url_live": item.get("url_live")}

    url = (item.get("official_url") or "").strip()
    if not url.startswith("http"):
        item["url_live"] = False
        item["url_verify_notes"] = "missing or invalid official_url"
        mark_item_verified(item, require_url_live=True)
        return {"checked": True, "url_live": False}

    http_ok, note = check_url_live(url, session=session)
    deep_ok = is_deep_event_url(url)
    archive = False
    if http_ok and not deep_ok:
        item["url_live"] = False
        item["url_verify_notes"] = "reachable but shallow URL (homepage/listing)"
    elif http_ok and briefing_year is not None:
        plain, body_note = fetch_page_text(url, session=session)
        if plain:
            year_result = apply_page_year_check(item, plain, briefing_year=briefing_year)
            archive = bool(year_result.get("archive"))
            if not archive:
                item["url_live"] = True
                item["url_verify_notes"] = note or "ok"
        else:
            # Body unreadable — keep live status; do not invent a year pass/fail.
            item["url_live"] = True
            item["url_verify_notes"] = note or (
                f"ok (page body unread: {body_note})" if body_note else "ok"
            )
    else:
        item["url_live"] = http_ok
        item["url_verify_notes"] = note or ("ok" if http_ok else "unreachable")
    mark_item_verified(item, require_url_live=True)

    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    return {
        "checked": True,
        "url_live": item["url_live"],
        "shallow": http_ok and not deep_ok,
        "archive": archive,
    }


def verify_culture_items(
    items: list[dict],
    *,
    sleep_ms: int = DEFAULT_SLEEP_MS,
    only_openai: bool = True,
    briefing_year: int | None = None,
) -> dict[str, int]:
    stats = {
        "checked": 0,
        "live": 0,
        "dead": 0,
        "shallow": 0,
        "archive": 0,
        "verified_after": 0,
        "skipped": 0,
    }
    session = requests.Session()
    for item in items:
        source = item.get("ingestion_source") or "openai"
        if only_openai and source != "openai":
            stats["skipped"] += 1
            continue
        result = verify_culture_item(
            item,
            session=session,
            sleep_ms=sleep_ms,
            only_openai=only_openai,
            briefing_year=briefing_year,
        )
        if not result.get("checked"):
            stats["skipped"] += 1
            continue
        stats["checked"] += 1
        if result.get("shallow"):
            stats["shallow"] += 1
            stats["dead"] += 1
        elif result.get("archive"):
            stats["archive"] += 1
            stats["dead"] += 1
        elif result.get("url_live"):
            stats["live"] += 1
        else:
            stats["dead"] += 1
        if item.get("verified"):
            stats["verified_after"] += 1
    return stats
