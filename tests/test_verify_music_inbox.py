#!/usr/bin/env python3
"""Tests for music-discovery inbox URL verification and slim."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from slim_inbox_for_synthesis import build_music_synthesis_inbox  # noqa: E402
from verify_music_inbox_urls import (  # noqa: E402
    extract_bandcamp_cover,
    extract_og_image,
    verify_music_item,
)


BANDCAMP_HTML = """
<html><head>
<meta property="og:image" content="https://f4.bcbits.com/img/a999_10.jpg">
</head></html>
"""


class TestExtractOgImage(unittest.TestCase):
    def test_property_then_content(self) -> None:
        self.assertEqual(
            extract_og_image(BANDCAMP_HTML),
            "https://f4.bcbits.com/img/a999_10.jpg",
        )

    def test_content_then_property(self) -> None:
        html = '<meta content="https://f4.bcbits.com/img/a1.jpg" property="og:image">'
        self.assertEqual(extract_og_image(html), "https://f4.bcbits.com/img/a1.jpg")

    def test_image_src_and_bcbits_fallbacks(self) -> None:
        html = '<link rel="image_src" href="https://f4.bcbits.com/img/a111_16.jpg">'
        self.assertEqual(
            extract_bandcamp_cover(html),
            "https://f4.bcbits.com/img/a111_10.jpg",
        )
        html = 'background:url(https://f4.bcbits.com/img/a222_5.jpg)'
        self.assertEqual(
            extract_bandcamp_cover(html),
            "https://f4.bcbits.com/img/a222_10.jpg",
        )


class TestVerifyMusicInboxItem(unittest.TestCase):
    def test_live_bandcamp_hydrates_cover_even_if_model_cover_is_dead(self) -> None:
        item = {
            "artist": "Test",
            "release": "EP",
            "bandcamp_url": "https://example.bandcamp.com/album/ep",
            "cover_url": "https://f4.bcbits.com/img/invented.jpg",
            "youtube_url": "https://www.youtube.com/playlist?list=dead",
            "dig_url": "https://example.bandcamp.com/album/other",
        }

        def fake_fetch(url: str, *, session=None, **_kwargs):  # noqa: ANN001
            if "invented" in url or "playlist" in url:
                return 404, "", ""
            if "album/other" in url:
                return 200, "<html></html>", ""
            if "album/ep" in url:
                return 200, BANDCAMP_HTML, ""
            return 200, "", ""

        with patch("verify_music_inbox_urls.fetch_html", side_effect=fake_fetch):
            result = verify_music_item(item, session=MagicMock(), sleep_ms=0)

        self.assertTrue(result["verified"])
        self.assertEqual(result["cover_url"], "https://f4.bcbits.com/img/a999_10.jpg")
        self.assertIsNone(result["youtube_url"])
        self.assertEqual(result["url_live"], "live")

    def test_live_bandcamp_without_cover_is_unverified(self) -> None:
        item = {
            "artist": "Test",
            "release": "EP",
            "bandcamp_url": "https://example.bandcamp.com/album/ep",
            "cover_url": "",
        }

        def fake_fetch(url: str, *, session=None, **_kwargs):  # noqa: ANN001
            return 200, "<html><head><title>No cover</title></head></html>", ""

        with patch("verify_music_inbox_urls.fetch_html", side_effect=fake_fetch):
            result = verify_music_item(item, session=MagicMock(), sleep_ms=0)

        self.assertFalse(result["verified"])
        self.assertEqual(result["cover_url"], "")

    def test_dead_bandcamp_is_unverified(self) -> None:
        item = {
            "artist": "Test",
            "release": "EP",
            "bandcamp_url": "https://example.bandcamp.com/album/missing",
            "cover_url": "https://f4.bcbits.com/img/a1.jpg",
        }

        def fake_fetch(url: str, *, session=None, **_kwargs):  # noqa: ANN001
            return 404, "", ""

        with patch("verify_music_inbox_urls.fetch_html", side_effect=fake_fetch):
            result = verify_music_item(item, session=MagicMock(), sleep_ms=0)

        self.assertFalse(result["verified"])
        self.assertEqual(result["url_live"], "dead")
        self.assertIn("404", result["url_verify_notes"])


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
