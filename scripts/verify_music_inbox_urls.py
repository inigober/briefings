#!/usr/bin/env python3
"""HTTP-verify music-discovery raw inbox Listen / cover / Dig URLs (post-fetch, pre-slim).

OpenAI often invents bcbits cover paths. We require a live Bandcamp album URL
(HTTP < 400) and a real cover image.

GitHub-hosted runners often get a tiny Bandcamp challenge page (~3KB, HTTP 200)
instead of the real ~250KB album HTML, so og:image is missing even when the
Listen URL works in a browser. That is an IP/bot-wall issue, not a
synthesis parsing issue. Cover fallback order (still Bandcamp art when possible):

1. Bandcamp HTML (og:image / image_src / bcbits art id) when the page is real
2. Microlink metadata for the same Bandcamp URL (their fetchers are not on
   GitHub's IP ranges; returns the Bandcamp bcbits cover)
3. MusicBrainz + Cover Art Archive, title-matched, last resort

YouTube Listen URLs are optional. OpenAI rarely copies a live
`music.youtube.com/playlist?list=OLAK5uy_…` album playlist, so this script
looks that playlist up via YouTube Music search (no API key). Missing YouTube
does not fail verification — synthesis copies `youtube_url` when present and
omits YouTube when it is null.
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
BOT_WALL_MAX_HTML = 20_000
MUSICBRAINZ_MIN_INTERVAL_SECONDS = 1.1

# Browser-like UA — Bandcamp/GitHub runners often 403 the BriefingBot UA on bursts.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,*/*;q=0.8",
}
API_HEADERS = {
    "User-Agent": "BriefingsPrefetch/1.0 (https://github.com/inigober/briefings)",
    "Accept": "application/json",
}

MICROLINK_URL = "https://api.microlink.io"
YTM_SEARCH_URL = "https://music.youtube.com/youtubei/v1/search"
MUSICBRAINZ_RELEASE_URL = "https://musicbrainz.org/ws/2/release/"
COVERART_RELEASE_URL = "https://coverartarchive.org/release/{mbid}/front-500"
COVERART_RELEASE_GROUP_URL = "https://coverartarchive.org/release-group/{mbid}/front-500"

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
TITLE_NOISE_RE = re.compile(r"\b(the|a|an|and|ep|lp|album)\b", re.IGNORECASE)
LUCENE_SPECIAL_RE = re.compile(r'[+\-&|!(){}\[\]^"~*?:\\/]')


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


def looks_like_bot_wall(html: str) -> bool:
    """True when the body is a tiny challenge page, not a Bandcamp album."""
    body = html or ""
    if extract_bandcamp_cover(body):
        return False
    if len(body) >= BOT_WALL_MAX_HTML:
        return False
    lowered = body.lower()
    if "og:image" in lowered or "bcbits.com/img" in lowered:
        return False
    return True


def normalize_music_name(value: str) -> str:
    text = html_lib.unescape(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = TITLE_NOISE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_various_artist(name: str) -> bool:
    raw = re.sub(r"[^\w\s/]", " ", (name or "").lower())
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw in {"various", "various artists", "va", "v a", "v/a"}


def names_match(left: str, right: str, *, min_ratio: float = 0.6) -> bool:
    a = normalize_music_name(left)
    b = normalize_music_name(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= min_ratio


def release_titles_match(query: str, candidate: str) -> bool:
    """Require a real title match, including catalog numbers like Part 2 vs Part 1."""
    q = normalize_music_name(query)
    c = normalize_music_name(candidate)
    if not q or not c:
        return False
    q_nums = re.findall(r"\d+", q)
    c_nums = re.findall(r"\d+", c)
    if q_nums and set(q_nums) != set(c_nums) and not set(q_nums).issubset(set(c_nums)):
        return False
    if q == c or q in c or c in q:
        return True
    tq, tc = set(q.split()), set(c.split())
    if not tq or not tc:
        return False
    return len(tq & tc) / min(len(tq), len(tc)) >= 0.8


def lucene_quote(value: str) -> str:
    cleaned = LUCENE_SPECIAL_RE.sub(" ", value or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_microlink_image(payload: object) -> str | None:
    """Return the Bandcamp (or other) image URL from a Microlink JSON body."""
    if not isinstance(payload, dict):
        return None
    if str(payload.get("status") or "").lower() not in ("", "success"):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    image = data.get("image")
    url = ""
    if isinstance(image, str):
        url = image.strip()
    elif isinstance(image, dict):
        url = str(image.get("url") or "").strip()
    if not is_http_url(url):
        return None
    if "bcbits.com" in url.lower():
        return normalize_bcbits_cover(url)
    return url


def mb_artist_name(release_row: dict) -> str:
    credits = release_row.get("artist-credit") or []
    parts: list[str] = []
    for credit in credits:
        if isinstance(credit, str):
            parts.append(credit)
            continue
        if not isinstance(credit, dict):
            continue
        name = credit.get("name") or ""
        if not name:
            name = str((credit.get("artist") or {}).get("name") or "")
        joinphrase = str(credit.get("joinphrase") or "")
        parts.append(f"{name}{joinphrase}")
    return "".join(parts).strip()


def pick_musicbrainz_release(results: list[dict], artist: str, release: str) -> dict | None:
    various = is_various_artist(artist)
    for row in results or []:
        title = str(row.get("title") or "")
        row_artist = mb_artist_name(row)
        if not release_titles_match(release, title):
            continue
        if various:
            if row_artist and not (
                is_various_artist(row_artist) or names_match(artist, row_artist)
            ):
                continue
        elif not names_match(artist, row_artist):
            continue
        return row
    return None


def fetch_html(
    url: str,
    *,
    session: requests.Session,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int | None, str, str]:
    """GET the full URL body. Returns (status_code, body, error_note).

    Do not truncate: Bandcamp album HTML is often 200KB+ when the real page
    is returned. GitHub runners often get a ~3KB challenge page instead.
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


