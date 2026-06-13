#!/usr/bin/env python3
"""HTTP verification and URL sanity checks for news pre-fetch source links."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

import requests

from culture_url_verify import USER_AGENT, check_url_live

DEFAULT_SLEEP_MS = 80

# Obvious placeholder paths produced by model hallucination (e.g. Tagesspiegel …12345678.html).
_PLACEHOLDER_PATH = re.compile(
    r"(?:^|/)(?:\d{6,}|\d{4,}(?:\d)\.html)(?:$|[?#])|/12345\d+\.html$",
    re.IGNORECASE,
)

# FT article IDs are UUIDs; slug-only paths are almost always invented.
_FT_CONTENT_SLUG = re.compile(
    r"^/content/(?!([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}))[^/]+$",
    re.IGNORECASE,
)


def url_looks_suspicious(url: str) -> str | None:
    """Return a short reason if the URL pattern looks fabricated."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return "invalid scheme"
    if not parsed.netloc:
        return "missing host"

    path = parsed.path or ""
    if _PLACEHOLDER_PATH.search(path):
        return "placeholder path segment"

    host = parsed.netloc.lower().removeprefix("www.")
    if host == "ft.com" and _FT_CONTENT_SLUG.match(path):
        return "ft.com slug without article UUID"

    # Homepage or section root — not an article.
    if path in ("", "/") or path.count("/") <= 1 and path.endswith("/"):
        return "homepage or section root"

    return None


def classify_http_status(status_code: int) -> str:
    if status_code < 400:
        return "live"
    if status_code in (401, 403):
        return "paywalled"
    return "dead"


def probe_url(url: str, *, session: requests.Session | None = None) -> tuple[str, str]:
    """Return (url_live, note) where url_live is live | paywalled | dead."""
    suspicion = url_looks_suspicious(url)
    if suspicion:
        return "dead", f"suspicious URL: {suspicion}"

    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}
    try:
        response = sess.head(url, timeout=12, headers=headers, allow_redirects=True)
        if response.status_code >= 400 or response.status_code == 0:
            response = sess.get(
                url,
                timeout=12,
                headers=headers,
                allow_redirects=True,
                stream=True,
            )
            next(response.iter_content(chunk_size=256), None)
        state = classify_http_status(response.status_code)
        if state == "live":
            return "live", ""
        if state == "paywalled":
            return "paywalled", f"HTTP {response.status_code} (paywall or bot block)"
        return "dead", f"HTTP {response.status_code}"
    except requests.RequestException as exc:
        return "dead", str(exc)[:120]


def mark_news_item_verified(item: dict) -> None:
    """Set verified:true when at least one source URL is live or paywalled."""
    states = [src.get("url_live") for src in item.get("sources") or []]
    item["verified"] = any(s in ("live", "paywalled") for s in states)


def verify_news_item(
    item: dict,
    *,
    session: requests.Session,
    sleep_ms: int = DEFAULT_SLEEP_MS,
    only_openai: bool = False,
) -> dict[str, Any]:
    source = item.get("ingestion_source") or "openai"
    if only_openai and source != "openai":
        # RSS URLs come from the feed itself — treat as live unless already flagged.
        for src in item.get("sources") or []:
            if "url_live" not in src:
                src["url_live"] = "live"
                src["url_verify_notes"] = "rss feed origin"
        item["url_live"] = "live"
        item["verified"] = True
        return {"checked": False, "url_live": "live"}

    worst = "live"
    notes: list[str] = []
    for src in item.get("sources") or []:
        url = (src.get("url") or "").strip()
        if not url.startswith("http"):
            src["url_live"] = "dead"
            src["url_verify_notes"] = "missing or invalid url"
            worst = "dead"
            notes.append("missing url")
            continue

        state, note = probe_url(url, session=session)
        src["url_live"] = state
        src["url_verify_notes"] = note or ("ok" if state == "live" else state)
        if state == "dead":
            worst = "dead"
        elif state == "paywalled" and worst == "live":
            worst = "paywalled"
        if note:
            notes.append(note)

    item["url_live"] = worst
    item["url_verify_notes"] = "; ".join(n for n in notes if n) or ("ok" if worst == "live" else worst)
    mark_news_item_verified(item)

    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    return {"checked": True, "url_live": worst}


def verify_news_items(
    items: list[dict],
    *,
    sleep_ms: int = DEFAULT_SLEEP_MS,
    only_openai: bool = False,
) -> dict[str, int]:
    stats = {
        "checked": 0,
        "live": 0,
        "paywalled": 0,
        "dead": 0,
        "suspicious": 0,
        "verified_after": 0,
        "skipped": 0,
    }
    session = requests.Session()
    for item in items:
        source = item.get("ingestion_source") or "openai"
        if only_openai and source != "openai":
            for src in item.get("sources") or []:
                src["url_live"] = src.get("url_live") or "live"
            item["url_live"] = "live"
            item["verified"] = True
            stats["skipped"] += 1
            continue

        result = verify_news_item(
            item,
            session=session,
            sleep_ms=sleep_ms,
            only_openai=only_openai,
        )
        if not result.get("checked"):
            stats["skipped"] += 1
            continue

        stats["checked"] += 1
        state = result.get("url_live") or item.get("url_live")
        if state == "live":
            stats["live"] += 1
        elif state == "paywalled":
            stats["paywalled"] += 1
        else:
            stats["dead"] += 1
        if (item.get("url_verify_notes") or "").startswith("suspicious"):
            stats["suspicious"] += 1
        if item.get("verified"):
            stats["verified_after"] += 1

    return stats
