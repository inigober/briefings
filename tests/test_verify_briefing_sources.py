#!/usr/bin/env python3
"""Tests for post-synthesis briefing URL verification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify_briefing_sources import (  # noqa: E402
    extract_briefing_urls,
    verify_briefing_sources,
)


class TestVerifyBriefingSources(unittest.TestCase):
    def test_extract_footnotes_and_selected_reads(self) -> None:
        text = """
* Story one. ([EL PAÍS][1])

Read article: [El País feature](https://elpais.com/example.html)

[1]: https://elpais.com/story-one.html "Story one"
"""
        urls = extract_briefing_urls(text)
        self.assertEqual(
            urls,
            [
                "https://elpais.com/story-one.html",
                "https://elpais.com/example.html",
            ],
        )

    def test_verify_accepts_inbox_urls(self) -> None:
        briefing = """
[1]: https://elpais.com/story-one.html "Story"
"""
        inbox = {
            "items": [
                {
                    "sources": [
                        {
                            "url": "https://elpais.com/story-one.html",
                            "publisher": "EL PAÍS",
                        }
                    ]
                }
            ]
        }
        cited, unknown = verify_briefing_sources(briefing_text=briefing, inbox_payload=inbox)
        self.assertEqual(len(cited), 1)
        self.assertEqual(unknown, [])

    def test_verify_rejects_invented_urls(self) -> None:
        briefing = """
[1]: https://www.tagesspiegel.de/berlin/fake-12345678.html "Fake"
"""
        inbox = {
            "items": [
                {
                    "sources": [
                        {
                            "url": "https://www.tagesspiegel.de/berlin/real-article.html",
                            "publisher": "Tagesspiegel",
                        }
                    ]
                }
            ]
        }
        _, unknown = verify_briefing_sources(briefing_text=briefing, inbox_payload=inbox)
        self.assertEqual(len(unknown), 1)
        self.assertIn("12345678", unknown[0])


if __name__ == "__main__":
    unittest.main()
