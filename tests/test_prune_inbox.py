import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from prune_inbox import prunable_files  # noqa: E402

TODAY = date(2026, 10, 20)


class PruneInboxTests(unittest.TestCase):
    def _make(self, names: list[str]) -> Path:
        tmp = Path(tempfile.mkdtemp())
        for name in names:
            (tmp / name).write_text("{}", encoding="utf-8")
        return tmp

    def test_removes_old_intermediates_only(self) -> None:
        inbox = self._make(
            [
                "2026-06-01-raw.json",
                "2026-06-01-rss.json",
                "2026-06-01-wordpress.json",
                "2026-06-01-html-calendars.json",
                "2026-06-01-raw.error.txt",
                "2026-06-01-synthesis.json",
                "2026-06-01-spend.json",
                "2026-06-01-context.json",
                "2026-06-01-taste-snapshot.md",
                ".gitkeep",
            ]
        )
        names = {p.name for p in prunable_files(inbox, today=TODAY, keep_days=60)}
        self.assertEqual(
            names,
            {
                "2026-06-01-raw.json",
                "2026-06-01-rss.json",
                "2026-06-01-wordpress.json",
                "2026-06-01-html-calendars.json",
                "2026-06-01-raw.error.txt",
            },
        )

    def test_keeps_recent_files_and_the_cutoff_day(self) -> None:
        inbox = self._make(
            [
                "2026-10-19-raw.json",  # yesterday
                "2026-08-21-raw.json",  # exactly 60 days old: kept
                "2026-08-20-raw.json",  # 61 days old: pruned
            ]
        )
        names = {p.name for p in prunable_files(inbox, today=TODAY, keep_days=60)}
        self.assertEqual(names, {"2026-08-20-raw.json"})

    def test_missing_directory_is_fine(self) -> None:
        self.assertEqual(prunable_files(Path("/nonexistent/inbox"), today=TODAY, keep_days=60), [])


if __name__ == "__main__":
    unittest.main()
