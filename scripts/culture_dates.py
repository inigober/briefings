#!/usr/bin/env python3
"""Shared date helpers for Berlin culture briefing runs."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

DEFAULT_ADVANCE_HORIZON_DAYS = 14


def culture_week_window(run_date: datetime) -> tuple[datetime, datetime]:
    """Wednesday through the following Tuesday of the briefing week (Tuesday run date)."""
    week_start = run_date + timedelta(days=1)
    week_end = run_date + timedelta(days=7)
    return week_start, week_end


def culture_week_date_bounds(run_date: datetime) -> tuple[date, date]:
    week_start, week_end = culture_week_window(run_date)
    return week_start.date(), week_end.date()


def culture_advance_horizon_end(week_end: date, *, horizon_days: int = DEFAULT_ADVANCE_HORIZON_DAYS) -> date:
    """Last calendar day kept for Advance Radar candidates after the briefing week."""
    return week_end + timedelta(days=horizon_days)


def culture_programme_months(run_dt: datetime) -> list[tuple[int, int]]:
    """Current and next calendar month — for venue HTML programme scrapers."""
    year, month = run_dt.year, run_dt.month
    if month == 12:
        return [(year, month), (year + 1, 1)]
    return [(year, month), (year, month + 1)]


def format_week_range(week_start: datetime, week_end: datetime) -> str:
    if week_start.month == week_end.month:
        return f"{week_start.strftime('%B')} {week_start.day}–{week_end.day}, {week_end.year}"
    return (
        f"{week_start.strftime('%B')} {week_start.day}–"
        f"{week_end.strftime('%B')} {week_end.day}, {week_end.year}"
    )


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
