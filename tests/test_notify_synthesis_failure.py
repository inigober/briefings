import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from notify_synthesis_failure import build_message  # noqa: E402


class BuildMessageTests(unittest.TestCase):
    def test_subject_and_escaping(self):
        subject, body = build_message("news", "2026-10-21", "<b>x</b>", "https://example.com/run/1")
        self.assertEqual(subject, "[Briefing] Synthesis failed — news 2026-10-21")
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", body)
        self.assertIn("https://example.com/run/1", body)

    def test_unknown_type(self):
        subject, _ = build_message("", "", "", "")
        self.assertEqual(subject, "[Briefing] Synthesis failed — unknown")


if __name__ == "__main__":
    unittest.main()
