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

from culture_dates import (  # noqa: E402
    culture_advance_horizon_end,
    culture_programme_months,
    culture_week_date_bounds,
)
from culture_schedule import (  # noqa: E402
    classify_event_timing,
    dates_overlap_briefing_window,
    filter_items_to_briefing_window,
    filter_programme_items_by_timing,
    item_in_briefing_window,
    parse_culture_date_bounds,
    route_programme_item_timing,
)


class TestCultureBriefingWindow(unittest.TestCase):
    def setUp(self) -> None:
        self.run_dt = datetime(2026, 6, 16, tzinfo=timezone.utc)
        self.week_start, self.week_end = culture_week_date_bounds(self.run_dt)
        self.horizon_end = culture_advance_horizon_end(self.week_end)

    def test_week_bounds_for_june_16_run(self) -> None:
        self.assertEqual(self.week_start, date(2026, 6, 17))
        self.assertEqual(self.week_end, date(2026, 6, 23))
        self.assertEqual(self.horizon_end, date(2026, 7, 7))

    def test_programme_months_current_and_next(self) -> None:
        self.assertEqual(culture_programme_months(self.run_dt), [(2026, 6), (2026, 7)])
        december = datetime(2026, 12, 9, tzinfo=timezone.utc)
        self.assertEqual(culture_programme_months(december), [(2026, 12), (2027, 1)])

    def test_classify_past_in_week_and_advance(self) -> None:
        past = {"topic_ids": ["music"], "dates": "07 June 2026"}
        in_week = {"topic_ids": ["music"], "dates": "21 June 2026"}
        advance = {"topic_ids": ["music"], "dates": "26 June 2026"}
        beyond = {"topic_ids": ["music"], "dates": "15 July 2026"}

        self.assertEqual(
            classify_event_timing(past, self.week_start, self.week_end, advance_horizon_end=self.horizon_end),
            "past",
        )
        self.assertEqual(
            classify_event_timing(in_week, self.week_start, self.week_end, advance_horizon_end=self.horizon_end),
            "in_week",
        )
        self.assertEqual(
            classify_event_timing(advance, self.week_start, self.week_end, advance_horizon_end=self.horizon_end),
            "advance",
        )
        self.assertEqual(
            classify_event_timing(beyond, self.week_start, self.week_end, advance_horizon_end=self.horizon_end),
            "beyond",
        )

    def test_route_advance_retags_section(self) -> None:
        item = {
            "topic_ids": ["music"],
            "title": "Late June gig",
            "dates": "26 June 2026",
            "ingestion_source": "silent_green_html",
        }
        routed = route_programme_item_timing(item, "advance", primary_section="music")
        self.assertIsNotNone(routed)
        assert routed is not None
        self.assertEqual(routed["topic_ids"], ["advance_radar"])
        self.assertEqual(routed["primary_section"], "music")
        self.assertEqual(routed["timing_bucket"], "advance")

    def test_silent_green_june_7_is_past(self) -> None:
        item = {
            "topic_ids": ["music"],
            "dates": "07 June 2026",
            "ingestion_source": "silent_green_html",
        }
        self.assertFalse(item_in_briefing_window(item, self.week_start, self.week_end))

    def test_exhibition_until_august_stays_in_window(self) -> None:
        item = {
            "topic_ids": ["exhibitions"],
            "dates": "until August 1, 2026",
        }
        self.assertTrue(item_in_briefing_window(item, self.week_start, self.week_end))

    def test_filter_drops_past_keeps_advance_for_programme_sources(self) -> None:
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
        kept, dropped, advance = filter_programme_items_by_timing(
            items,
            self.week_start,
            self.week_end,
        )
        self.assertEqual(dropped, 1)
        self.assertEqual(advance, 1)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["ingestion_source"], "openai")
        self.assertEqual(kept[1]["topic_ids"], ["advance_radar"])

    def test_filter_items_to_briefing_window_compat(self) -> None:
        items = [
            {
                "topic_ids": ["wildcards"],
                "dates": "26 June 2026",
                "ingestion_source": "index_berlin_ics",
            },
        ]
        kept, dropped = filter_items_to_briefing_window(items, self.week_start, self.week_end)
        self.assertEqual(dropped, 0)
        self.assertEqual(kept[0]["topic_ids"], ["advance_radar"])

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
