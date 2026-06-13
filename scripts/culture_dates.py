#!/usr/bin/env python3
"""Shared date helpers for Berlin culture briefing runs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def normalize_tuesday_run_date(date_str: str) -> tuple[str, datetime]:
    """Culture briefings use the Tuesday run date as the file key.

    If ``date_str`` is not a Tuesday, snap to the previous Tuesday so manual
    test runs align with fetch / slim file names.
    """
    run_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if run_dt.weekday() != 1:
        days_since_tuesday = (run_dt.weekday() - 1) % 7 or 7
        run_dt = run_dt - timedelta(days=days_since_tuesday)
        date_str = run_dt.strftime("%Y-%m-%d")
    return date_str, run_dt
