#!/usr/bin/env python3
"""Tests for culture week-key date normalization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_dates import normalize_tuesday_run_date  # noqa: E402


class TestCultureDates(unittest.TestCase):
    def test_keeps_tuesday(self) -> None:
        date_str, dt = normalize_tuesday_run_date("2026-06-09")
        self.assertEqual(date_str, "2026-06-09")
        self.assertEqual(dt.weekday(), 1)

    def test_snaps_saturday_to_previous_tuesday(self) -> None:
        date_str, _ = normalize_tuesday_run_date("2026-06-13")
        self.assertEqual(date_str, "2026-06-09")


if __name__ == "__main__":
    unittest.main()
