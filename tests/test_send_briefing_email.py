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
    extract_lead_paragraphs,
    extract_preheader,
    format_email_subject,
    resolve_briefing_paths,
)


class TestExtractLeadParagraphs(unittest.TestCase):
    SAMPLE = """# News Briefing — 13 June 2026

*Research accessed 12 June 2026.*

US export controls and infrastructure delivery dominate today's edition.

## Spain 🇪🇸

* **First story**
"""

    def test_extracts_plain_intro(self) -> None:
        self.assertEqual(
            extract_lead_paragraphs(self.SAMPLE),
            "US export controls and infrastructure delivery dominate today's edition.",
        )

    def test_skips_research_accessed_line(self) -> None:
        lead = extract_lead_paragraphs(self.SAMPLE)
        self.assertNotIn("Research accessed", lead)


class TestExtractPreheader(unittest.TestCase):
    def test_prefers_lead_intro(self) -> None:
        md = """# News Briefing — 13 June 2026

Export controls and rail delays frame a day of state-capacity stress tests across Europe.

## Spain 🇪🇸

* **Anthropic blocks advanced Claude access**

## What Matters Today 🧠

1. **US tech controls are biting in Europe.** Details here.
"""
        self.assertEqual(
            extract_preheader(md),
            "Export controls and rail delays frame a day of state-capacity stress tests across Europe.",
        )

    def test_falls_back_to_what_matters_today(self) -> None:
        md = """# News Briefing — 13 June 2026

## Spain 🇪🇸

* **Anthropic blocks advanced Claude access**

## What Matters Today 🧠

1. **US tech controls are biting in Europe.** Details here.

2. **Infrastructure promises face delivery audits.** More details.
"""
        self.assertEqual(
            extract_preheader(md),
            "US tech controls are biting in Europe · Infrastructure promises face delivery audits",
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
