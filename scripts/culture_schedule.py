#!/usr/bin/env python3
"""Extract schedule hints from culture feed titles and descriptions."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "mai": 5,
    "june": 6,
    "jun": 6,
    "juni": 6,
    "july": 7,
    "jul": 7,
    "juli": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
    "dez": 12,
}

TIME_RE = re.compile(
    r"\b(\d{1,2})[:.h](\d{2})\s*(?:uhr)?\b",
    re.I,
)

DATE_RANGE_RE = re.compile(
    r"\b(\d{1,2})\s*[–\-—]\s*(\d{1,2})\s+"
    r"(january|february|march|märz|maerz|april|may|mai|june|juni|july|juli|august|"
    r"september|october|okt|november|december|dez|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"(?:\s+(\d{4}))?",
    re.I,
)

SINGLE_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(january|february|march|märz|maerz|april|may|mai|june|juni|july|juli|august|"
    r"september|october|okt|november|december|dez|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"(?:\s+(\d{4}))?",
    re.I,
)

ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

DE_DOT_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")

UNTIL_DATE_RE = re.compile(
    r"until\s+"
    r"(january|february|march|märz|maerz|april|may|mai|june|juni|july|juli|august|"
    r"september|october|okt|november|december|dez|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\s+(\d{1,2}),?\s+(\d{4})",
    re.I,
)

LONG_RANGE_RE = re.compile(
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"\d{1,2},?\s+\d{4})\s*[–\-—]\s*"
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"\d{1,2},?\s+\d{4})",
    re.I,
)


def _month_num(token: str) -> int | None:
    return MONTHS.get(token.lower().strip())


def _default_year(reference_year: int | None, explicit: str | None) -> int:
    if explicit and explicit.isdigit():
        return int(explicit)
    return reference_year or datetime.now().year


def extract_schedule_from_text(text: str, *, reference_year: int | None = None) -> tuple[str, str]:
    """Return (dates, times) strings — best-effort from free text."""
    blob = (text or "").strip()
    if not blob:
        return "", ""

    times: list[str] = []
    for match in TIME_RE.finditer(blob):
        hour, minute = match.group(1), match.group(2)
        times.append(f"{int(hour):02d}:{minute}")

    iso = ISO_DATE_RE.search(blob)
    if iso:
        return iso.group(1), times[0] if times else ""

    range_match = DATE_RANGE_RE.search(blob)
    if range_match:
        d1, d2, month_tok, year_tok = range_match.groups()
        month = _month_num(month_tok or "")
        year = _default_year(reference_year, year_tok)
        if month:
            month_name = datetime(year, month, 1).strftime("%B")
            return f"{d1}–{d2} {month_name} {year}", times[0] if times else ""

    single = SINGLE_DATE_RE.search(blob)
    if single:
        day, month_tok, year_tok = single.groups()
        month = _month_num(month_tok or "")
        year = _default_year(reference_year, year_tok)
        if month:
            dt = datetime(year, month, int(day))
            return dt.strftime("%d %B %Y"), times[0] if times else ""

    return "", times[0] if times else ""


def _parse_single_date_token(day: str, month_tok: str, year_tok: str | None, reference_year: int) -> date | None:
    month = _month_num(month_tok or "")
    if not month:
        return None
    year = _default_year(reference_year, year_tok)
    try:
        return date(year, month, int(day))
    except ValueError:
        return None


def _parse_month_day_year_blob(blob: str, reference_year: int) -> date | None:
    single = SINGLE_DATE_RE.search(blob)
    if single:
        return _parse_single_date_token(single.group(1), single.group(2), single.group(3), reference_year)
    de = DE_DOT_DATE_RE.search(blob)
    if de:
        day, month, year = de.groups()
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None
    iso = ISO_DATE_RE.search(blob)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            return None
    return None


def parse_culture_date_bounds(
    dates: str,
    *,
    reference_year: int | None = None,
) -> tuple[date | None, date | None]:
    """Best-effort (start, end) dates from a culture item's dates string."""
    blob = (dates or "").strip()
    if not blob:
        return None, None

    ref_year = reference_year or datetime.now().year

    until = UNTIL_DATE_RE.search(blob)
    if until:
        month_tok, day, year = until.groups()
        end = _parse_single_date_token(day, month_tok, year, int(year))
        return None, end

    long_range = LONG_RANGE_RE.search(blob)
    if long_range:
        start = _parse_month_day_year_blob(long_range.group(1), ref_year)
        end = _parse_month_day_year_blob(long_range.group(2), ref_year)
        return start, end

    range_match = DATE_RANGE_RE.search(blob)
    if range_match:
        d1, d2, month_tok, year_tok = range_match.groups()
        month = _month_num(month_tok or "")
        year = _default_year(ref_year, year_tok)
        if month:
            try:
                start = date(year, month, int(d1))
                end = date(year, month, int(d2))
                return start, end
            except ValueError:
                pass

    single = _parse_month_day_year_blob(blob, ref_year)
    if single:
        return single, single

    return None, None


def dates_overlap_briefing_window(
    start: date | None,
    end: date | None,
    week_start: date,
    week_end: date,
    *,
    section_id: str,
) -> bool:
    """True when dates fall in or span the Wednesday–Tuesday briefing window."""
    if start is None and end is None:
        return True

    if section_id == "exhibitions":
        if end is not None and end >= week_start:
            return True
        if start is not None and end is not None:
            return start <= week_end and end >= week_start
        if start is not None:
            return start <= week_end
        return False

    eff_start = start or end
    eff_end = end or start
    if eff_start is None:
        return True
    return eff_start <= week_end and eff_end >= week_start


def item_in_briefing_window(
    item: dict[str, Any],
    week_start: date,
    week_end: date,
) -> bool:
    section_id = (item.get("topic_ids") or ["exhibitions"])[0]
    start, end = parse_culture_date_bounds(
        item.get("dates") or "",
        reference_year=week_end.year,
    )
    return dates_overlap_briefing_window(
        start,
        end,
        week_start,
        week_end,
        section_id=section_id,
    )


def filter_items_to_briefing_window(
    items: list[dict[str, Any]],
    week_start: date,
    week_end: date,
    *,
    ingestion_sources: set[str] | None = None,
    require_parseable_date: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Drop items outside the briefing window; return (kept, dropped_count)."""
    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        source = (item.get("ingestion_source") or "").strip()
        if ingestion_sources is not None and source not in ingestion_sources:
            kept.append(item)
            continue
        start, end = parse_culture_date_bounds(
            item.get("dates") or "",
            reference_year=week_end.year,
        )
        if require_parseable_date and start is None and end is None:
            dropped += 1
            continue
        if item_in_briefing_window(item, week_start, week_end):
            kept.append(item)
        else:
            dropped += 1
    return kept, dropped
