#!/usr/bin/env python3
"""Tests for culture synthesis inbox shaping."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import yaml  # noqa: E402

from slim_inbox_for_synthesis import build_culture_synthesis_inbox  # noqa: E402


class TestBuildCultureSynthesisInbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sources_path = REPO_ROOT / "config/briefings/berlin-culture/sources.yaml"
        topics_path = REPO_ROOT / "config/briefings/berlin-culture/topics.yaml"
        cls.sources_cfg = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
        cls.topics_cfg = yaml.safe_load(topics_path.read_text(encoding="utf-8"))

    def test_drops_dead_openai_urls(self) -> None:
        raw = {
            "date": "2026-06-16",
            "inbox_dir": "inbox/berlin-culture",
            "items": [
                {
                    "topic_ids": ["film"],
                    "title": "Live screening",
                    "venue": "Arsenal",
                    "official_url": "https://www.arsenal-berlin.de/en/archive/film/123",
                    "dates": "12 June 2026",
                    "times": "20:00",
                    "ingestion_source": "openai",
                    "url_live": True,
                    "verified": True,
                },
                {
                    "topic_ids": ["film"],
                    "title": "Dead screening",
                    "venue": "Example Kino",
                    "official_url": "https://example.com/dead",
                    "dates": "12 June 2026",
                    "times": "20:00",
                    "ingestion_source": "openai",
                    "url_live": False,
                    "verified": False,
                },
            ],
        }
        payload = build_culture_synthesis_inbox(
            raw,
            sources_cfg=self.sources_cfg,
            topics_cfg=self.topics_cfg,
        )
        titles = {item["title"] for item in payload["items"]}
        self.assertIn("Live screening", titles)
        self.assertNotIn("Dead screening", titles)


if __name__ == "__main__":
    unittest.main()
