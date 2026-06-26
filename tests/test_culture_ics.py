#!/usr/bin/env python3
"""Tests for ICS parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_ics import is_ics_calendar, parse_ics_events  # noqa: E402

SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:evt1@example.com
SUMMARY:Ambient Night
DTSTART:20260618T200000Z
DTEND:20260618T230000Z
LOCATION:KM28 Berlin
URL:https://km28.de/events/ambient-night
DESCRIPTION:Live electronics
END:VEVENT
END:VCALENDAR
"""


class TestCultureIcs(unittest.TestCase):
    def test_parses_vevent(self) -> None:
        self.assertTrue(is_ics_calendar(SAMPLE_ICS))
        events = parse_ics_events(SAMPLE_ICS)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Ambient Night")
        self.assertIn("June", events[0]["dates"])
        self.assertEqual(events[0]["times"], "20:00")


if __name__ == "__main__":
    unittest.main()
