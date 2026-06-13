#!/usr/bin/env python3
"""Unit tests for backup synthesis routing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from detect_synthesis_trigger import detect_backup_trigger  # noqa: E402


class TestBackupTrigger(unittest.TestCase):
    def test_finds_pending_news(self) -> None:
        synthesis = REPO_ROOT / "inbox/news/2099-06-01-synthesis.json"
        briefing = REPO_ROOT / "briefings/news/2099-06-01.md"
        synthesis.parent.mkdir(parents=True, exist_ok=True)
        briefing.parent.mkdir(parents=True, exist_ok=True)
        synthesis.write_text("{}", encoding="utf-8")
        if briefing.exists():
            briefing.unlink()

        try:
            decision = detect_backup_trigger("2099-06-01")
            self.assertEqual(decision.type_id, "news")
            self.assertIn("backup:", decision.reason)
        finally:
            synthesis.unlink(missing_ok=True)

    def test_skips_when_briefing_exists(self) -> None:
        date_str = "2099-06-02"
        synthesis = REPO_ROOT / f"inbox/news/{date_str}-synthesis.json"
        briefing = REPO_ROOT / f"briefings/news/{date_str}.md"
        synthesis.parent.mkdir(parents=True, exist_ok=True)
        briefing.parent.mkdir(parents=True, exist_ok=True)
        synthesis.write_text("{}", encoding="utf-8")
        briefing.write_text("# test\n", encoding="utf-8")

        try:
            with patch(
                "detect_synthesis_trigger.load_manifest",
                return_value={"news": {}},
            ):
                decision = detect_backup_trigger(date_str)
            self.assertIsNone(decision.type_id)
        finally:
            synthesis.unlink(missing_ok=True)
            briefing.unlink(missing_ok=True)

    def test_culture_uses_tuesday_key_on_friday(self) -> None:
        date_str = "2099-06-09"  # Tuesday key
        friday = "2099-06-13"
        synthesis = REPO_ROOT / f"inbox/berlin-culture/{date_str}-synthesis.json"
        briefing = REPO_ROOT / f"briefings/berlin-culture/{date_str}.md"
        synthesis.parent.mkdir(parents=True, exist_ok=True)
        briefing.parent.mkdir(parents=True, exist_ok=True)
        synthesis.write_text("{}", encoding="utf-8")
        if briefing.exists():
            briefing.unlink()

        try:
            with patch(
                "detect_synthesis_trigger.load_manifest",
                return_value={"berlin-culture": {}},
            ):
                decision = detect_backup_trigger(friday)
            self.assertEqual(decision.type_id, "berlin-culture")
            self.assertIn(date_str, decision.reason)
        finally:
            synthesis.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
