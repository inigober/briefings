#!/usr/bin/env python3
"""Tests for venue programme RSS flag."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import yaml  # noqa: E402

from culture_calendar import is_programme_warehouse_item, programme_counts  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestProgrammeFeeds(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = yaml.safe_load(
            (REPO_ROOT / "config/briefings/berlin-culture/sources.yaml").read_text(encoding="utf-8")
        )

    def test_a_trane_rss_counts_as_music_programme(self) -> None:
        item = {
            "topic_ids": ["music"],
            "title": "Jazz Quartet",
            "venue": "A-Trane",
            "official_url": "https://a-trane.de/events/jazz-quartet",
            "dates": "18 June 2026",
            "times": "21:00",
            "ingestion_source": "rss",
            "programme_feed": True,
        }
        self.assertTrue(is_programme_warehouse_item(item, self.sources))
        counts = programme_counts([item], self.sources)
        self.assertEqual(counts.get("music"), 1)


if __name__ == "__main__":
    unittest.main()
