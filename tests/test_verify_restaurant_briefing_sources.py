#!/usr/bin/env python3
"""Tests for restaurant Maps inbox membership verification."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_restaurant_briefing_sources  # noqa: E402
from verify_restaurant_briefing_sources import (  # noqa: E402
    extract_maps_urls,
    maps_url_key,
    verify_restaurant_maps,
)


class TestMapsUrlKey(unittest.TestCase):
    def test_cid_key(self) -> None:
        url = "https://maps.google.com/?cid=4307595915358650379&g_mp=abc"
        self.assertEqual(maps_url_key(url), "cid:4307595915358650379")


class TestVerifyRestaurantMaps(unittest.TestCase):
    def test_extract_maps_lines(self) -> None:
        text = """
**Maps:** https://maps.google.com/?cid=111
**Maps:** https://maps.google.com/?cid=222&g_mp=x
"""
        self.assertEqual(
            extract_maps_urls(text),
            [
                "https://maps.google.com/?cid=111",
                "https://maps.google.com/?cid=222&g_mp=x",
            ],
        )

    def test_accepts_inbox_maps(self) -> None:
        briefing = "**Maps:** https://maps.google.com/?cid=111&g_mp=x\n"
        inbox = {
            "items": [
                {"google_maps_url": "https://maps.google.com/?cid=111&g_mp=other"},
            ]
        }
        cited, unknown = verify_restaurant_maps(
            briefing_text=briefing, inbox_payload=inbox
        )
        self.assertEqual(len(cited), 1)
        self.assertEqual(unknown, [])

    def test_rejects_invented_maps(self) -> None:
        briefing = "**Maps:** https://maps.google.com/?cid=999\n"
        inbox = {
            "items": [
                {"google_maps_url": "https://maps.google.com/?cid=111"},
            ]
        }
        _, unknown = verify_restaurant_maps(
            briefing_text=briefing, inbox_payload=inbox
        )
        self.assertEqual(len(unknown), 1)

    def test_cli_ok_with_matching_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            briefing_path = Path(tmp) / "2026-07-30.md"
            inbox_path = Path(tmp) / "inbox.json"
            briefing_path.write_text(
                "**Maps:** https://maps.google.com/?cid=111&g_mp=x\n",
                encoding="utf-8",
            )
            inbox_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "google_maps_url": "https://maps.google.com/?cid=111&g_mp=y",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(
                sys,
                "argv",
                [
                    "verify_restaurant_briefing_sources.py",
                    "--briefing",
                    str(briefing_path),
                    "--inbox",
                    str(inbox_path),
                ],
            ):
                code = verify_restaurant_briefing_sources.main()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
