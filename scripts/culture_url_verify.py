#!/usr/bin/env python3
"""HTTP verification helpers for culture pre-fetch official_url fields."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import requests

from culture_calendar import is_deep_event_url, mark_item_verified

DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_SLEEP_MS = 80
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


def verify_culture_item(
    item: dict,
    *,
    session: requests.Session,
    sleep_ms: int = DEFAULT_SLEEP_MS,
    only_openai: bool = True,
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

    live, note = check_url_live(url, session=session)
    item["url_live"] = live
    item["url_verify_notes"] = note or ("ok" if live else "unreachable")
    if live and not is_deep_event_url(url):
        item["url_verify_notes"] = "reachable but shallow URL (homepage/listing)"
    mark_item_verified(item, require_url_live=True)

    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    return {"checked": True, "url_live": live}


def verify_culture_items(
    items: list[dict],
    *,
    sleep_ms: int = DEFAULT_SLEEP_MS,
    only_openai: bool = True,
) -> dict[str, int]:
    stats = {"checked": 0, "live": 0, "dead": 0, "verified_after": 0, "skipped": 0}
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
        )
        if not result.get("checked"):
            stats["skipped"] += 1
            continue
        stats["checked"] += 1
        if result.get("url_live"):
            stats["live"] += 1
        else:
            stats["dead"] += 1
        if item.get("verified"):
            stats["verified_after"] += 1
    return stats
