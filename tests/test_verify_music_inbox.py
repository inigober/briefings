#!/usr/bin/env python3
"""Tests for music-discovery inbox URL verification and slim."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from slim_inbox_for_synthesis import build_music_synthesis_inbox  # noqa: E402
from verify_music_inbox_urls import verify_music_item  # noqa: E402


class TestVerifyMusicInboxItem(unittest.TestCase):
    def test_requires_live_bandcamp_and_cover(self) -> None:
        item = {
            "artist": "Test",
            "release": "EP",
            "bandcamp_url": "https://example.bandcamp.com/album/ep",
            "cover_url": "https://f4.bcbits.com/img/a1.jpg",
            "youtube_url": "https://www.youtube.com/playlist?list=dead",
            "dig_url": "https://example.bandcamp.com/album/other",
        }

        def fake_live(url: str, *, session=None):  # noqa: ANN001
            if "playlist" in url:
                return False, "HTTP 404"
            return True, ""

        with patch("verify_music_inbox_urls.check_url_live", side_effect=fake_live):
            result = verify_music_item(item, sleep_ms=0)

        self.assertTrue(result["verified"])
        self.assertIsNone(result["youtube_url"])
        self.assertEqual(result["url_live"], "live")

    def test_dead_bandcamp_is_unverified(self) -> None:
        item = {
            "artist": "Test",
            "release": "EP",
            "bandcamp_url": "https://example.bandcamp.com/album/missing",
            "cover_url": "https://f4.bcbits.com/img/a1.jpg",
        }

        def fake_live(url: str, *, session=None):  # noqa: ANN001
            if "missing" in url:
                return False, "HTTP 404"
            return True, ""

        with patch("verify_music_inbox_urls.check_url_live", side_effect=fake_live):
            result = verify_music_item(item, sleep_ms=0)

        self.assertFalse(result["verified"])
        self.assertEqual(result["url_live"], "dead")


class TestSlimMusicInbox(unittest.TestCase):
    def test_keeps_verified_only(self) -> None:
        raw = {
            "date": "2026-08-14",
            "model": "gpt-5.4",
            "inbox_dir": "inbox/music-discovery",
            "items": [
                {
                    "id": "a",
                    "topic_ids": ["featured"],
                    "artist": "Live Act",
                    "release": "One",
                    "verified": True,
                    "bandcamp_url": "https://a.bandcamp.com/album/one",
                    "youtube_url": "https://youtube.com/playlist?list=1",
                },
                {
                    "id": "b",
                    "topic_ids": ["featured"],
                    "artist": "Dead Act",
                    "release": "Two",
                    "verified": False,
                },
                {
                    "id": "c",
                    "topic_ids": ["more_listening"],
                    "artist": "Extra",
                    "release": "Three",
                    "verified": True,
                    "bandcamp_url": "https://c.bandcamp.com/album/three",
                },
            ],
        }
        topics = {
            "topics": [
                {"id": "featured", "enabled": True, "max_items": 6, "slim_cap": 12},
                {"id": "more_listening", "enabled": True, "max_items": 4, "slim_cap": 8},
            ]
        }
        payload = build_music_synthesis_inbox(raw, topics_cfg=topics)
        ids = {item["id"] for item in payload["items"]}
        self.assertEqual(ids, {"a", "c"})
        self.assertEqual(payload["verified_count"], 2)
        self.assertEqual(payload["section_counts"]["featured"], 1)
        self.assertEqual(payload["section_counts"]["more_listening"], 1)


if __name__ == "__main__":
    unittest.main()
