#!/usr/bin/env python3
"""Tests for culture schedule text extraction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_schedule import extract_schedule_from_text  # noqa: E402


class TestCultureSchedule(unittest.TestCase):
    def test_extracts_german_date_range(self) -> None:
        dates, times = extract_schedule_from_text(
            "Konzert 17–18 Juni 2026 im A-Trane, 20:00",
            reference_year=2026,
        )
        self.assertIn("17", dates)
        self.assertIn("June", dates)
        self.assertEqual(times, "20:00")

    def test_extracts_iso_date(self) -> None:
        dates, _ = extract_schedule_from_text("Screening on 2026-06-18 at Arsenal")
        self.assertEqual(dates, "2026-06-18")

    def test_parse_until_date(self) -> None:
        from culture_schedule import parse_culture_date_bounds

        start, end = parse_culture_date_bounds("until August 1, 2026", reference_year=2026)
        self.assertIsNone(start)
        self.assertEqual(end.month, 8)
        self.assertEqual(end.day, 1)


if __name__ == "__main__":
    unittest.main()
