#!/usr/bin/env python3
"""Tests for combined culture pre-fetch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_calendar import culture_openai_min  # noqa: E402
from fetch_culture_research import (  # noqa: E402
    build_combined_prompt,
    build_search_phase_prompt,
    build_section_search_prompt,
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
        self.state_dir = REPO_ROOT / "state/berlin-culture"

    def test_prompt_is_search_phase_with_required_web_search(self) -> None:
        prompt = build_search_phase_prompt(
            date_str="2026-06-09",
            week_label="June 10–16, 2026",
            topics_cfg=self.topics_cfg,
            sources_cfg=self.sources_cfg,
            search_domains=self.sources_cfg.get("allowed_domains") or [],
            state_dir=self.state_dir,
        )
        self.assertIn("PHASE 1", prompt)
        self.assertIn("web_search REQUIRED", prompt)
        self.assertIn("minimum 4 separate web_search", prompt.lower())
        self.assertIn("exhibitions, film, performing_arts, music", prompt)
        self.assertIn("exhibitions", prompt)
        self.assertIn("HKW", prompt)
        self.assertIn("Already recommended", prompt)
        self.assertNotIn("Return JSON", prompt)

    def test_section_search_prompt_for_film_lists_arsenal(self) -> None:
        prompt = build_section_search_prompt(
            section_id="film",
            date_str="2026-06-09",
            week_label="June 10–16, 2026",
            topics_cfg=self.topics_cfg,
            sources_cfg=self.sources_cfg,
            search_domains=self.sources_cfg.get("allowed_domains") or [],
            state_dir=self.state_dir,
        )
        self.assertIn("Section: **Film", prompt)
        self.assertIn("Arsenal Filminstitut", prompt)
        self.assertIn("web_search REQUIRED", prompt)
        self.assertNotIn("Return JSON", prompt)

    def test_combined_prompt_dry_run_includes_search_phase(self) -> None:
        prompt = build_combined_prompt(
            date_str="2026-06-09",
            week_label="June 10–16, 2026",
            topics_cfg=self.topics_cfg,
            sources_cfg=self.sources_cfg,
            search_domains=self.sources_cfg.get("allowed_domains") or [],
            state_dir=self.state_dir,
        )
        self.assertIn("PHASE 1", prompt)

    def test_prompt_shows_programme_reduction(self) -> None:
        rss_items = [
            {
                "ingestion_source": "rss",
                "topic_ids": ["exhibitions"],
                "title": "Sample Show",
                "venue": "KW Institute for Contemporary Art",
                "official_url": "https://www.kw-berlin.de/en/exhibitions/sample-show",
                "dates": "10 June – 1 September 2026",
                "times": "",
            }
        ]
        prompt = build_search_phase_prompt(
            date_str="2026-06-09",
            week_label="June 10–16, 2026",
            topics_cfg=self.topics_cfg,
            sources_cfg=self.sources_cfg,
            search_domains=[],
            calendar_items=rss_items,
            state_dir=self.state_dir,
        )
        self.assertIn("Venue programme warehouse", prompt)
        self.assertIn("reduced from 7", prompt)

    def test_prompt_separates_press_from_programme(self) -> None:
        items = [
            {
                "ingestion_source": "rss",
                "venue": "Berlin Art Link",
                "title": "Review: Some Show",
                "official_url": "https://www.berlinartlink.com/review",
                "topic_ids": ["exhibitions"],
            }
        ]
        prompt = build_search_phase_prompt(
            date_str="2026-06-09",
            week_label="June 10–16, 2026",
            topics_cfg=self.topics_cfg,
            sources_cfg=self.sources_cfg,
            search_domains=[],
            calendar_items=items,
            state_dir=self.state_dir,
        )
        self.assertIn("Editorial leads", prompt)
        self.assertNotIn("reduced from 7", prompt)

    def test_prefetch_mins_from_topics_yaml(self) -> None:
        topics = {t["id"]: t for t in self.topics_cfg.get("topics") or []}
        self.assertEqual(section_min_items(topics["exhibitions"]), 7)
        self.assertEqual(section_min_items(topics["music"]), 5)
        self.assertEqual(section_min_items(topics["advance_radar"]), 2)

    def test_culture_openai_min_respects_programme_saturation(self) -> None:
        self.assertEqual(culture_openai_min("exhibitions", 0, 7), 7)
        self.assertEqual(culture_openai_min("exhibitions", 3, 7), 4)
        self.assertEqual(culture_openai_min("exhibitions", 6, 7), 2)

    def test_enrich_candidate_verified_only_with_url_live(self) -> None:
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
        self.assertFalse(item["verified"])
        self.assertIsNone(item["url_live"])
        self.assertEqual(item["ingestion_source"], "openai")

        item["url_live"] = True
        enrich_candidate(item)
        self.assertTrue(item["verified"])

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
