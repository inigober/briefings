#!/usr/bin/env python3
"""Tests for culture calendar warehouse classification and novelty index."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_calendar import (  # noqa: E402
    build_novelty_block,
    build_programme_urls_block,
    culture_openai_min,
    is_deep_event_url,
    is_press_item,
    is_programme_warehouse_item,
    mark_item_verified,
    programme_counts,
    press_counts,
)
from fetch_openai_research import load_yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCultureCalendar(unittest.TestCase):
    def setUp(self) -> None:
        self.sources_cfg = load_yaml(REPO_ROOT / "config/briefings/berlin-culture/sources.yaml")
        self.topics_cfg = load_yaml(REPO_ROOT / "config/briefings/berlin-culture/topics.yaml")

    def test_press_item_detected_by_publisher(self) -> None:
        item = {
            "ingestion_source": "rss",
            "venue": "Berlin Art Link",
            "official_url": "https://www.berlinartlink.com/2026/06/review/",
            "topic_ids": ["exhibitions"],
        }
        self.assertTrue(is_press_item(item, self.sources_cfg))
        self.assertFalse(is_programme_warehouse_item(item, self.sources_cfg))

    def test_venue_rss_counts_as_programme(self) -> None:
        item = {
            "ingestion_source": "rss",
            "venue": "Ballhaus Naunynstraße",
            "official_url": "https://ballhausnaunynstrasse.de/en/play/foo",
            "topic_ids": ["performing_arts"],
            "dates": "",
            "times": "",
        }
        self.assertFalse(is_press_item(item, self.sources_cfg))
        self.assertTrue(is_programme_warehouse_item(item, self.sources_cfg))

    def test_programme_and_press_counts_split(self) -> None:
        items = [
            {
                "ingestion_source": "rss",
                "venue": "Berlin Art Link",
                "official_url": "https://www.berlinartlink.com/x",
                "topic_ids": ["exhibitions"],
            },
            {
                "ingestion_source": "rss",
                "venue": "Ballhaus Naunynstraße",
                "official_url": "https://ballhausnaunynstrasse.de/en/play/foo",
                "topic_ids": ["performing_arts"],
            },
        ]
        self.assertEqual(press_counts(items, self.sources_cfg).get("exhibitions"), 1)
        self.assertEqual(programme_counts(items, self.sources_cfg).get("performing_arts"), 1)

    def test_programme_urls_block_lists_hkw_and_gropius(self) -> None:
        block = build_programme_urls_block(
            self.sources_cfg,
            sections_needing_search={"exhibitions", "film"},
        )
        self.assertIn("HKW", block)
        self.assertIn("Gropius Bau", block)
        self.assertIn("MUST use web_search", block)

    def test_novelty_block_from_events_index(self) -> None:
        block = build_novelty_block(
            state_dir=REPO_ROOT / "state/berlin-culture",
            run_date="2026-06-16",
            topics_cfg=self.topics_cfg,
        )
        self.assertIn("Already recommended", block)
        self.assertIn("Shilpa Gupta", block)

    def test_novelty_block_empty_when_no_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            block = build_novelty_block(
                state_dir=Path(tmp),
                run_date="2026-06-16",
                topics_cfg=self.topics_cfg,
            )
            self.assertEqual(block, "")

    def test_mark_verified_requires_url_live_for_openai(self) -> None:
        item = {
            "ingestion_source": "openai",
            "topic_ids": ["film"],
            "official_url": "https://www.arsenal-berlin.de/en/archive/film/123",
            "dates": "12 June 2026",
            "times": "20:00",
            "url_live": None,
        }
        mark_item_verified(item, require_url_live=True)
        self.assertFalse(item["verified"])

        item["url_live"] = True
        mark_item_verified(item, require_url_live=True)
        self.assertTrue(item["verified"])

    def test_long_single_segment_slug_is_deep(self) -> None:
        url = (
            "https://ceecee.cc/ein-fang-in-mitte-austern-ceviche-yuzu-highlights-bei-fat-henry/"
        )
        self.assertTrue(is_deep_event_url(url))

    def test_culture_openai_min_floor(self) -> None:
        self.assertEqual(culture_openai_min("exhibitions", 6, 7), 2)
        self.assertEqual(culture_openai_min("advance_radar", 3, 2), 1)


if __name__ == "__main__":
    unittest.main()
