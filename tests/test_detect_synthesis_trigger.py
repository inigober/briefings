#!/usr/bin/env python3
"""Unit tests for synthesis trigger routing helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from detect_synthesis_trigger import (  # noqa: E402
    is_research_inbox_file,
    research_date_from_path,
    synthesis_file_modified,
)
from send_briefing_email import _latest_per_type  # noqa: E402


class TestInboxResearchDetection(unittest.TestCase):
    def test_accepts_synthesis_and_raw(self) -> None:
        prefix = "inbox/news"
        self.assertTrue(is_research_inbox_file(f"{prefix}/2026-06-11-synthesis.json", prefix))
        self.assertTrue(is_research_inbox_file(f"{prefix}/2026-06-11-raw.json", prefix))

    def test_ignores_noise_files(self) -> None:
        prefix = "inbox/news"
        self.assertFalse(is_research_inbox_file(f"{prefix}/2026-06-11-rss.json", prefix))
        self.assertFalse(is_research_inbox_file(f"{prefix}/2026-06-11-spend.json", prefix))
        self.assertFalse(is_research_inbox_file(f"{prefix}/.gitkeep", prefix))

    def test_research_date(self) -> None:
        self.assertEqual(
            research_date_from_path("inbox/news/2026-06-11-synthesis.json"),
            "2026-06-11",
        )

    def test_synthesis_modified(self) -> None:
        paths = ["inbox/news/2026-06-11-synthesis.json", "state/news/last_run.json"]
        self.assertTrue(synthesis_file_modified(paths, "inbox/news", "2026-06-11"))
        self.assertFalse(synthesis_file_modified(paths, "inbox/news", "2026-06-10"))


class TestBriefingExistsGuard(unittest.TestCase):
    def test_skips_when_briefing_already_exists(self) -> None:
        from detect_synthesis_trigger import evaluate_type

        date_str = "2099-06-03"
        synthesis = REPO_ROOT / f"inbox/news/{date_str}-synthesis.json"
        briefing = REPO_ROOT / f"briefings/news/{date_str}.md"
        synthesis.parent.mkdir(parents=True, exist_ok=True)
        briefing.parent.mkdir(parents=True, exist_ok=True)
        synthesis.write_text('{"built_at":"2099-06-03T10:00:00Z"}', encoding="utf-8")
        briefing.write_text("# test\n", encoding="utf-8")

        try:
            should_run, reason, _ = evaluate_type(
                "news",
                commit_sha="deadbeef",
                subject=f"inbox/news: {date_str} research pre-fetch",
                changed=[f"inbox/news/{date_str}-synthesis.json"],
            )
            self.assertFalse(should_run)
            self.assertIn("already exists", reason)
        finally:
            synthesis.unlink(missing_ok=True)
            briefing.unlink(missing_ok=True)


    def test_keeps_newest_date_per_type(self) -> None:
        paths = [
            REPO_ROOT / "briefings/news/2026-06-09.md",
            REPO_ROOT / "briefings/news/2026-06-11.md",
            REPO_ROOT / "briefings/berlin-culture/2026-06-02.md",
            REPO_ROOT / "briefings/berlin-culture/2026-06-09.md",
        ]
        result = _latest_per_type(paths)
        rel = {str(p.relative_to(REPO_ROOT)) for p in result}
        self.assertEqual(
            rel,
            {"briefings/news/2026-06-11.md", "briefings/berlin-culture/2026-06-09.md"},
        )


if __name__ == "__main__":
    unittest.main()
