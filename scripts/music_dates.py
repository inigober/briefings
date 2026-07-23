#!/usr/bin/env python3
"""Friday run-date helpers for music-discovery inbox keys."""

from __future__ import annotations

from datetime import date, datetime, timedelta


def normalize_friday_run_date(date_str: str) -> tuple[str, date]:
    """Map any calendar day to the Friday that owns that week's music briefing.

    If the date is already Friday, return it. Otherwise return the most recent
    Friday on or before that date (same pattern as culture Tuesday / restaurants Thursday).
    """
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    # Monday=0 … Friday=4
    delta = (day.weekday() - 4) % 7
    friday = day - timedelta(days=delta)
    return friday.isoformat(), friday
