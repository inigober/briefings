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

from fetch_rss import entry_to_restaurant_item, matches_opening  # noqa: E402
from send_briefing_email import parse_restaurant_briefing, render_restaurant_body_html  # noqa: E402
from slim_inbox_for_synthesis import load_restaurant_openings  # noqa: E402
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
