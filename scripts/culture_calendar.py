#!/usr/bin/env python3
"""Shared Berlin culture calendar helpers: warehouse classification, programme URLs, novelty index."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent

EVENT_PATH_KEYWORDS = (
    "event",
    "exhibition",
    "exhibitions",
    "stueck",
    "festival",
    "film-screening",
    "programm",
    "program",
    "programme",
    "fair",
    "konzert",
    "concert",
    "ticket",
    "spielplan",
    "timetable",
    "vorfuehrung",
    "screening",
)

VAGUE_SCHEDULE_MARKERS = (
    "tba",
    "various",
    "check website",
    "see website",
    "uhrzeit folgt",
    "time tbd",
)

SECTIONS_REQUIRING_WEB_SEARCH = frozenset(
    {"film", "music", "performing_arts", "exhibitions"}
)

INDEX_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s+\|\s+([^|]+)\s+\|\s+([^|]+)\s+\|\s+([^|]+)\s+\|\s+(\S+)\s*$"
)


def host_domain(url: str) -> str:
    host = urlparse((url or "").strip()).netloc.lower().removeprefix("www.")
    return host


def press_publishers(sources_cfg: dict) -> set[str]:
    return {str(p).strip() for p in (sources_cfg.get("press_publishers") or []) if p}


def press_domains(sources_cfg: dict) -> set[str]:
    return {d.lower().removeprefix("www.") for d in (sources_cfg.get("press_domains") or []) if d}


def venue_programme_publishers(sources_cfg: dict) -> set[str]:
    """RSS/ICS feeds flagged as venue programme (not editorial press)."""
    publishers: set[str] = set()
    for feed in (sources_cfg.get("rss_feeds") or []):
        if not feed.get("programme"):
            continue
        for key in ("publisher", "venue"):
            value = (feed.get(key) or "").strip()
            if value:
                publishers.add(value)
    for feed in (sources_cfg.get("ics_feeds") or []):
        for key in ("publisher", "venue"):
            value = (feed.get(key) or "").strip()
            if value:
                publishers.add(value)
    return publishers


def programme_domains(sources_cfg: dict) -> set[str]:
    domains: set[str] = set()
    for entries in (sources_cfg.get("programme_urls") or {}).values():
        for entry in entries or []:
            url = entry.get("url") or ""
            if url.startswith("http"):
                domains.add(host_domain(url))
    for domain in sources_cfg.get("allowed_domains") or []:
        if domain:
            domains.add(domain.lower().removeprefix("www."))
    return domains


def is_press_item(item: dict, sources_cfg: dict) -> bool:
    source = item.get("ingestion_source")
    if source not in ("rss", "wordpress"):
        return False
    venue = (item.get("venue") or "").strip()
    if venue and venue in press_publishers(sources_cfg):
        return True
    url_host = host_domain(item.get("official_url") or "")
    if url_host and url_host in press_domains(sources_cfg):
        return True
    return False


def is_deep_event_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower().rstrip("/")
    if not path:
        return False
    segments = [s for s in path.split("/") if s]
    if not segments or segments in (["en"], ["de"]):
        return False
    if len(segments) == 1 and segments[0] in ("en", "de"):
        return False
    if any(kw in path for kw in EVENT_PATH_KEYWORDS):
        return True
    if len(segments) >= 3:
        return True
    if len(segments) >= 2 and any(ch.isdigit() for ch in segments[-1]):
        return True
    # Single-segment editorial slugs (e.g. ceecee.cc/long-article-title/).
    if len(segments) == 1 and len(segments[0]) >= 24 and "-" in segments[0]:
        return True
    return False


def has_concrete_schedule(dates: str, times: str, *, section_id: str) -> bool:
    d = (dates or "").strip().lower()
    t = (times or "").strip().lower()
    if not d or any(m in d for m in VAGUE_SCHEDULE_MARKERS):
        return False
    if section_id == "exhibitions":
        return True
    if not t or any(m in t for m in VAGUE_SCHEDULE_MARKERS):
        return False
    return True


def is_programme_warehouse_item(item: dict, sources_cfg: dict) -> bool:
    """True when a feed item signals real venue programme coverage (not editorial press)."""
    if item.get("programme_feed"):
        return True
    if item.get("ingestion_source") in ("ics", "wordpress_events", "index_berlin_ics", "index_berlin_html", "silent_green_html"):
        return True
    if is_press_item(item, sources_cfg):
        return False
    section_id = (item.get("topic_ids") or ["exhibitions"])[0]
    url_host = host_domain(item.get("official_url") or "")
    if url_host and url_host in programme_domains(sources_cfg):
        if is_deep_event_url(item.get("official_url") or "") or has_concrete_schedule(
            item.get("dates") or "",
            item.get("times") or "",
            section_id=section_id,
        ):
            return True
        # Venue-domain RSS (e.g. Ballhaus feed) counts even without parsed dates.
        if item.get("ingestion_source") == "rss":
            return True
    venue = (item.get("venue") or "").strip()
    if venue in venue_programme_publishers(sources_cfg) and item.get("ingestion_source") == "rss":
        return True
    if has_concrete_schedule(
        item.get("dates") or "",
        item.get("times") or "",
        section_id=section_id,
    ):
        return True
    return False


def programme_counts(calendar_items: list[dict], sources_cfg: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in calendar_items:
        if not is_programme_warehouse_item(item, sources_cfg):
            continue
        sid = (item.get("topic_ids") or ["exhibitions"])[0]
        counts[sid] = counts.get(sid, 0) + 1
    return counts


def press_counts(calendar_items: list[dict], sources_cfg: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in calendar_items:
        if not is_press_item(item, sources_cfg):
            continue
        sid = (item.get("topic_ids") or ["exhibitions"])[0]
        counts[sid] = counts.get(sid, 0) + 1
    return counts


def culture_openai_min(section_id: str, programme_count: int, base_min: int) -> int:
    floor = 2 if section_id != "advance_radar" else 1
    if section_id == "advance_radar":
        floor = 1
    if programme_count == 0:
        return base_min
    if programme_count >= 6:
        return floor
    if programme_count >= 3:
        return max(floor, (base_min + floor) // 2)
    reduction = min(programme_count, base_min - floor)
    return max(floor, base_min - reduction)


def build_programme_urls_block(sources_cfg: dict, *, sections_needing_search: set[str]) -> str:
    programme_urls = sources_cfg.get("programme_urls") or {}
    if not programme_urls:
        return ""

    lines = ["## Venue programme pages (web_search required for sections below)"]
    if sections_needing_search:
        lines.append(
            "- **MUST use web_search** on programme URLs for: "
            + ", ".join(sorted(sections_needing_search))
            + ". Do not invent event URLs."
        )
    else:
        lines.append("- Use web_search on these pages when filling section gaps.")

    for section_id, entries in programme_urls.items():
        if not entries:
            continue
        label = section_id.replace("_", " ")
        lines.append(f"\n### {label}")
        for entry in entries:
            venue = entry.get("venue") or "Venue"
            url = entry.get("url") or ""
            note = entry.get("note") or ""
            suffix = f" — {note}" if note else ""
            lines.append(f"- {venue}: {url}{suffix}")
    return "\n".join(lines) + "\n\n"


def parse_events_index(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        match = INDEX_LINE_RE.match(line)
        if not match:
            continue
        rows.append(
            {
                "date": match.group(1),
                "section": match.group(2).strip(),
                "title": match.group(3).strip(),
                "venue": match.group(4).strip(),
                "official_url": match.group(5).strip(),
            }
        )
    return rows


def load_recent_index_entries(
    *,
    state_dir: Path,
    run_date: str,
    max_age_weeks: int = 8,
    max_per_section: int = 12,
) -> list[dict[str, str]]:
    index_path = state_dir / "events_index.md"
    rows = parse_events_index(index_path)
    if not rows:
        return []

    try:
        run_dt = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return rows[-max_per_section * 6 :]

    cutoff = run_dt - timedelta(weeks=max_age_weeks)
    recent = []
    for row in rows:
        try:
            row_dt = datetime.strptime(row["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if row_dt >= cutoff:
            recent.append(row)
    return recent


def build_novelty_block(
    *,
    state_dir: Path,
    run_date: str,
    topics_cfg: dict,
) -> str:
    entries = load_recent_index_entries(state_dir=state_dir, run_date=run_date)
    if not entries:
        return ""

    by_section: dict[str, list[dict[str, str]]] = {}
    for row in entries:
        section = row["section"]
        by_section.setdefault(section, []).append(row)

    lines = [
        "## Already recommended (prioritize novelty)",
        "These appeared in recent briefings (`state/berlin-culture/events_index.md`).",
        "- **Do not re-add** unless materially new: opening week, new programme/discussion, "
        "closing within 10 days, or date change.",
        "- **Exhibitions** often run for months — deprioritize indexed shows; "
        "search programme pages for **new openings** and **closing-soon** instead.",
        "- **Film / performance / music** are weekly — search programme pages for "
        "dated events in the event window not listed below.",
    ]

    section_order = [
        t.get("id")
        for t in topics_cfg.get("topics") or []
        if t.get("id") and t.get("id") != "top_picks"
    ]
    seen_sections = set(section_order) | set(by_section)
    for section in section_order + sorted(seen_sections - set(section_order)):
        rows = by_section.get(section) or []
        if not rows:
            continue
        samples = rows[-8:]
        bullets = [
            f"{r['title']} @ {r['venue']}"
            for r in samples
        ]
        lines.append(f"- {section}: " + "; ".join(bullets))

    return "\n".join(lines) + "\n\n"


def build_press_warehouse_block(
    *,
    calendar_items: list[dict],
    sources_cfg: dict,
) -> str:
    press_items = [i for i in calendar_items if is_press_item(i, sources_cfg)]
    if not press_items:
        return ""

    lines = [
        "## Editorial leads (press — context only, not programme coverage)",
        f"- {len(press_items)} magazine/review items ingested (Berlin Art Link, The Berliner, Cee Cee, etc.).",
        "- These **do not** reduce venue search minimums. Use for context only.",
        "- Do not copy review URLs as event `official_url` — find the venue programme page.",
    ]
    samples = [((i.get("title") or "").strip(), (i.get("venue") or "").strip()) for i in press_items[:6]]
    if samples:
        lines.append("- Samples: " + "; ".join(f"{t} ({v})" for t, v in samples if t))
    return "\n".join(lines) + "\n\n"


def build_programme_warehouse_block(
    *,
    calendar_items: list[dict],
    sources_cfg: dict,
    topics_cfg: dict,
) -> str:
    programme_items = [i for i in calendar_items if is_programme_warehouse_item(i, sources_cfg)]
    if not programme_items:
        return ""

    section_ids = [
        t["id"]
        for t in topics_cfg.get("topics") or []
        if t.get("enabled", True) and t.get("id") not in ("top_picks",)
    ]
    counts = {sid: 0 for sid in section_ids}
    samples: dict[str, list[str]] = {sid: [] for sid in section_ids}

    for item in programme_items:
        sid = (item.get("topic_ids") or ["exhibitions"])[0]
        if sid not in counts:
            continue
        counts[sid] += 1
        title = (item.get("title") or "").strip()
        if title and len(samples[sid]) < 3:
            samples[sid].append(title)

    lines = [
        "## Venue programme warehouse (already collected)",
        f"- {len(programme_items)} venue-programme items with real schedule signals.",
        "- Reduced OpenAI minimums apply only where counts below are > 0.",
        "- Still web_search programme URLs for **new** dated events not listed here.",
    ]
    for sid in section_ids:
        if counts[sid] == 0:
            continue
        sample_text = "; ".join(samples[sid])
        lines.append(
            f"- {sid}: {counts[sid]} programme items"
            + (f" (e.g. {sample_text})" if sample_text else "")
        )
    return "\n".join(lines) + "\n\n"


def mark_item_verified(item: dict, *, require_url_live: bool = True) -> None:
    section_id = (item.get("topic_ids") or ["exhibitions"])[0]
    url_ok = is_deep_event_url(item.get("official_url") or "")
    schedule_ok = has_concrete_schedule(
        item.get("dates") or "",
        item.get("times") or "",
        section_id=section_id,
    )
    url_live = item.get("url_live")
    if require_url_live and item.get("ingestion_source") == "openai":
        live_ok = url_live is True
    else:
        live_ok = url_live is not False

    item["verified"] = bool(url_ok and schedule_ok and live_ok)


def is_publisher_venue_item(item: dict, sources_cfg: dict) -> bool:
    venue = (item.get("venue") or "").strip()
    if venue in press_publishers(sources_cfg):
        return True
    url_host = host_domain(item.get("official_url") or "")
    return bool(url_host and url_host in press_domains(sources_cfg))


# --- Deduplication keys (series / venue / event) ---

_SERIES_SLUG_RE = re.compile(r"[^a-z0-9]+")

FESTIVAL_URL_HOSTS: dict[str, str] = {
    "polishartweek.com": "polish-art-week",
}

FESTIVAL_TITLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"polish\s+art\s+week", re.I), "polish-art-week"),
    (re.compile(r"avant\s+art\s+festival", re.I), "polish-art-week"),
    (re.compile(r"kyiv\s+biennial", re.I), "kyiv-biennial"),
    (re.compile(r"projekt\s*raum", re.I), "projekt-raum"),
    (re.compile(r"open\s+studios?", re.I), "open-studios"),
)

UMBRELLA_TITLE_RE = re.compile(
    r"\b(art\s+week|festival|biennial|open\s+studios?)\b",
    re.I,
)


def normalize_text_key(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"[^\w\s-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_venue_key(venue: str) -> str:
    raw = (venue or "").strip()
    if "," in raw:
        parts = [normalize_text_key(p) for p in raw.split(",") if p.strip()]
        if parts:
            # "Hochzeitssaal, Sophiensæle" → parent institution
            return parts[-1]
    v = normalize_text_key(raw)
    for sep in (" — ", " - "):
        if sep in v:
            v = v.split(sep, 1)[0].strip()
    return v


def normalize_event_key(item: dict) -> str:
    title = normalize_text_key(item.get("title") or "")
    venue = normalize_venue_key(item.get("venue") or "")
    return f"{title}|{venue}"


def slugify_series_id(text: str) -> str:
    slug = _SERIES_SLUG_RE.sub("-", normalize_text_key(text)).strip("-")
    return slug[:80]


def infer_series_id(item: dict) -> str:
    explicit = (item.get("series_id") or "").strip()
    if explicit:
        return slugify_series_id(explicit)

    url = (item.get("official_url") or "").strip().lower()
    for host, series in FESTIVAL_URL_HOSTS.items():
        if host in url:
            return series

    title = item.get("title") or ""
    for pattern, series in FESTIVAL_TITLE_PATTERNS:
        if pattern.search(title):
            return series

    event_kind = (item.get("event_kind") or "").strip().lower()
    if event_kind == "festival_overview" or UMBRELLA_TITLE_RE.search(title):
        return slugify_series_id(title)

    return ""


def infer_event_kind(item: dict) -> str:
    kind = (item.get("event_kind") or "").strip().lower()
    if kind in ("single", "festival_overview", "festival_event"):
        return kind

    title = item.get("title") or ""
    if UMBRELLA_TITLE_RE.search(title) and "&" in title:
        return "festival_overview"
    series = infer_series_id(item)
    if series and not UMBRELLA_TITLE_RE.search(title):
        return "festival_event"
    if series:
        return "festival_overview"
    return "single"


def enrich_culture_metadata(item: dict) -> dict:
    """Attach series_id and event_kind for slim-inbox diversification."""
    item["series_id"] = infer_series_id(item)
    item["event_kind"] = infer_event_kind(item)
    return item
