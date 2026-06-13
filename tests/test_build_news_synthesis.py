#!/usr/bin/env python3
"""Tests for news synthesis inbox shaping."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import yaml  # noqa: E402

from slim_inbox_for_synthesis import build_news_synthesis_inbox  # noqa: E402


class TestBuildNewsSynthesisInbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sources_path = REPO_ROOT / "config/briefings/news/sources.yaml"
        topics_path = REPO_ROOT / "config/briefings/news/topics.yaml"
        cls.sources_cfg = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
        cls.topics_cfg = yaml.safe_load(topics_path.read_text(encoding="utf-8"))

    def test_builds_section_items_and_selected_reads(self) -> None:
        raw = {
            "date": "2026-06-13",
            "inbox_dir": "inbox/news",
            "items": [
                {
                    "topic_ids": ["spain"],
                    "headline": "Spain story",
                    "sources": [
                        {
                            "url": "https://elpais.com/espana/story.html",
                            "publisher": "EL PAÍS",
                        }
                    ],
                    "ingestion_source": "rss",
                },
                {
                    "topic_ids": ["world"],
                    "headline": "World read",
                    "sources": [
                        {
                            "url": "https://foreignpolicy.com/2026/world-story/",
                            "publisher": "Foreign Policy",
                        }
                    ],
                    "ingestion_source": "rss",
                },
            ],
        }
        payload = build_news_synthesis_inbox(
            raw,
            sources_cfg=self.sources_cfg,
            topics_cfg=self.topics_cfg,
        )
        self.assertEqual(payload["briefing_type"], "news")
        self.assertGreaterEqual(len(payload["items"]), 1)
        self.assertGreaterEqual(len(payload["selected_read_candidates"]), 1)
        self.assertIn("spain", payload["section_counts"])


if __name__ == "__main__":
    unittest.main()
