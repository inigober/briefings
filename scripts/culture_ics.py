#!/usr/bin/env python3
"""Minimal ICS/ICAL parsing for Berlin culture venue calendars."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

VEVENT_BLOCK_RE = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL | re.I)
FIELD_RE = re.compile(r"^([A-Z0-9-]+)(?:;[^:]*)?:(.*)$", re.MULTILINE)


def unfold_ics(text: str) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line.rstrip("\r"))
    return "\n".join(lines)


def parse_ics_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in FIELD_RE.finditer(block):
        key = match.group(1).upper().split(";")[0]
        value = match.group(2).strip()
        fields[key] = value
    return fields


def parse_ics_datetime(raw: str) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1]
    if "T" in value and len(value) >= 15:
        try:
            core = value.split("T", 1)
            date_part = core[0]
            time_part = core[1].split("+")[0].split("-")[0]
            if len(date_part) == 8 and date_part.isdigit():
                dt = datetime.strptime(f"{date_part}T{time_part[:6]}", "%Y%m%dT%H%M%S")
                return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
        try:
            if "+" in value[9:] or "-" in value[9:]:
                return datetime.fromisoformat(value).astimezone(timezone.utc)
        except ValueError:
            pass
    if len(value) >= 8 and value[:8].isdigit():
        try:
            dt = datetime.strptime(value[:8], "%Y%m%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def format_ics_date(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.strftime("%d %B %Y")


def format_ics_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.hour == 0 and dt.minute == 0:
        return ""
    return dt.strftime("%H:%M")


def is_ics_calendar(text: str) -> bool:
    return "BEGIN:VCALENDAR" in (text or "").upper()


def parse_ics_events(text: str) -> list[dict[str, Any]]:
    unfolded = unfold_ics(text)
    if not is_ics_calendar(unfolded):
        return []

    events: list[dict[str, Any]] = []
    for block_match in VEVENT_BLOCK_RE.finditer(unfolded):
        fields = parse_ics_fields(block_match.group(1))
        summary = fields.get("SUMMARY", "").strip()
        if not summary:
            continue
        start = parse_ics_datetime(fields.get("DTSTART", ""))
        end = parse_ics_datetime(fields.get("DTEND", ""))
        location = fields.get("LOCATION", "").strip()
        url = fields.get("URL", "").strip()
        description = fields.get("DESCRIPTION", "").strip()
        uid = fields.get("UID", "").strip()

        if start and end and start.date() != end.date():
            dates = f"{format_ics_date(start)} – {format_ics_date(end)}"
        else:
            dates = format_ics_date(start)

        events.append(
            {
                "title": summary,
                "venue": location,
                "dates": dates,
                "times": format_ics_time(start),
                "official_url": url,
                "description": description,
                "uid": uid,
                "dtstart": start.isoformat() if start else "",
            }
        )
    return events


def ics_event_url(event: dict[str, Any], fallback_url: str) -> str:
    url = (event.get("official_url") or "").strip()
    if url.startswith("http"):
        return url
    uid = event.get("uid") or ""
    if uid.startswith("http"):
        return uid
    return fallback_url
