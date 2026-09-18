#!/usr/bin/env python3
"""Tests for the missing-closing-date exhibition audit log."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from culture_missing_end_log import (  # noqa: E402
    append_missing_end_date_row,
    format_log_row,
    parse_log_rows,
    summarize_log,
)


class TestCultureMissingEndLog(unittest.TestCase):
    def test_format_and_parse_roundtrip(self) -> None:
        line = format_log_row(
            date_str="2026-09-22",
            title="Show | Pipe",
            venue="Venue Two",
            dates="Opening Thursday, 17 September 2026",
            url="https://example.com/show",
            notes="spot-checked; no run end",
        )
        self.assertNotIn("Show | Pipe", line)
        self.assertIn("Show / Pipe", line)
        rows = parse_log_rows("header\n" + line + "\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-09-22")
        self.assertEqual(rows[0]["title"], "Show / Pipe")
        self.assertEqual(rows[0]["url"], "https://example.com/show")

    def test_append_skips_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing_end_dates.md"
            first = append_missing_end_date_row(
                date_str="2026-09-22",
                title="Long Show",
                venue="Venue Two",
                dates="Opening Thursday, 17 September 2026",
                url="https://example.com/b",
                path=path,
            )
            second = append_missing_end_date_row(
                date_str="2026-09-22",
                title="Long Show",
                venue="Venue Two",
                dates="Opening Thursday, 17 September 2026",
                url="https://example.com/b/",
                path=path,
            )
            other = append_missing_end_date_row(
                date_str="2026-09-22",
                title="Other Show",
                venue="Venue Three",
                dates="Opening Friday, 18 September 2026",
                url="https://example.com/c",
                path=path,
            )
            self.assertTrue(first)
            self.assertFalse(second)
            self.assertTrue(other)
            text = path.read_text(encoding="utf-8")
            rows = parse_log_rows(text)
            self.assertEqual(len(rows), 2)
            self.assertEqual(summarize_log(text), [("2026-09-22", 2)])


if __name__ == "__main__":
    unittest.main()
