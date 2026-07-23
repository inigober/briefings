#!/usr/bin/env python3
"""Shared inbox date keys for pre-fetch, health checks, and backup synthesis."""

from __future__ import annotations

from culture_dates import normalize_tuesday_run_date
from restaurant_dates import normalize_thursday_run_date
from music_dates import normalize_friday_run_date


def resolve_inbox_date_key(type_id: str, date_str: str) -> str:
    """Map a health-check / backup UTC date to the inbox filename stem.

    Weekly briefings key files to the Tuesday, Thursday, or Friday run date, not
    the calendar day of the health check.
    """
    if type_id == "berlin-culture":
        return normalize_tuesday_run_date(date_str)[0]
    if type_id == "berlin-restaurants":
        return normalize_thursday_run_date(date_str)[0]
    if type_id == "music-discovery":
        return normalize_friday_run_date(date_str)[0]
    return date_str
