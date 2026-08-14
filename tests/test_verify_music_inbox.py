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
    extract_microlink_image,
    extract_og_image,
    looks_like_bot_wall,
    pick_musicbrainz_release,
    release_titles_match,
    verify_music_item,
)


BANDCAMP_HTML = """
<html><head>
<meta property="og:image" content="https://f4.bcbits.com/img/a999_10.jpg">
</head></html>
"""
BOT_WALL_HTML = "<html><body>Just a moment</body></html>" + ("x" * 2900)


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
        html = "background:url(https://f4.bcbits.com/img/a222_5.jpg)"
        self.assertEqual(
            extract_bandcamp_cover(html),
            "https://f4.bcbits.com/img/a222_10.jpg",
        )


class TestBotWallAndMatching(unittest.TestCase):
    def test_tiny_challenge_html_is_bot_wall(self) -> None:
        self.assertTrue(looks_like_bot_wall(BOT_WALL_HTML))
        self.assertFalse(looks_like_bot_wall(BANDCAMP_HTML))

    def test_release_titles_distinguish_part_numbers(self) -> None:
        self.assertTrue(release_titles_match("Expanding Time", "Expanding Time - EP"))
        self.assertTrue(release_titles_match("Repercussions Part 2", "Repercussions Part 2 - EP"))
        self.assertFalse(release_titles_match("Repercussions Part 2", "Repercussions Part 1 - EP"))

    def test_microlink_extracts_bandcamp_cover(self) -> None:
        payload = {
            "status": "success",
            "data": {
                "image": {
                    "url": "https://f4.bcbits.com/img/a0676472179_5.jpg",
                    "width": 700,
                    "height": 700,
                }
            },
        }
        self.assertEqual(
            extract_microlink_image(payload),
            "https://f4.bcbits.com/img/a0676472179_10.jpg",
        )
        self.assertIsNone(extract_microlink_image({"status": "fail"}))

    def test_musicbrainz_picks_title_matched_release(self) -> None:
        rows = [
            {
                "id": "mbid-warious2",
                "title": "WARIOUS2",
                "artist-credit": [{"name": "Various Artists", "joinphrase": ""}],
                "release-group": {"id": "rg-warious2"},
            }
        ]
        picked = pick_musicbrainz_release(rows, "Various Artists", "WARIOUS2")
        self.assertEqual(picked["id"], "mbid-warious2")


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
        self.assertEqual(result["url_field_status"]["cover_url"], "from_bandcamp_html")

    def test_bot_wall_uses_microlink_bandcamp_cover(self) -> None:
        item = {
            "artist": "Purelink",
            "release": "Faith",
            "bandcamp_url": "https://purelink.bandcamp.com/album/faith",
            "cover_url": "",
        }
        cover = "https://f4.bcbits.com/img/a1878222548_10.jpg"

        with (
            patch("verify_music_inbox_urls.fetch_html", return_value=(200, BOT_WALL_HTML, "")),
            patch("verify_music_inbox_urls.lookup_microlink_cover", return_value=cover),
            patch("verify_music_inbox_urls.lookup_coverartarchive_cover") as caa,
        ):
            result = verify_music_item(item, session=MagicMock(), sleep_ms=0)

        caa.assert_not_called()
        self.assertTrue(result["verified"])
        self.assertEqual(result["cover_url"], cover)
        self.assertEqual(result["url_field_status"]["cover_url"], "from_microlink")
        self.assertIn("bot wall", result["url_verify_notes"])

    def test_bot_wall_falls_back_to_cover_art_archive(self) -> None:
        item = {
            "artist": "bookworms",
            "release": "depth perceptions",
            "bandcamp_url": "https://bookworms.bandcamp.com/album/depth-perceptions",
            "cover_url": "",
        }
        caa_url = "https://archive.org/download/mbid-abc/front-500.jpg"

        with (
            patch("verify_music_inbox_urls.fetch_html", return_value=(200, BOT_WALL_HTML, "")),
            patch("verify_music_inbox_urls.lookup_microlink_cover", return_value=None),
            patch(
                "verify_music_inbox_urls.lookup_coverartarchive_cover",
                return_value=caa_url,
            ),
        ):
            result = verify_music_item(item, session=MagicMock(), sleep_ms=0)

        self.assertTrue(result["verified"])
        self.assertEqual(result["cover_url"], caa_url)
        self.assertEqual(result["url_field_status"]["cover_url"], "from_coverartarchive")

    def test_live_bandcamp_without_cover_is_unverified(self) -> None:
        item = {
            "artist": "Test",
            "release": "EP",
            "bandcamp_url": "https://example.bandcamp.com/album/ep",
            "cover_url": "",
        }

        def fake_fetch(url: str, *, session=None, **_kwargs):  # noqa: ANN001
            return 200, "<html><head><title>No cover</title></head></html>", ""

        with (
            patch("verify_music_inbox_urls.fetch_html", side_effect=fake_fetch),
            patch("verify_music_inbox_urls.lookup_microlink_cover", return_value=None),
            patch("verify_music_inbox_urls.lookup_coverartarchive_cover", return_value=None),
        ):
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
