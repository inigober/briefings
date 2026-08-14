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

from briefing_paths import load_briefing_type, production_briefing_exists  # noqa: E402
from detect_synthesis_trigger import (  # noqa: E402
    _best_skip_rejection,
    detect_smoke_trigger,
    inbox_research_files_for_date,
    is_research_inbox_file,
    latest_inbox_date,
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

    def test_ignores_music_taste_cache_files(self) -> None:
        prefix = "inbox/music-discovery"
        self.assertFalse(
            is_research_inbox_file(f"{prefix}/2026-08-14-context.json", prefix)
        )
        self.assertFalse(
            is_research_inbox_file(f"{prefix}/2026-08-14-taste-snapshot.md", prefix)
        )
        self.assertTrue(
            is_research_inbox_file(f"{prefix}/2026-08-14-synthesis.json", prefix)
        )

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

    def test_test_briefing_does_not_block_synthesis(self) -> None:
        from detect_synthesis_trigger import evaluate_type

        date_str = "2099-06-05"
        synthesis = REPO_ROOT / f"inbox/news/{date_str}-synthesis.json"
        test_briefing = REPO_ROOT / f"briefings/news/{date_str}.test.md"
        synthesis.parent.mkdir(parents=True, exist_ok=True)
        test_briefing.parent.mkdir(parents=True, exist_ok=True)
        synthesis.write_text('{"built_at":"2099-06-05T10:00:00Z"}', encoding="utf-8")
        test_briefing.write_text("# sandbox\n", encoding="utf-8")

        try:
            bt = load_briefing_type("news")
            self.assertFalse(production_briefing_exists(bt, date_str))
            should_run, reason, _ = evaluate_type(
                "news",
                commit_sha="deadbeef",
                subject=f"inbox/news: {date_str} research pre-fetch",
                changed=[f"inbox/news/{date_str}-synthesis.json"],
            )
            self.assertTrue(should_run, reason)
        finally:
            synthesis.unlink(missing_ok=True)
            test_briefing.unlink(missing_ok=True)

    def test_detect_trigger_surfaces_briefing_exists_reason(self) -> None:
        from unittest.mock import patch

        from detect_synthesis_trigger import detect_trigger

        date_str = "2099-06-04"
        synthesis = REPO_ROOT / f"inbox/berlin-culture/{date_str}-synthesis.json"
        briefing = REPO_ROOT / f"briefings/berlin-culture/{date_str}.md"
        synthesis.parent.mkdir(parents=True, exist_ok=True)
        briefing.parent.mkdir(parents=True, exist_ok=True)
        synthesis.write_text('{"built_at":"2099-06-04T10:00:00Z"}', encoding="utf-8")
        briefing.write_text("# test\n", encoding="utf-8")

        try:
            with (
                patch("detect_synthesis_trigger.resolve_commit_sha", return_value="abc123"),
                patch(
                    "detect_synthesis_trigger.commit_subject",
                    return_value=f"inbox/berlin-culture: {date_str} research pre-fetch",
                ),
                patch(
                    "detect_synthesis_trigger.changed_files_in_commit",
                    return_value=[f"inbox/berlin-culture/{date_str}-synthesis.json"],
                ),
            ):
                decision = detect_trigger("abc123")
            self.assertIsNone(decision.type_id)
            self.assertIn(f"Briefing already exists for {date_str}", decision.reason)
            self.assertIn("berlin-culture", decision.reason)
            self.assertTrue(decision.matched_files)
        finally:
            synthesis.unlink(missing_ok=True)
            briefing.unlink(missing_ok=True)

    def test_best_skip_rejection_prefers_briefing_exists(self) -> None:
        reason, matched = _best_skip_rejection(
            [
                (
                    "news",
                    "No news inbox research in commit",
                    (),
                ),
                (
                    "berlin-culture",
                    "Briefing already exists for 2026-06-09",
                    ("inbox/berlin-culture/2026-06-09-synthesis.json",),
                ),
            ]
        )
        self.assertEqual(reason, "berlin-culture: Briefing already exists for 2026-06-09")
        self.assertEqual(len(matched), 1)

    def test_smoke_reuses_latest_inbox_even_if_briefing_exists(self) -> None:
        date_str = "2099-06-07"
        synthesis = REPO_ROOT / f"inbox/news/{date_str}-synthesis.json"
        briefing = REPO_ROOT / f"briefings/news/{date_str}.md"
        synthesis.parent.mkdir(parents=True, exist_ok=True)
        briefing.parent.mkdir(parents=True, exist_ok=True)
        synthesis.write_text('{"built_at":"2099-06-07T10:00:00Z"}', encoding="utf-8")
        briefing.write_text("# production\n", encoding="utf-8")
        try:
            self.assertEqual(
                inbox_research_files_for_date("news", date_str),
                [f"inbox/news/{date_str}-synthesis.json"],
            )
            decision = detect_smoke_trigger("news", date_str)
            self.assertEqual(decision.type_id, "news")
            self.assertIn("smoke:", decision.reason)
            self.assertIn(f"inbox/news/{date_str}-synthesis.json", decision.matched_files)
        finally:
            synthesis.unlink(missing_ok=True)
            briefing.unlink(missing_ok=True)

    def test_smoke_unknown_type(self) -> None:
        decision = detect_smoke_trigger("not-a-type")
        self.assertIsNone(decision.type_id)
        self.assertIn("Unknown type_id", decision.reason)

    def test_latest_inbox_date_finds_news(self) -> None:
        latest = latest_inbox_date("news")
        self.assertIsNotNone(latest)
        self.assertRegex(latest or "", r"^\d{4}-\d{2}-\d{2}$")

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
