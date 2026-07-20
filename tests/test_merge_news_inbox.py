#!/usr/bin/env python3
"""Tests for news RSS + WordPress merge pre-fetch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_openai_research import load_yaml  # noqa: E402
from fetch_wordpress import post_to_news_item  # noqa: E402
from merge_news_inbox import merge_inbox_items  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestNewsWordPressAndMerge(unittest.TestCase):
    def test_post_to_news_item_maps_fields(self) -> None:
        item = post_to_news_item(
            {
                "link": "https://www.the-berliner.com/berlin/sample-story/",
                "title": {"rendered": "Berlin housing policy shift"},
                "excerpt": {"rendered": "<p>City senate outlines new rules.</p>"},
                "date_gmt": "2026-06-13T08:00:00",
            },
            feed_cfg={"publisher": "The Berliner"},
            section_id="berlin",
            blocklist=[],
        )
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["topic_ids"], ["berlin"])
        self.assertEqual(item["ingestion_source"], "wordpress")
        self.assertEqual(item["sources"][0]["url"], "https://www.the-berliner.com/berlin/sample-story/")

    def test_merge_dedupes_by_url(self) -> None:
        rss = [
            {
                "ingestion_source": "rss",
                "sources": [{"url": "https://example.com/a", "publisher": "A"}],
            }
        ]
        wp = [
            {
                "ingestion_source": "wordpress",
                "sources": [{"url": "https://example.com/a", "publisher": "A"}],
            },
            {
                "ingestion_source": "wordpress",
                "sources": [{"url": "https://example.com/b", "publisher": "B"}],
            },
        ]
        merged, counts = merge_inbox_items(rss, wp)
        self.assertEqual(len(merged), 2)
        self.assertEqual(counts["rss"], 1)
        self.assertEqual(counts["wordpress"], 1)

    def test_news_sources_yaml_has_berliner_wordpress(self) -> None:
        sources_cfg = load_yaml(REPO_ROOT / "config/briefings/news/sources.yaml")
        feeds = sources_cfg.get("wordpress_feeds") or []
        urls = [f.get("url", "") for f in feeds]
        self.assertTrue(any("the-berliner.com/wp-json" in url for url in urls))

    def test_news_sources_yaml_has_20percent_berlin_rss(self) -> None:
        sources_cfg = load_yaml(REPO_ROOT / "config/briefings/news/sources.yaml")
        feeds = sources_cfg.get("rss_feeds") or []
        match = next(
            (f for f in feeds if "20percent.berlin" in (f.get("url") or "")),
            None,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.get("section_ids"), ["berlin"])
        self.assertGreaterEqual(int(match.get("max_age_hours") or 0), 168)

    def test_news_openai_fetch_disabled(self) -> None:
        from unittest.mock import patch

        from fetch_openai_research import main

        with patch("sys.argv", ["fetch_openai_research.py", "--type", "news"]):
            self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
