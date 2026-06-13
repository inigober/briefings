#!/usr/bin/env python3
"""Shared date helpers for Berlin restaurant briefing runs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def normalize_thursday_run_date(date_str: str) -> tuple[str, datetime]:
    """Restaurant briefings use the Thursday run date as the week key.

    If ``date_str`` is not a Thursday, snap to the previous Thursday so manual
    test runs and health checks align with fetch / verify / slim file names.
    """
    run_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if run_dt.weekday() != 3:
        days_since_thursday = (run_dt.weekday() - 3) % 7 or 7
        run_dt = run_dt - timedelta(days=days_since_thursday)
        date_str = run_dt.strftime("%Y-%m-%d")
    return date_str, run_dt
