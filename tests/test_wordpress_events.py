#!/usr/bin/env python3
"""Tests for WordPress event feed ingestion."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_calendar import is_programme_warehouse_item  # noqa: E402
from fetch_wordpress import wp_rest_event_to_culture_item  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestWordpressEvents(unittest.TestCase):
    def test_wp_event_item_is_programme_warehouse(self) -> None:
        import yaml

        sources = yaml.safe_load(
            (REPO_ROOT / "config/briefings/berlin-culture/sources.yaml").read_text(encoding="utf-8")
        )
        item = wp_rest_event_to_culture_item(
            {
                "link": "https://example.com/events/jazz-night",
                "title": {"rendered": "Jazz Night"},
                "excerpt": {"rendered": "18 June 2026"},
                "date_gmt": "2026-06-10T12:00:00",
            },
            feed_cfg={"venue": "Example Club", "publisher": "Example"},
            section_id="music",
            blocklist=[],
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["ingestion_source"], "wordpress_events")
        self.assertTrue(is_programme_warehouse_item(item, sources))


if __name__ == "__main__":
    unittest.main()
