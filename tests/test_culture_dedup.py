#!/usr/bin/env python3
"""Tests for culture series/event deduplication."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import yaml  # noqa: E402

from culture_calendar import infer_series_id, normalize_event_key  # noqa: E402
from slim_inbox_for_synthesis import build_culture_synthesis_inbox  # noqa: E402


class TestCultureDedup(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sources_path = REPO_ROOT / "config/briefings/berlin-culture/sources.yaml"
        topics_path = REPO_ROOT / "config/briefings/berlin-culture/topics.yaml"
        cls.sources_cfg = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
        cls.topics_cfg = yaml.safe_load(topics_path.read_text(encoding="utf-8"))

    def test_infer_series_id_from_url(self) -> None:
        item = {
            "title": "The Gospels of Aerial",
            "venue": "Panke Gallery",
            "official_url": "https://polishartweek.com/event/gospels",
        }
        self.assertEqual(infer_series_id(item), "polish-art-week")

    def test_series_cap_across_sections(self) -> None:
        raw = {
            "date": "2026-06-16",
            "inbox_dir": "inbox/berlin-culture",
            "items": [
                {
                    "topic_ids": ["exhibitions"],
                    "title": "Polish Art Week & Avant Art Festival Berlin",
                    "venue": "Multiple venues",
                    "official_url": "https://polishartweek.com/",
                    "dates": "22–28 June 2026",
                    "event_kind": "festival_overview",
                    "series_id": "polish-art-week",
                    "ingestion_source": "openai",
                    "url_live": True,
                    "verified": True,
                },
                {
                    "topic_ids": ["wildcards"],
                    "title": "Polish Art Week — workshops",
                    "venue": "Polish Institute Berlin",
                    "official_url": "https://polishartweek.com/workshops",
                    "dates": "22–28 June 2026",
                    "event_kind": "festival_event",
                    "series_id": "polish-art-week",
                    "ingestion_source": "openai",
                    "url_live": True,
                    "verified": True,
                },
                {
                    "topic_ids": ["film"],
                    "title": "Unique screening",
                    "venue": "Wolf Kino",
                    "official_url": "https://wolfberlin.org/film/a",
                    "dates": "18 June 2026",
                    "ingestion_source": "openai",
                    "url_live": True,
                    "verified": True,
                },
            ],
        }
        payload = build_culture_synthesis_inbox(
            raw,
            sources_cfg=self.sources_cfg,
            topics_cfg=self.topics_cfg,
        )
        titles = [item["title"] for item in payload["items"]]
        polish_hits = [t for t in titles if "Polish Art Week" in t]
        self.assertEqual(len(polish_hits), 1)
        reasons = {r["reason"] for r in payload["editorial_context"]["rejected_candidates"]}
        self.assertTrue(any(r.startswith("series_cap:") for r in reasons))

    def test_event_duplicate_same_title_venue(self) -> None:
        item_a = {"title": "NO LIMIT", "venue": "Hochzeitssaal, Sophiensæle"}
        item_b = {"title": "NO LIMIT", "venue": "Sophiensæle"}
        self.assertEqual(normalize_event_key(item_a), normalize_event_key(item_b))


if __name__ == "__main__":
    unittest.main()
