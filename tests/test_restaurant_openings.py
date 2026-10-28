#!/usr/bin/env python3
"""Tests for the restaurant new-opening radar (RSS filter, slim inbox, URL guard, email)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_rss import entry_to_restaurant_item, fetch_feed, matches_opening  # noqa: E402
from send_briefing_email import parse_restaurant_briefing, render_restaurant_body_html  # noqa: E402
from fetch_wordpress import post_to_restaurant_item  # noqa: E402
from slim_inbox_for_synthesis import (  # noqa: E402
    load_reported_opening_urls,
    load_restaurant_openings,
)
from verify_restaurant_briefing_sources import (  # noqa: E402
    extract_openings_urls,
    unknown_openings_urls,
)

OPENING = ["opens", "eröffnet"]
FOOD = ["restaurant", "bar"]


class TestMatchesOpening(unittest.TestCase):
    def test_food_feed_needs_only_opening_term(self) -> None:
        self.assertTrue(matches_opening("Noodle spot opens in Wedding", opening_terms=OPENING, food_terms=FOOD, general=False))

    def test_general_feed_needs_food_term_too(self) -> None:
        self.assertFalse(matches_opening("Gallery opens new show", opening_terms=OPENING, food_terms=FOOD, general=True))
        self.assertTrue(matches_opening("New restaurant opens in Neukölln", opening_terms=OPENING, food_terms=FOOD, general=True))

    def test_no_opening_term(self) -> None:
        self.assertFalse(matches_opening("Best ramen in Berlin", opening_terms=OPENING, food_terms=FOOD, general=False))


class TestEntryToRestaurantItem(unittest.TestCase):
    def test_builds_item(self) -> None:
        entry = SimpleNamespace(
            link="https://example.com/a",
            title="Dumpling place opens",
            summary="<p>In Wedding</p>",
            published_parsed=(2026, 10, 20, 0, 0, 0),
        )
        item = entry_to_restaurant_item(
            entry, feed_cfg={"publisher": "Ex"}, section_id="x", blocklist=[],
            opening_terms=OPENING, food_terms=FOOD,
        )
        self.assertEqual(item["url"], "https://example.com/a")
        self.assertEqual(item["published_at"], "2026-10-20")
        self.assertEqual(item["publisher"], "Ex")

    def test_filtered_out(self) -> None:
        entry = SimpleNamespace(link="https://example.com/b", title="Recipe", summary="")
        self.assertIsNone(
            entry_to_restaurant_item(
                entry, feed_cfg={}, section_id="x", blocklist=[],
                opening_terms=OPENING, food_terms=FOOD,
            )
        )


class TestLoadOpenings(unittest.TestCase):
    def test_missing_file(self) -> None:
        self.assertEqual(load_restaurant_openings(Path("/nonexistent/x-rss.json")), [])

    def test_newest_first_and_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r-rss.json"
            path.write_text(json.dumps({"items": [
                {"url": "https://a", "published_at": "2026-10-01", "headline": "old"},
                {"url": "https://b", "published_at": "2026-10-20", "headline": "new"},
            ]}))
            got = load_restaurant_openings(path, limit=1)
            self.assertEqual([i["url"] for i in got], ["https://b"])


class TestWordpressRestaurantItem(unittest.TestCase):
    POST = {
        "link": "https://example.com/p",
        "title": {"rendered": "New restaurant opens in Neukölln"},
        "excerpt": {"rendered": "<p>Dumplings</p>"},
        "date_gmt": "2026-10-21T08:00:00",
    }

    def test_builds_item(self) -> None:
        item = post_to_restaurant_item(
            self.POST, feed_cfg={"publisher": "Ex", "general": True}, blocklist=[],
            opening_terms=OPENING, food_terms=FOOD,
        )
        self.assertEqual(item["url"], "https://example.com/p")
        self.assertEqual(item["published_at"], "2026-10-21")
        self.assertEqual(item["ingestion_source"], "wordpress")

    def test_non_opening_dropped(self) -> None:
        post = {**self.POST, "title": {"rendered": "Gallery guide"}, "excerpt": {"rendered": ""}}
        self.assertIsNone(
            post_to_restaurant_item(
                post, feed_cfg={"general": True}, blocklist=[],
                opening_terms=OPENING, food_terms=FOOD,
            )
        )


class TestMergedOpenings(unittest.TestCase):
    def test_merges_and_dedupes_across_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.json", Path(tmp) / "b.json"
            a.write_text(json.dumps({"items": [{"url": "https://x/1/", "published_at": "2026-10-01"}]}))
            b.write_text(json.dumps({"items": [
                {"url": "https://x/1", "published_at": "2026-10-01"},
                {"url": "https://x/2", "published_at": "2026-10-05"},
            ]}))
            got = load_restaurant_openings(a, b)
            self.assertEqual([i["url"] for i in got], ["https://x/2", "https://x/1/"])


class TestReportedOpenings(unittest.TestCase):
    def test_reported_urls_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "r-rss.json"
            feed.write_text(json.dumps({"items": [
                {"url": "https://x/old", "published_at": "2026-10-10"},
                {"url": "https://x/new", "published_at": "2026-10-20"},
            ]}))
            state = Path(tmp) / "openings_reported.json"
            state.write_text(json.dumps([{"url": "https://x/old/", "date": "2026-10-22"}]))
            reported = load_reported_opening_urls(state)
            got = load_restaurant_openings(feed, reported_urls=reported)
            self.assertEqual([i["url"] for i in got], ["https://x/new"])

    def test_missing_or_bad_state_file_means_nothing_reported(self) -> None:
        self.assertEqual(load_reported_opening_urls(Path("/nonexistent/x.json")), set())
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("not json")
            self.assertEqual(load_reported_opening_urls(bad), set())


class TestFeedStats(unittest.TestCase):
    def test_checked_count_ignores_posts_outside_window(self) -> None:
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        now = datetime.now(timezone.utc)

        def entry(link: str, title: str, age_days: int) -> SimpleNamespace:
            when = (now - timedelta(days=age_days)).timetuple()[:6]
            return SimpleNamespace(link=link, title=title, summary="", published_parsed=when)

        parsed = SimpleNamespace(
            bozo=False,
            entries=[
                entry("https://x/a", "New restaurant opens", 1),
                entry("https://x/b", "Gallery guide", 2),
                entry("https://x/c", "Old restaurant opens", 40),
            ],
        )
        stats: dict = {}
        with patch("fetch_rss.feedparser.parse", return_value=parsed):
            items, err = fetch_feed(
                {"publisher": "X", "url": "https://x/feed"},
                cutoff=now - timedelta(days=14),
                blocklist=[],
                item_format="restaurant",
                opening_terms=OPENING,
                food_terms=FOOD,
                stats=stats,
            )
        self.assertIsNone(err)
        self.assertEqual(len(items), 1)
        self.assertEqual(stats["checked"], 2)


BRIEFING = """# Berlin Restaurant Briefing — Week of 2026-10-22

