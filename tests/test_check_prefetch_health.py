#!/usr/bin/env python3
"""Unit tests for pre-fetch health checks."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_prefetch_health import check_type, inbox_ready, types_for_profile  # noqa: E402
from cron_schedule import is_scheduled_on_date  # noqa: E402


class TestCronSchedule(unittest.TestCase):
    def test_daily_cron_matches_any_day(self) -> None:
        cron = "35 5 * * *"
        self.assertTrue(is_scheduled_on_date(cron, datetime(2026, 6, 12)))
        self.assertTrue(is_scheduled_on_date(cron, datetime(2026, 6, 14)))

    def test_tuesday_only(self) -> None:
        cron = "0 5 * * 2"
        self.assertTrue(is_scheduled_on_date(cron, datetime(2026, 6, 9)))  # Tuesday
        self.assertFalse(is_scheduled_on_date(cron, datetime(2026, 6, 12)))  # Friday


class TestPrefetchHealth(unittest.TestCase):
    def test_morning_profile_types(self) -> None:
        self.assertEqual(types_for_profile("morning"), ("news", "berlin-culture"))

    def test_news_missing_inbox(self) -> None:
        with patch("check_prefetch_health.inbox_ready", return_value=(False, "missing")):
            status = check_type("news", "2099-01-01")
        self.assertFalse(status.ok)
        self.assertEqual(status.type_id, "news")

    def test_all_profile_types(self) -> None:
        self.assertEqual(
            set(types_for_profile("all")),
            {"news", "berlin-culture", "berlin-restaurants"},
        )

    def test_culture_checks_normalized_week_key_on_friday(self) -> None:
        with patch("check_prefetch_health.inbox_ready", return_value=(True, "found synthesis")):
            status = check_type("berlin-culture", "2026-06-12")  # Friday
        self.assertTrue(status.ok)
        self.assertEqual(status.date_str, "2026-06-09")
        self.assertNotEqual(status.detail, "not scheduled today")

    def test_raw_only_inbox_counts_as_missed(self) -> None:
        from unittest.mock import MagicMock

        bt = MagicMock()
        synthesis = MagicMock()
        synthesis.exists.return_value = False
        synthesis.relative_to.return_value = Path("inbox/news/2099-01-01-synthesis.json")
        raw = MagicMock()
        raw.exists.return_value = True
        raw.relative_to.return_value = Path("inbox/news/2099-01-01-raw.json")
        bt.inbox_path.side_effect = lambda _date, suffix: synthesis if suffix == "synthesis" else raw

        ok, detail = inbox_ready(bt, "2099-01-01")
        self.assertFalse(ok)
        self.assertIn("slim step may have failed", detail)


if __name__ == "__main__":
    unittest.main()