def fetch_json(
    url: str,
    *,
    session: requests.Session,
    params: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int | None, object | None, str]:
    try:
        response = session.get(
            url,
            params=params,
            timeout=timeout,
            headers=API_HEADERS,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            return response.status_code, None, f"HTTP {response.status_code}"
        try:
            return response.status_code, response.json(), ""
        except ValueError:
            return response.status_code, None, "invalid json"
    except requests.RequestException as exc:
        return None, None, str(exc)[:160]


def follow_image_url(
    url: str,
    *,
    session: requests.Session,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bool, str, str]:
    """GET an image URL, follow redirects, return (ok, final_url, note)."""
    try:
        response = session.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": API_HEADERS["User-Agent"],
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            },
            allow_redirects=True,
            stream=True,
        )
        status = response.status_code
        final = (response.url or url).strip()
        response.close()
        if status is not None and status < 400 and is_http_url(final):
            return True, final, ""
        return False, "", f"HTTP {status}"
    except requests.RequestException as exc:
        return False, "", str(exc)[:160]


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


def lookup_microlink_cover(
    bandcamp_url: str,
    *,
    session: requests.Session,
    sleep_ms: int = DEFAULT_SLEEP_MS,
) -> str | None:
    """Ask Microlink to read the Bandcamp page from a non-GitHub IP."""
    if not is_http_url(bandcamp_url):
        return None
    if sleep_ms > 0:
        time.sleep(sleep_ms / 1000.0)
    status, payload, err = fetch_json(
        MICROLINK_URL,
        session=session,
        params={"url": bandcamp_url, "meta": "true"},
        timeout=30,
    )
    if status == 429:
        log("    Microlink rate-limited (free tier is 25 requests/day per IP)")
        return None
    if err or not isinstance(payload, dict):
        log(f"    Microlink failed for {bandcamp_url}: {err or 'bad payload'}")
        return None
    artwork = extract_microlink_image(payload)
    if not artwork:
        return None
    ok, final, note = follow_image_url(artwork, session=session)
    if ok:
        return final
    log(f"    Microlink image dead for {bandcamp_url}: {note}")
    return None


def lookup_coverartarchive_cover(
    artist: str,
    release: str,
    *,
    session: requests.Session,
    sleep_ms: int = DEFAULT_SLEEP_MS,
) -> str | None:
    if not artist or not release:
        return None
    wait = max(MUSICBRAINZ_MIN_INTERVAL_SECONDS, (sleep_ms or 0) / 1000.0)
    time.sleep(wait)
    query = f'release:"{lucene_quote(release)}" AND artist:"{lucene_quote(artist)}"'
    status, payload, err = fetch_json(
        MUSICBRAINZ_RELEASE_URL,
        session=session,
        params={"query": query, "fmt": "json", "limit": 5},
    )
    if status == 503:
        time.sleep(wait)
        status, payload, err = fetch_json(
            MUSICBRAINZ_RELEASE_URL,
            session=session,
            params={"query": query, "fmt": "json", "limit": 5},
        )
    if err or not isinstance(payload, dict):
        log(f"    MusicBrainz search failed for {artist} — {release}: {err or 'bad payload'}")
        return None
    row = pick_musicbrainz_release(payload.get("releases") or [], artist, release)
    if not row:
        return None
    mbid = str(row.get("id") or "").strip()
    rgid = str((row.get("release-group") or {}).get("id") or "").strip()
    candidates = []
    if mbid:
        candidates.append(COVERART_RELEASE_URL.format(mbid=mbid))
    if rgid:
        candidates.append(COVERART_RELEASE_GROUP_URL.format(mbid=rgid))
    for url in candidates:
        ok, final, _note = follow_image_url(url, session=session)
        if ok:
            return final
    return None