Intro.

### Example — Wedding — €

**Maps:** https://maps.google.com/?cid=1

Body.

### New openings to watch

- **Noodle Bar** (Wedding) — Hand-pulled noodles. [Berlin Food Stories](https://bfs.example/noodle)

### This week's strongest bets

1. Example, for noodles.
"""


class TestOpeningsGuardAndEmail(unittest.TestCase):
    def test_extract_urls_stops_at_next_heading(self) -> None:
        self.assertEqual(extract_openings_urls(BRIEFING), ["https://bfs.example/noodle"])

    def test_unknown_urls(self) -> None:
        ok = {"openings": [{"url": "https://bfs.example/noodle/"}]}
        self.assertEqual(unknown_openings_urls(briefing_text=BRIEFING, inbox_payload=ok), [])
        self.assertEqual(
            unknown_openings_urls(briefing_text=BRIEFING, inbox_payload={"openings": []}),
            ["https://bfs.example/noodle"],
        )

    def test_parser_keeps_openings_out_of_entries(self) -> None:
        parsed = parse_restaurant_briefing(BRIEFING)
        self.assertEqual(len(parsed.entries), 1)
        self.assertEqual(parsed.entries[0].body_paragraphs, ["Body."])
        self.assertEqual(len(parsed.openings), 1)
        self.assertEqual(len(parsed.strongest_bets), 1)

    def test_html_renders_section(self) -> None:
        html = render_restaurant_body_html(BRIEFING)
        self.assertIn("New openings to watch", html)
        self.assertIn("https://bfs.example/noodle", html)


if __name__ == "__main__":
    unittest.main()
