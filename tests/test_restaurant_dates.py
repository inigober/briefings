#!/usr/bin/env python3
"""Tests for restaurant week-key date normalization."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from restaurant_dates import normalize_thursday_run_date  # noqa: E402


class TestRestaurantDates(unittest.TestCase):
    def test_keeps_thursday(self) -> None:
        date_str, dt = normalize_thursday_run_date("2026-06-11")
        self.assertEqual(date_str, "2026-06-11")
        self.assertEqual(dt.weekday(), 3)

    def test_snaps_friday_to_previous_thursday(self) -> None:
        date_str, _ = normalize_thursday_run_date("2026-06-12")
        self.assertEqual(date_str, "2026-06-11")

    def test_snaps_saturday_test_run(self) -> None:
        date_str, _ = normalize_thursday_run_date("2026-06-13")
        self.assertEqual(date_str, "2026-06-11")


if __name__ == "__main__":
    unittest.main()