def simplify_release_title(value: str) -> str:
    """Drop catalogue junk like (HM024) and [BALEARIC, ELECTRONIC] for matching."""
    text = re.sub(r"\[[^\]]*\]", " ", value or "")
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_youtube_listen_url(url: str | None) -> bool:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in {"youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}:
        return False
    path = parsed.path.lower()
    if path.startswith("/results") or "search_query" in (parsed.query or ""):
        return False
    return True


def _walk_dicts(obj: object):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_dicts(value)


def _runs_text(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    runs = node.get("runs")
    if isinstance(runs, list):
        return "".join(str(part.get("text") or "") for part in runs if isinstance(part, dict))
    return str(node.get("content") or node.get("text") or "")


def _first_official_playlist_id(obj: object) -> str | None:
    for node in _walk_dicts(obj):
        pid = node.get("playlistId")
        if isinstance(pid, str) and pid.startswith("OLAK5uy_"):
            return pid
    return None


def ytm_album_hits(payload: object) -> list[dict]:
    """Album/playlist hits from a YouTube Music search JSON body."""
    hits: list[dict] = []
    seen: set[str] = set()
    if not isinstance(payload, dict):
        return hits
    for node in _walk_dicts(payload):
        card = node.get("musicCardShelfRenderer")
        if isinstance(card, dict):
            title = _runs_text(card.get("title") or {})
            subtitle = _runs_text(card.get("subtitle") or {})
            pid = _first_official_playlist_id(card)
            if pid and title and pid not in seen:
                seen.add(pid)
                hits.append({"title": title, "subtitle": subtitle, "playlist_id": pid})
            continue
        row = node.get("musicResponsiveListItemRenderer")
        if not isinstance(row, dict):
            continue
        texts: list[str] = []
        for col in row.get("flexColumns") or []:
            if not isinstance(col, dict):
                continue
            texts.append(
                _runs_text(
                    (col.get("musicResponsiveListItemFlexColumnRenderer") or {}).get("text")
                    or {}
                )
            )
        title = texts[0] if texts else ""
        subtitle = " ".join(t for t in texts[1:] if t)
        pid = _first_official_playlist_id(row)
        if pid and title and pid not in seen:
            seen.add(pid)
            hits.append({"title": title, "subtitle": subtitle, "playlist_id": pid})
    return hits


def pick_youtube_music_playlist(hits: list[dict], artist: str, release: str) -> str | None:
    """Return a music.youtube.com album playlist URL when title + artist match."""
    release_simple = simplify_release_title(release)
    various = is_various_artist(artist)
    for hit in hits or []:
        title = str(hit.get("title") or "")
        subtitle = str(hit.get("subtitle") or "")
        pid = str(hit.get("playlist_id") or "")
        if not pid.startswith("OLAK5uy_"):
            continue
        title_ok = release_titles_match(release, title) or (
            release_simple and release_titles_match(release_simple, title)
        )
        if not title_ok:
            continue
        blob = f"{title} {subtitle}"
        artist_ok = (
            names_match(artist, subtitle)
            or names_match(artist, blob)
            or names_match(artist, title)
        )
        looks_like_label = bool(
            re.search(r"\b(recordings?|records|music|label)\b", artist or "", re.I)
        )
        if various or artist_ok or looks_like_label:
            return f"https://music.youtube.com/playlist?list={pid}"
    return None


def youtube_search_queries(artist: str, release: str) -> list[str]:
    """Shorter queries match YouTube Music albums better than catalogue-padded titles."""
    simple = simplify_release_title(release) or (release or "")
    simple = simple.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    simple = re.sub(r"\b(double album|full album)\b", " ", simple, flags=re.I)
    simple = re.sub(r"\s+", " ", simple).strip()
    artist_q = re.sub(r"\s+", " ", (artist or "").replace("&", " ")).strip()
    queries: list[str] = []
    if is_various_artist(artist_q):
        queries.append(simple)
    else:
        queries.append(f"{artist_q} {simple}".strip())
        words = simple.split()
        if len(words) > 5:
            queries.append(f"{artist_q} {' '.join(words[:5])}".strip())
        queries.append(simple)
    presents = re.match(r"^(.+?)\s+presents\s+(.+)$", simple, flags=re.I)
    if presents:
        who, rest = presents.group(1).strip(), presents.group(2).strip()
        queries.append(f"{who} {rest}".strip())
        queries.append(rest)
    seen: set[str] = set()
    out: list[str] = []
    for query in queries:
        if query and query.lower() not in seen:
            seen.add(query.lower())
            out.append(query)
    return out


def lookup_youtube_music_album(
    artist: str,
    release: str,
    *,
    session: requests.Session,
    sleep_ms: int = DEFAULT_SLEEP_MS,
) -> str | None:
    """Find an official YouTube Music album playlist (OLAK5uy_…) for artist + release."""
    if not artist or not release:
        return None
    headers = {
        "User-Agent": BROWSER_UA,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Referer": "https://music.youtube.com/",
        "Origin": "https://music.youtube.com",
    }
    client = {
        "clientName": "WEB_REMIX",
        "clientVersion": "1.20240124.01.00",
        "hl": "en",
        "gl": "US",
    }
    for query in youtube_search_queries(artist, release):
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        try:
            response = session.post(
                YTM_SEARCH_URL,
                params={"prettyPrint": "false"},
                json={"context": {"client": client}, "query": query},
                timeout=DEFAULT_TIMEOUT_SECONDS,
                headers=headers,
            )
        except requests.RequestException as exc:
            log(f"    YouTube Music search failed for {artist} — {release}: {str(exc)[:160]}")
            continue
        status = getattr(response, "status_code", None)
        if not isinstance(status, int) or status >= 400:
            continue
        try:
            payload = response.json()
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        found = pick_youtube_music_playlist(ytm_album_hits(payload), artist, release)
        if found:
            return found
    return None


def resolve_cover_url(
    item: dict,
    html: str,
    *,
    session: requests.Session,
    sleep_ms: int = DEFAULT_SLEEP_MS,
) -> tuple[str, str, list[str]]:
    """Return (cover_url, cover_status, notes)."""
    notes: list[str] = []
    html_len = len(html or "")
    bot_wall = looks_like_bot_wall(html)
    if bot_wall:
        notes.append(f"bandcamp_html: bot wall (html_len={html_len})")

    cover = extract_bandcamp_cover(html)
    if cover:
        model_cover = str(item.get("cover_url") or "").strip()
        if model_cover and model_cover != cover:
            notes.append("cover_url: replaced from Bandcamp HTML")
        return cover, "from_bandcamp_html", notes

    artist = str(item.get("artist") or "").strip()
    release = str(item.get("release") or "").strip()
    bandcamp = str(item.get("bandcamp_url") or "").strip()
    microlink = lookup_microlink_cover(bandcamp, session=session, sleep_ms=sleep_ms)
    if microlink:
        notes.append("cover_url: Bandcamp og:image via Microlink")
        return microlink, "from_microlink", notes

    caa = lookup_coverartarchive_cover(artist, release, session=session, sleep_ms=sleep_ms)
    if caa:
        notes.append("cover_url: from Cover Art Archive")
        return caa, "from_coverartarchive", notes

    model_cover = str(item.get("cover_url") or "").strip()
    if is_http_url(model_cover) and "bcbits.com" not in model_cover.lower():
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        ok, note = check_music_url_live(model_cover, session=session)
        if ok:
            notes.append("cover_url: kept model URL")
            return model_cover, "live", notes
        notes.append(f"cover_url: {note}")

    has_og = "og:image" in (html or "").lower()
    has_bcbits = "bcbits.com/img" in (html or "").lower()
    notes.append(
        f"cover_url: missing (html_len={html_len}, "
        f"og:image={'yes' if has_og else 'no'}, bcbits={'yes' if has_bcbits else 'no'})"
    )
    return "", "missing", notes


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
    cover, cover_status, cover_notes = resolve_cover_url(
        item, html, session=sess, sleep_ms=sleep_ms
    )
    notes.extend(cover_notes)
    item["cover_url"] = cover
    live_fields["cover_url"] = cover_status

    for field in OPTIONAL_FIELDS:
        raw = item.get(field)
        if field == "youtube_url":
            continue
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

    youtube = str(item.get("youtube_url") or "").strip()
    if youtube.lower() in ("", "null"):
        youtube = ""
    kept_youtube = False
    if youtube and is_youtube_listen_url(youtube):
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        ok, note = check_music_url_live(youtube, session=sess)
        if ok:
            live_fields["youtube_url"] = "live"
            item["youtube_url"] = youtube
            kept_youtube = True
        else:
            notes.append(f"youtube_url: {note}, cleared")
    elif youtube:
        notes.append("youtube_url: invalid or search URL, cleared")
    if not kept_youtube:
        found = lookup_youtube_music_album(
            str(item.get("artist") or ""),
            str(item.get("release") or ""),
            session=sess,
            sleep_ms=sleep_ms,
        )
        if found:
            item["youtube_url"] = found
            live_fields["youtube_url"] = "from_youtube_music"
            notes.append("youtube_url: from YouTube Music search")
        else:
            item["youtube_url"] = None

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
