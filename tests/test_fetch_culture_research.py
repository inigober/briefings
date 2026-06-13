#!/usr/bin/env python3
"""Tests for combined culture pre-fetch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_culture_research import (  # noqa: E402
    build_combined_prompt,
    culture_openai_min,
    enrich_candidate,
    merge_calendar_items,
    section_counts,
    section_min_items,
)
from fetch_openai_research import load_yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCombinedCultureFetch(unittest.TestCase):
    def setUp(self) -> None:
        self.topics_cfg = load_yaml(REPO_ROOT / "config/briefings/berlin-culture/topics.yaml")
        self.sources_cfg = load_yaml(REPO_ROOT / "config/briefings/berlin-culture/sources.yaml")

    def test_prompt_is_single_combined_pass(self) -> None:
        prompt = build_combined_prompt(
            date_str="2026-06-09",
            week_label="June 10–16, 2026",
            topics_cfg=self.topics_cfg,
            sources_cfg=self.sources_cfg,
            search_domains=self.sources_cfg.get("allowed_domains") or [],
        )
        self.assertIn("ONE combined pass", prompt)
        self.assertIn("exhibitions", prompt)
        self.assertIn("advance_radar", prompt)
        self.assertNotIn("web_search allowed domains:\n- ceecee.cc", prompt)

    def test_prompt_shows_rss_reduction(self) -> None:
        rss_items = [
            {
                "topic_ids": ["exhibitions"],
                "title": "Sample Show",
                "official_url": "https://example.com/show",
            }
        ]
        prompt = build_combined_prompt(
            date_str="2026-06-09",
            week_label="June 10–16, 2026",
            topics_cfg=self.topics_cfg,
            sources_cfg=self.sources_cfg,
            search_domains=[],
            calendar_items=rss_items,
        )
        self.assertIn("Calendar warehouse", prompt)
        self.assertIn("reduced from 7", prompt)

    def test_prefetch_mins_from_topics_yaml(self) -> None:
        topics = {t["id"]: t for t in self.topics_cfg.get("topics") or []}
        self.assertEqual(section_min_items(topics["exhibitions"]), 7)
        self.assertEqual(section_min_items(topics["music"]), 5)
        self.assertEqual(section_min_items(topics["advance_radar"]), 2)

    def test_culture_openai_min_respects_rss_saturation(self) -> None:
        self.assertEqual(culture_openai_min("exhibitions", 0, 7), 7)
        self.assertEqual(culture_openai_min("exhibitions", 3, 7), 4)
        self.assertEqual(culture_openai_min("exhibitions", 6, 7), 2)

    def test_enrich_candidate_marks_verified(self) -> None:
        item = enrich_candidate(
            {
                "id": "test-1",
                "topic_ids": ["film"],
                "title": "Screening",
                "venue": "Arsenal",
                "dates": "12 June 2026",
                "times": "20:00",
                "artists": [],
                "official_url": "https://www.arsenal-berlin.de/en/archive/film/123",
                "closing_soon": False,
                "why_candidate": "Essay film",
            }
        )
        self.assertTrue(item["verified"])
        self.assertEqual(item["ingestion_source"], "openai")

    def test_merge_culture_rss_dedupes_by_official_url(self) -> None:
        openai_items = [
            enrich_candidate(
                {
                    "topic_ids": ["film"],
                    "title": "A",
                    "venue": "Arsenal",
                    "dates": "12 June",
                    "times": "20:00",
                    "artists": [],
                    "official_url": "https://example.com/a",
                    "closing_soon": False,
                    "why_candidate": "x",
                }
            )
        ]
        rss_items = [
            {
                "topic_ids": ["film"],
                "title": "A duplicate",
                "venue": "Arsenal",
                "dates": "",
                "times": "",
                "artists": [],
                "official_url": "https://example.com/a",
                "closing_soon": False,
                "why_candidate": "rss",
                "ingestion_source": "rss",
                "verified": False,
            },
            {
                "topic_ids": ["music"],
                "title": "B",
                "venue": "KM28",
                "dates": "",
                "times": "",
                "artists": [],
                "official_url": "https://example.com/b",
                "closing_soon": False,
                "why_candidate": "rss",
                "ingestion_source": "rss",
                "verified": False,
            },
        ]
        merged, added = merge_calendar_items(openai_items, rss_items)
        self.assertEqual(len(merged), 2)
        self.assertEqual(added, 1)

    def test_section_counts_primary_topic(self) -> None:
        items = [
            enrich_candidate({"topic_ids": ["film"], "title": "A", "venue": "X", "dates": "d", "times": "t", "artists": [], "official_url": "https://a", "closing_soon": False, "why_candidate": "w"}),
            enrich_candidate({"topic_ids": ["music"], "title": "B", "venue": "Y", "dates": "d", "times": "t", "artists": [], "official_url": "https://b", "closing_soon": False, "why_candidate": "w"}),
        ]
        counts = section_counts(items, self.topics_cfg)
        self.assertEqual(counts["film"], 1)
        self.assertEqual(counts["music"], 1)


if __name__ == "__main__":
    unittest.main()
