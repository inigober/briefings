#!/usr/bin/env python3
"""Tests for WordPress culture pre-fetch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_openai_research import load_yaml  # noqa: E402
from fetch_wordpress import post_to_culture_item  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestWordPressCultureFetch(unittest.TestCase):
    def test_post_to_culture_item_maps_fields(self) -> None:
        item = post_to_culture_item(
            {
                "link": "https://www.the-berliner.com/berlin/sample-article/",
                "title": {"rendered": "Sample exhibition roundup"},
                "excerpt": {"rendered": "<p>A look at new shows across Berlin.</p>"},
            },
            feed_cfg={"publisher": "The Berliner", "venue": "The Berliner"},
            section_id="wildcards",
            blocklist=[],
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["topic_ids"], ["wildcards"])
        self.assertEqual(item["ingestion_source"], "wordpress")
        self.assertFalse(item["verified"])
        self.assertIn("the-berliner.com", item["official_url"])

    def test_sources_yaml_has_berliner_feed(self) -> None:
        sources_cfg = load_yaml(REPO_ROOT / "config/briefings/berlin-culture/sources.yaml")
        feeds = sources_cfg.get("wordpress_feeds") or []
        urls = [f.get("url", "") for f in feeds]
        self.assertTrue(any("the-berliner.com/wp-json" in url for url in urls))


if __name__ == "__main__":
    unittest.main()
