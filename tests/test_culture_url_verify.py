#!/usr/bin/env python3
"""Tests for culture URL HTTP verification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_url_verify import verify_culture_item  # noqa: E402


class TestCultureUrlVerify(unittest.TestCase):
    def test_dead_url_marks_unverified(self) -> None:
        item = {
            "ingestion_source": "openai",
            "topic_ids": ["film"],
            "official_url": "https://example.com/dead",
            "dates": "12 June 2026",
            "times": "20:00",
        }
        session = MagicMock()
        with patch("culture_url_verify.check_url_live", return_value=(False, "HTTP 404")):
            result = verify_culture_item(item, session=session, sleep_ms=0)
        self.assertFalse(result["url_live"])
        self.assertFalse(item["verified"])

    def test_live_deep_url_marks_verified(self) -> None:
        item = {
            "ingestion_source": "openai",
            "topic_ids": ["film"],
            "official_url": "https://www.arsenal-berlin.de/en/archive/film/123",
            "dates": "12 June 2026",
            "times": "20:00",
        }
        session = MagicMock()
        with patch("culture_url_verify.check_url_live", return_value=(True, "")):
            result = verify_culture_item(item, session=session, sleep_ms=0)
        self.assertTrue(result["url_live"])
        self.assertTrue(item["verified"])

    def test_skips_non_openai_by_default(self) -> None:
        item = {
            "ingestion_source": "rss",
            "official_url": "https://example.com/event",
        }
        session = MagicMock()
        result = verify_culture_item(item, session=session, sleep_ms=0, only_openai=True)
        self.assertFalse(result["checked"])


if __name__ == "__main__":
    unittest.main()
