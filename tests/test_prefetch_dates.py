#!/usr/bin/env python3
"""Tests for shared pre-fetch date key resolution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from prefetch_dates import resolve_inbox_date_key  # noqa: E402


class TestPrefetchDates(unittest.TestCase):
    def test_news_uses_calendar_date(self) -> None:
        self.assertEqual(resolve_inbox_date_key("news", "2026-06-13"), "2026-06-13")

    def test_culture_snaps_friday_to_tuesday(self) -> None:
        self.assertEqual(resolve_inbox_date_key("berlin-culture", "2026-06-12"), "2026-06-09")

    def test_restaurants_snaps_friday_to_thursday(self) -> None:
        self.assertEqual(resolve_inbox_date_key("berlin-restaurants", "2026-06-12"), "2026-06-11")


if __name__ == "__main__":
    unittest.main()
