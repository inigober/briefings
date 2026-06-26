#!/usr/bin/env python3
"""Tests for culture briefing week window filtering."""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_dates import culture_programme_months, culture_week_date_bounds  # noqa: E402
from culture_schedule import (  # noqa: E402
    dates_overlap_briefing_window,
    filter_items_to_briefing_window,
    item_in_briefing_window,
    parse_culture_date_bounds,
)


class TestCultureBriefingWindow(unittest.TestCase):
    def test_week_bounds_for_june_16_run(self) -> None:
        run_dt = datetime(2026, 6, 16, tzinfo=timezone.utc)
        week_start, week_end = culture_week_date_bounds(run_dt)
        self.assertEqual(week_start, date(2026, 6, 17))
        self.assertEqual(week_end, date(2026, 6, 23))

    def test_programme_months_current_and_next(self) -> None:
        run_dt = datetime(2026, 6, 16, tzinfo=timezone.utc)
        self.assertEqual(culture_programme_months(run_dt), [(2026, 6), (2026, 7)])
        december = datetime(2026, 12, 9, tzinfo=timezone.utc)
        self.assertEqual(culture_programme_months(december), [(2026, 12), (2027, 1)])

    def test_silent_green_june_7_outside_window(self) -> None:
        run_dt = datetime(2026, 6, 16, tzinfo=timezone.utc)
        week_start, week_end = culture_week_date_bounds(run_dt)
        item = {
            "topic_ids": ["music"],
            "dates": "07 June 2026",
            "ingestion_source": "silent_green_html",
        }
        self.assertFalse(item_in_briefing_window(item, week_start, week_end))

    def test_exhibition_until_august_stays_in_window(self) -> None:
        run_dt = datetime(2026, 6, 16, tzinfo=timezone.utc)
        week_start, week_end = culture_week_date_bounds(run_dt)
        item = {
            "topic_ids": ["exhibitions"],
            "dates": "until August 1, 2026",
        }
        self.assertTrue(item_in_briefing_window(item, week_start, week_end))

    def test_filter_drops_only_target_sources(self) -> None:
        run_dt = datetime(2026, 6, 16, tzinfo=timezone.utc)
        week_start, week_end = culture_week_date_bounds(run_dt)
        items = [
            {
                "topic_ids": ["music"],
                "dates": "07 June 2026",
                "ingestion_source": "silent_green_html",
            },
            {
                "topic_ids": ["music"],
                "dates": "21 June 2026",
                "ingestion_source": "openai",
            },
            {
                "topic_ids": ["wildcards"],
                "dates": "26 June 2026",
                "ingestion_source": "index_berlin_ics",
            },
        ]
        kept, dropped = filter_items_to_briefing_window(
            items,
            week_start,
            week_end,
            ingestion_sources={"silent_green_html", "index_berlin_ics"},
        )
        self.assertEqual(dropped, 2)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["ingestion_source"], "openai")

    def test_parse_single_june_date(self) -> None:
        start, end = parse_culture_date_bounds("21 June 2026", reference_year=2026)
        self.assertEqual(start, date(2026, 6, 21))
        self.assertEqual(end, date(2026, 6, 21))

    def test_timed_event_overlap(self) -> None:
        week_start = date(2026, 6, 17)
        week_end = date(2026, 6, 23)
        self.assertTrue(
            dates_overlap_briefing_window(
                date(2026, 6, 21),
                date(2026, 6, 21),
                week_start,
                week_end,
                section_id="music",
            )
        )
        self.assertFalse(
            dates_overlap_briefing_window(
                date(2026, 6, 26),
                date(2026, 6, 26),
                week_start,
                week_end,
                section_id="wildcards",
            )
        )


if __name__ == "__main__":
    unittest.main()
