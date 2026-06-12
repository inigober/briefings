#!/usr/bin/env python3
"""Helpers for briefing schedule cron expressions (POSIX 5-field, UTC)."""

from __future__ import annotations

from datetime import datetime

CRON_DOW_TO_WEEKDAY = {
    0: 6,  # Sunday
    1: 0,  # Monday
    2: 1,
    3: 2,
    4: 3,
    5: 4,
    6: 5,
    7: 6,
}


def parse_cron_day_field(cron_expr: str) -> str | None:
    parts = cron_expr.split()
    if len(parts) != 5:
        return None
    return parts[4]


def is_scheduled_on_date(cron_expr: str, day: datetime) -> bool:
    """Return True when cron's day-of-week field includes this UTC date."""
    dow_field = parse_cron_day_field(cron_expr)
    if dow_field is None or dow_field == "*":
        return True

    weekday = day.weekday()  # Monday=0 .. Sunday=6
    for token in dow_field.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_s, end_s = token.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            values = range(start, end + 1)
        else:
            values = [int(token)]

        for cron_dow in values:
            if CRON_DOW_TO_WEEKDAY.get(cron_dow) == weekday:
                return True
    return False
