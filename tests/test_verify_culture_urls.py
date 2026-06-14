#!/usr/bin/env python3
"""Tests for verify_culture_urls CLI."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_culture_urls  # noqa: E402


class TestVerifyCultureUrlsCli(unittest.TestCase):
    def test_warns_on_dead_urls_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox" / "berlin-culture"
            inbox.mkdir(parents=True)
            raw_path = inbox / "2026-06-16-raw.json"
            raw_path.write_text(
                json.dumps(
                    {
                        "date": "2026-06-16",
                        "items": [
                            {
                                "ingestion_source": "openai",
                                "official_url": "https://example.com/dead",
                                "topic_ids": ["film"],
                                "dates": "12 June 2026",
                                "times": "20:00",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            class FakeBriefing:
                inbox_dir = inbox

            with patch.object(
                verify_culture_urls, "load_briefing_type", return_value=FakeBriefing()
            ), patch(
                "culture_url_verify.check_url_live",
                return_value=(False, "HTTP 404"),
            ), patch.object(
                sys,
                "argv",
                ["verify_culture_urls.py", "--date", "2026-06-16"],
            ):
                code = verify_culture_urls.main()

            self.assertEqual(code, 0)
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            self.assertFalse(payload["items"][0]["verified"])


if __name__ == "__main__":
    unittest.main()
