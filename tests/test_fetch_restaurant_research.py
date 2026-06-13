#!/usr/bin/env python3
"""Tests for combined restaurant pre-fetch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_restaurant_research import (  # noqa: E402
    build_combined_prompt,
    enrich_candidate,
    section_counts,
)
from fetch_openai_research import load_yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCombinedRestaurantFetch(unittest.TestCase):
    def test_prompt_excludes_google_maps_verification(self) -> None:
        topics_cfg = load_yaml(REPO_ROOT / "config/briefings/berlin-restaurants/topics.yaml")
        sources_cfg = load_yaml(REPO_ROOT / "config/briefings/berlin-restaurants/sources.yaml")
        prompt = build_combined_prompt(
            date_str="2026-06-12",
            topics_cfg=topics_cfg,
            sources_cfg=sources_cfg,
            search_domains=sources_cfg.get("allowed_domains") or [],
        )
        self.assertIn("no Google Maps", prompt)
        self.assertIn("regional_chinese", prompt)
        self.assertNotIn("google_maps_rating", prompt)

    def test_enrich_candidate_adds_places_placeholders(self) -> None:
        item = enrich_candidate(
            {
                "id": "test-1",
                "topic_ids": ["southeast_asian"],
                "name": "Test Restaurant",
                "neighborhood": "Neukolln",
                "address": "Example Str 1",
                "cuisine": "Thai",
                "price_tier": "€€",
                "value_label": None,
                "fine_dining": False,
                "strengths": ["spice"],
                "weaknesses": ["wait"],
                "comparative_context": "context",
                "critical_assessment": "assessment",
                "source_urls": ["https://example.com"],
            }
        )
        self.assertFalse(item["verified"])
        self.assertEqual(item["verification_notes"], "Pending Google Places verification")
        self.assertEqual(item["google_maps_name"], "Test Restaurant")
        self.assertEqual(item["google_maps_url"], "")

    def test_section_counts_primary_topic(self) -> None:
        topics_cfg = load_yaml(REPO_ROOT / "config/briefings/berlin-restaurants/topics.yaml")
        items = [
            enrich_candidate({"topic_ids": ["regional_chinese"], "name": "A"}),
            enrich_candidate({"topic_ids": ["regional_chinese"], "name": "B"}),
            enrich_candidate({"topic_ids": ["fine_dining"], "name": "C"}),
        ]
        counts = section_counts(items, topics_cfg)
        self.assertEqual(counts["regional_chinese"], 2)
        self.assertEqual(counts["fine_dining"], 1)


if __name__ == "__main__":
    unittest.main()
