#!/usr/bin/env python3
"""Tests for music-discovery OpenAI research pre-fetch helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_music_research import (  # noqa: E402
    MUSIC_SEARCH_MIN_CALLS,
    build_search_phase_prompt,
    compact_skip_list,
    enrich_candidate,
    keys_match,
    release_key,
    section_counts,
)
from fetch_openai_research import load_yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestMusicResearchHelpers(unittest.TestCase):
    def setUp(self) -> None:
        self.sources_cfg = load_yaml(REPO_ROOT / "config/briefings/music-discovery/sources.yaml")
        self.taste = {
            "snapshot": "## Recent taste\n- Spray, Floorplan\n",
            "skip_lines": ["Roza Terenzi — Ministry of Wish (recommended)"],
            "known_label_lines": ["Radiant Love (70)"],
            "recent_taste_block": "Rekordbox artists: Spray",
            "releases_index": ["Papa Nugs — Move It Or Lose It EP"],
            "library_albums": [],
            "context": {},
            "known_label_threshold": 15,
        }

    def test_prompt_requires_web_search_and_forbids_invented_urls(self) -> None:
        prompt = build_search_phase_prompt(
            date_str="2026-08-14",
            taste=self.taste,
            search_domains=self.sources_cfg.get("allowed_domains") or [],
        )
        self.assertIn("PHASE 1", prompt)
        self.assertIn("web_search REQUIRED", prompt)
        self.assertIn(f"minimum {MUSIC_SEARCH_MIN_CALLS}", prompt)
        self.assertIn("never invent slugs", prompt.lower())
        self.assertIn("Roza Terenzi", prompt)
        self.assertIn("Radiant Love", prompt)
        self.assertIn("bandcamp.com", prompt)
        self.assertNotIn("Return JSON", prompt)

    def test_keys_match_fuzzy_release(self) -> None:
        self.assertTrue(
            keys_match(release_key("Air", "Moon Safari"), release_key("Air", "Moon Safari"))
        )
        self.assertTrue(
            keys_match(
                release_key("Papa Nugs", "Move It Or Lose It"),
                release_key("Papa Nugs", "Move It Or Lose It EP"),
            )
        )
        self.assertFalse(
            keys_match(release_key("Air", "Moon Safari"), release_key("Spray", "Moon Safari"))
        )

    def test_enrich_drops_skip_and_demotes_known_label(self) -> None:
        skip = [{"artist": "Roza Terenzi", "release": "Ministry of Wish"}]
        known = [{"name": "Radiant Love", "tracks": 70}]
        blocked = enrich_candidate(
            {
                "topic_ids": ["featured"],
                "artist": "Roza Terenzi",
                "release": "Ministry of Wish",
                "label": "Somewhere",
            },
            known_labels=known,
            threshold=15,
            skip_list=skip,
            library_albums=[],
            recent_releases=[],
        )
        self.assertEqual(blocked["blocked_reason"], "skip_list")

        demoted = enrich_candidate(
            {
                "topic_ids": ["featured"],
                "artist": "Someone",
                "release": "New EP",
                "label": "Radiant Love",
                "writeup_url": None,
            },
            known_labels=known,
            threshold=15,
            skip_list=[],
            library_albums=[],
            recent_releases=[],
        )
        self.assertTrue(demoted["known_label"])
        self.assertEqual(demoted["topic_ids"][0], "more_listening")

    def test_compact_skip_list(self) -> None:
        lines = compact_skip_list(
            [{"artist": "A", "release": "B", "status": "owned"}]
        )
        self.assertEqual(lines, ["A — B (owned)"])

    def test_section_counts(self) -> None:
        items = [
            {"topic_ids": ["featured"], "mode": "club"},
            {"topic_ids": ["featured"], "mode": "home"},
            {"topic_ids": ["more_listening"], "mode": "club"},
        ]
        counts = section_counts(items)
        self.assertEqual(counts["featured"], 2)
        self.assertEqual(counts["more_listening"], 1)
        self.assertEqual(counts["club"], 2)
        self.assertEqual(counts["home"], 1)

    def test_sources_include_bandcamp_and_writeups(self) -> None:
        domains = self.sources_cfg.get("allowed_domains") or []
        self.assertIn("bandcamp.com", domains)
        self.assertIn("ra.co", domains)
        self.assertIn("youtube.com", domains)


if __name__ == "__main__":
    unittest.main()
