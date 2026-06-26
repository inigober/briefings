#!/usr/bin/env python3
"""Tests for culture venue normalization and series inference."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_calendar import infer_series_id, normalize_venue_key  # noqa: E402


class TestCultureVenueSeries(unittest.TestCase):
    def test_dock11_room_uses_parent_venue(self) -> None:
        self.assertEqual(normalize_venue_key("DOCK11, Saal 4"), "dock11")
        self.assertEqual(normalize_venue_key("DOCK11"), "dock11")

    def test_hochzeitssaal_uses_parent_institution(self) -> None:
        self.assertEqual(normalize_venue_key("Hochzeitssaal, Sophiensæle"), "sophiensæle")

    def test_mash_dance_prefix_series(self) -> None:
        item = {
            "title": "Mash Dance Berlin 2026 – Sounds Alive",
            "venue": "DOCK11",
            "official_url": "https://example.com",
        }
        self.assertEqual(infer_series_id(item), "mash-dance-berlin-2026")


if __name__ == "__main__":
    unittest.main()
