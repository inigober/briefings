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

from culture_schedule import (  # noqa: E402
    extract_event_years_from_text,
    is_archive_page_year,
)
from culture_url_verify import apply_page_year_check, verify_culture_item  # noqa: E402

# Fixtures mimicking Radialsystem archive vs revival pages.
ARCHIVE_2022_TEXT = """
THE PRESSING Performance by Dani Brown in the frame of SENSE
Fr 2022 20:30 – 21:30h Premiere
Sa 2022 20:30 – 21:30h Audiodescription + Artist Talk
Su 2022 18:30 – 19:30h
At the festival edition in July 2022, three Berlin choreographers will celebrate
the premiere of their new works: Dani Brown with THE PRESSING.
Haptic Access Tour Sat 30 07 2022 7.30 pm
"""

REVIVAL_2026_TEXT = """
THE PRESSING Performance by Dani Brown
Th 2026 20:30h
Fr 2026 20:30h
Sa 2026 20:30h Artist talk afterwards
Su 2026 19:30h
THE PRESSING premiered in 2022 at Radialsystem.
The 2026 revival is funded by the Berlin Senate Department.
Programme A post-show audience discussion will take place on August 8.
"""


class TestEventYearExtraction(unittest.TestCase):
    def test_archive_2022_years(self) -> None:
        years = extract_event_years_from_text(ARCHIVE_2022_TEXT)
        self.assertEqual(years, {2022})
        self.assertTrue(is_archive_page_year(years, 2026))

    def test_revival_2026_not_archive(self) -> None:
        years = extract_event_years_from_text(REVIVAL_2026_TEXT)
        self.assertIn(2026, years)
        self.assertFalse(is_archive_page_year(years, 2026))


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

    def test_shallow_homepage_url_marked_dead(self) -> None:
        item = {
            "ingestion_source": "openai",
            "topic_ids": ["exhibitions"],
            "official_url": "https://www.hkw.de/en?utm_source=openai",
            "dates": "10 June – 1 September 2026",
            "times": "",
        }
        session = MagicMock()
        with patch("culture_url_verify.check_url_live", return_value=(True, "")):
            result = verify_culture_item(item, session=session, sleep_ms=0)
        self.assertTrue(result["shallow"])
        self.assertFalse(result["url_live"])
        self.assertFalse(item["verified"])

    def test_skips_non_openai_by_default(self) -> None:
        item = {
            "ingestion_source": "rss",
            "official_url": "https://example.com/event",
        }
        session = MagicMock()
        result = verify_culture_item(item, session=session, sleep_ms=0, only_openai=True)
        self.assertFalse(result["checked"])

    def test_archive_page_rejected_for_briefing_year(self) -> None:
        item = {
            "ingestion_source": "openai",
            "topic_ids": ["performing_arts"],
            "official_url": "https://www.radialsystem.de/en/veranstaltungen/the-pressing-dani-brown/",
            "dates": "Wednesday, July 29, 2026",
            "times": "20:30",
        }
        session = MagicMock()
        with (
            patch("culture_url_verify.check_url_live", return_value=(True, "")),
            patch("culture_url_verify.fetch_page_text", return_value=(ARCHIVE_2022_TEXT, "")),
        ):
            result = verify_culture_item(
                item, session=session, sleep_ms=0, briefing_year=2026
            )
        self.assertTrue(result["archive"])
        self.assertFalse(result["url_live"])
        self.assertFalse(item["verified"])
        self.assertIn("archive page year=2022", item["url_verify_notes"])

    def test_revival_page_accepted_and_dates_from_page(self) -> None:
        item = {
            "ingestion_source": "openai",
            "topic_ids": ["performing_arts"],
            "official_url": "https://www.radialsystem.de/en/veranstaltungen/the-pressing-2026/",
            "dates": "Wednesday, July 29, 2026",
            "times": "Time not visible in retrieved event-page excerpt",
        }
        session = MagicMock()
        with (
            patch("culture_url_verify.check_url_live", return_value=(True, "")),
            patch("culture_url_verify.fetch_page_text", return_value=(REVIVAL_2026_TEXT, "")),
        ):
            result = verify_culture_item(
                item, session=session, sleep_ms=0, briefing_year=2026
            )
        self.assertFalse(result.get("archive"))
        self.assertTrue(result["url_live"])
        self.assertTrue(item["verified"])
        self.assertIn(2026, item["page_event_years"])

    def test_apply_page_year_check_archive_helper(self) -> None:
        item: dict = {"dates": "29 July 2026", "times": "20:30"}
        result = apply_page_year_check(item, ARCHIVE_2022_TEXT, briefing_year=2026)
        self.assertTrue(result["archive"])
        self.assertFalse(item["url_live"])


if __name__ == "__main__":
    unittest.main()
