#!/usr/bin/env python3
"""Tests for quarterly OpenAI pre-fetch model review."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from openai_model_review import (  # noqa: E402
    is_review_due,
    parse_model_id,
    pick_candidates,
)


class TestModelReviewCalendar(unittest.TestCase):
    def test_first_of_quarter_only(self) -> None:
        self.assertTrue(is_review_due(date(2027, 1, 1)))
        self.assertTrue(is_review_due(date(2027, 4, 1)))
        self.assertTrue(is_review_due(date(2027, 7, 1)))
        self.assertTrue(is_review_due(date(2026, 10, 1)))
        self.assertFalse(is_review_due(date(2026, 10, 2)))
        self.assertFalse(is_review_due(date(2026, 11, 1)))


class TestPickCandidates(unittest.TestCase):
    def test_newer_sol_beats_current(self) -> None:
        listed = [
            "gpt-6.1-sol",
            "gpt-6.2-sol",
            "gpt-7-sol",
            "gpt-6-astra",
            "gpt-6-luna",
            "gpt-5.4-nano",
            "gpt-5.3-codex",
            "gpt-6.1-sol-2026-09-01",
        ]
        self.assertEqual(
            pick_candidates("gpt-6.1-sol", listed),
            ["gpt-7-sol", "gpt-6.2-sol"],
        )

    def test_no_candidates_when_already_newest_sol(self) -> None:
        self.assertEqual(
            pick_candidates("gpt-6.1-sol", ["gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra"]),
            [],
        )

    def test_snapshot_suffix_still_counts(self) -> None:
        self.assertEqual(
            pick_candidates("gpt-6.1-sol", ["gpt-6.2-sol-2026-11-01"]),
            ["gpt-6.2-sol"],
        )


if __name__ == "__main__":
    unittest.main()
