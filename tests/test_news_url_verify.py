#!/usr/bin/env python3
"""Tests for news URL verification helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from news_url_verify import (  # noqa: E402
    url_looks_suspicious,
    verify_news_item,
    verify_news_items,
)


class TestNewsUrlSuspicious(unittest.TestCase):
    def test_rejects_placeholder_path(self) -> None:
        reason = url_looks_suspicious(
            "https://www.tagesspiegel.de/berlin/12345678.html"
        )
        self.assertIsNotNone(reason)

    def test_accepts_realistic_path(self) -> None:
        reason = url_looks_suspicious(
            "https://www.tagesspiegel.de/politik/ende-des-pannen-bauprojekts-15711730.html"
        )
        self.assertIsNone(reason)

    def test_accepts_handelsblatt_numeric_article_id(self) -> None:
        reason = url_looks_suspicious(
            "https://www.handelsblatt.com/politik/international/"
            "usa-macron-und-trump-planen-treffen-in-versailles/29669594.html"
        )
        self.assertIsNone(reason)


class TestVerifyNewsItems(unittest.TestCase):
    def test_checks_rss_items_by_default(self) -> None:
        item = {
            "ingestion_source": "rss",
            "sources": [{"url": "https://example.com/story-one"}],
        }
        with patch("news_url_verify.probe_url", return_value=("live", "")):
            stats = verify_news_items([item], sleep_ms=0)
        self.assertEqual(stats["checked"], 1)
        self.assertEqual(stats["skipped"], 0)
        self.assertTrue(item["verified"])

    def test_openai_only_skips_rss(self) -> None:
        item = {
            "ingestion_source": "rss",
            "sources": [{"url": "https://example.com/story-one"}],
        }
        stats = verify_news_items([item], sleep_ms=0, only_openai=True)
        self.assertEqual(stats["checked"], 0)
        self.assertEqual(stats["skipped"], 1)

    def test_marks_suspicious_as_dead(self) -> None:
        item = {
            "ingestion_source": "openai",
            "sources": [{"url": "https://www.ft.com/content/fake-slug-only"}],
        }
        stats = verify_news_items([item], sleep_ms=0)
        self.assertEqual(stats["dead"], 1)
        self.assertFalse(item["verified"])

    def test_rss_skips_suspicious_pattern_check(self) -> None:
        item = {
            "ingestion_source": "rss",
            "sources": [
                {
                    "url": "https://www.handelsblatt.com/politik/international/"
                    "usa-macron-und-trump-planen-treffen-in-versailles/29669594.html"
                }
            ],
        }
        with patch("news_url_verify.probe_url", return_value=("live", "")) as mock_probe:
            verify_news_items([item], sleep_ms=0)
        mock_probe.assert_called_once()
        self.assertFalse(mock_probe.call_args.kwargs.get("check_suspicious", True))


if __name__ == "__main__":
    unittest.main()
