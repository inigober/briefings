#!/usr/bin/env python3
"""Tests for culture briefing Official Link HTTP verification."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_culture_briefing_urls  # noqa: E402
from verify_culture_briefing_urls import extract_official_link_urls  # noqa: E402

SAMPLE = """
## Top Picks

### Show A

**Venue:** Venue A

**Official Link:** [Show A](https://example.com/events/show-a)

### Show B

**Venue:** Venue B

**Official Link:** [Show B](https://example.com/programm/)
"""


class TestExtractOfficialLinks(unittest.TestCase):
    def test_extracts_official_links(self) -> None:
        urls = extract_official_link_urls(SAMPLE)
        self.assertEqual(
            urls,
            [
                "https://example.com/events/show-a",
                "https://example.com/programm/",
            ],
        )


class TestVerifyCultureBriefingUrlsCli(unittest.TestCase):
    def test_cli_fails_on_dead_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-07-28.md"
            path.write_text(SAMPLE, encoding="utf-8")

            def fake_live(url: str, *, session=None):  # noqa: ANN001
                if url.rstrip("/").endswith("/programm"):
                    return False, "HTTP 404"
                return True, ""

            with (
                patch("verify_culture_briefing_urls.check_url_live", side_effect=fake_live),
                patch.object(
                    sys,
                    "argv",
                    [
                        "verify_culture_briefing_urls.py",
                        "--briefing",
                        str(path),
                        "--sleep-ms",
                        "0",
                    ],
                ),
            ):
                code = verify_culture_briefing_urls.main()

        self.assertEqual(code, 1)

    def test_cli_fails_when_official_link_missing(self) -> None:
        text = """
## Exhibitions Radar

### Orphan Show

**Venue:** Somewhere

**Short Context:** No link here.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-07-28.md"
            path.write_text(text, encoding="utf-8")
            with patch.object(
                sys,
                "argv",
                ["verify_culture_briefing_urls.py", "--briefing", str(path), "--sleep-ms", "0"],
            ):
                code = verify_culture_briefing_urls.main()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
