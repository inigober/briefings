#!/usr/bin/env python3
"""Tests for briefing email delivery helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from briefing_paths import load_briefing_type  # noqa: E402
from send_briefing_email import (  # noqa: E402
    format_email_subject,
    resolve_briefing_paths,
)


class TestFormatEmailSubject(unittest.TestCase):
    def test_adds_emoji(self) -> None:
        self.assertEqual(
            format_email_subject("News — 13 June 2026", "📰"),
            "📰 News — 13 June 2026",
        )

    def test_idempotent_when_emoji_present(self) -> None:
        title = "📰 News — 13 June 2026"
        self.assertEqual(format_email_subject(title, "📰"), title)

    def test_empty_emoji(self) -> None:
        self.assertEqual(
            format_email_subject("News — 13 June 2026", ""),
            "News — 13 June 2026",
        )


class TestBriefingSubjectEmojiConfig(unittest.TestCase):
    def test_types_have_subject_emoji(self) -> None:
        self.assertEqual(load_briefing_type("news").email_subject_emoji, "📰")
        self.assertEqual(load_briefing_type("berlin-culture").email_subject_emoji, "🎭")
        self.assertEqual(load_briefing_type("berlin-restaurants").email_subject_emoji, "🍽️")


class TestResolveBriefingPaths(unittest.TestCase):
    def test_skips_deleted_changed_files(self) -> None:
        paths = resolve_briefing_paths(
            None,
            ["briefings/berlin-restaurants/2099-01-01.md"],
        )
        self.assertEqual(paths, [])

    def test_keeps_existing_changed_files(self) -> None:
        paths = resolve_briefing_paths(
            None,
            ["briefings/news/2026-06-13.md"],
        )
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].name == "2026-06-13.md")

    def test_explicit_missing_file_still_returned(self) -> None:
        paths = resolve_briefing_paths(
            "briefings/news/2099-01-01.md",
            [],
        )
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].is_file())


if __name__ == "__main__":
    unittest.main()
