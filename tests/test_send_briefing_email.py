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
    BRIEFING_FOOTER_TEXT,
    extract_lead_paragraphs,
    extract_preheader,
    format_email_subject,
    render_culture_body_html,
    render_html,
    resolve_briefing_paths,
    transform_selected_reads,
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
"""
        self.assertEqual(
            extract_preheader(md),
            "Export controls and rail delays frame a day of state-capacity stress tests across Europe.",
        )

    def test_culture_prefers_intro(self) -> None:
        md = """# Berlin Culture Briefing — Week of June 16–22, 2026

Kyiv Biennial opens at KW while experimental film anchors a dense mid-June week.

## Top Picks

### Kyiv Biennial – A Bird That Cannot Land
"""
        self.assertEqual(
            extract_preheader(md, section_name="Top Picks", max_len=140),
            "Kyiv Biennial opens at KW while experimental film anchors a dense mid-June week.",
        )

    def test_culture_falls_back_to_top_picks_titles(self) -> None:
        md = """# Berlin Culture Briefing — Week of June 16–22, 2026

## Top Picks

### Kyiv Biennial – A Bird That Cannot Land

**Venue:** KW

### Afterlives

**Venue:** Wolf Kino

## Exhibitions Radar
"""
        self.assertEqual(
            extract_preheader(md, section_name="Top Picks"),
            "Kyiv Biennial – A Bird That Cannot Land · Afterlives",
        )

    def test_falls_back_to_first_headline_without_intro(self) -> None:
        md = """# News Briefing — 13 June 2026

## Spain 🇪🇸

* **Anthropic blocks advanced Claude access**

* **Second story headline**
"""
        self.assertEqual(
            extract_preheader(md),
            "Anthropic blocks advanced Claude access",
        )


class TestCultureEmailIntro(unittest.TestCase):
    SAMPLE = """# Berlin Culture Briefing — Week of June 16–22, 2026

A politically charged opening week pairs biennial-scale art with essay film.

## Top Picks

### Kyiv Biennial – A Bird That Cannot Land

**Venue:** KW Institute for Contemporary Art

**Date(s):** 11 June – 13 September 2026

**Time(s):** Wed–Mon 11:00–19:00

**Short Context:** Opening week at KW.

**Why It Fits:** Strong thematic match.

**Official Link:** [KW](https://www.kw-berlin.de/en/exhibitions/kyiv-biennial)
"""

    def test_renders_intro_before_top_picks(self) -> None:
        html = render_culture_body_html(self.SAMPLE)
        intro_pos = html.index("politically charged opening week")
        top_picks_pos = html.index("Top Picks")
        self.assertLess(intro_pos, top_picks_pos)

    def test_renders_berlin_footer(self) -> None:
        html = render_culture_body_html(self.SAMPLE)
        self.assertIn(BRIEFING_FOOTER_TEXT, html)


class TestNewsEmailFooter(unittest.TestCase):
    SAMPLE = """# News Briefing — 17 June 2026

*Research accessed 16 June 2026.*

Export controls dominate today's edition.

## Spain 🇪🇸

* **First story**

Body with a [source link](https://example.com/article).
"""

    def test_renders_berlin_footer(self) -> None:
        html = render_html(self.SAMPLE, briefing_type="news")
        self.assertIn(BRIEFING_FOOTER_TEXT, html)

    def test_news_links_are_underlined(self) -> None:
        html = render_html(self.SAMPLE, briefing_type="news")
        self.assertIn("text-decoration:underline", html)
        self.assertIn('class="briefing-link"', html)
        self.assertNotIn("text-decoration:none", html)

    def test_news_source_links_have_no_inline_color(self) -> None:
        html = render_html(self.SAMPLE, briefing_type="news")
        self.assertIn('class="briefing-link" href="https://example.com/article"', html)
        self.assertNotRegex(
            html,
            r'class="briefing-link" href="https://example.com/article" style="color:',
        )

    def test_email_css_includes_mobile_and_dark_mode(self) -> None:
        html = render_html(self.SAMPLE, briefing_type="news")
        self.assertIn("@media only screen and (max-width: 480px)", html)
        self.assertIn("@media (prefers-color-scheme: dark)", html)
        self.assertIn("color-scheme", html)
        self.assertIn("light dark", html)
        self.assertIn("p.insight", html)
        self.assertIn("color: #e8e8e8 !important", html)

    def test_body_has_inline_font_size_for_mobile_clients(self) -> None:
        html = render_html(self.SAMPLE, briefing_type="news")
        self.assertIn('body style="', html)
        self.assertIn("font-size:18px", html)


class TestTransformSelectedReads(unittest.TestCase):
    SAMPLE = """## Selected Reads 🗞️

* **Nikkei Asia — AI investors shouldn't choose between Wall Street and Asia**

Why it's worth reading: Regional capital flows matter.

Read article: [AI investors shouldn't choose between Wall Street and Asia](https://asia.nikkei.com/opinion/example)

* **Financial Times — Uber stalls European food delivery push**

Why it's worth reading: Consolidation logic.

Read article: [Uber stalls European food delivery push](https://www.ft.com/content/example)

## Spain 🇪🇸
"""

    def test_merges_headline_with_read_article_url(self) -> None:
        transformed = transform_selected_reads(self.SAMPLE)
        self.assertIn(
            "* [Nikkei Asia — AI investors shouldn't choose between Wall Street and Asia]"
            "(https://asia.nikkei.com/opinion/example)",
            transformed,
        )
        self.assertNotIn("Read article:", transformed)
        link_pos = transformed.index("asia.nikkei.com/opinion/example")
        why_pos = transformed.index("Why it's worth reading: Regional capital flows matter.")
        self.assertLess(link_pos, why_pos)

    def test_renders_linked_headline_in_html(self) -> None:
        md = "# News Briefing — 5 July 2026\n\n" + self.SAMPLE
        html = render_html(md, briefing_type="news")
        self.assertIn('class="briefing-link"', html)
        self.assertIn("selected-read-item", html)
        self.assertIn("Why it", html)
        self.assertNotIn("Read article:", html)
        self.assertNotRegex(html, r"</a>\s*Why it[^<]+</li>")


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
