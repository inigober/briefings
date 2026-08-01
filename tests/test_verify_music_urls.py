#!/usr/bin/env python3
"""Tests for music-discovery briefing URL extraction and HTTP verification."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import verify_music_urls  # noqa: E402
from verify_music_urls import (  # noqa: E402
    extract_music_briefing_urls,
    verify_music_briefing_urls,
)


SAMPLE_BRIEFING = """
# Music Discovery — Week of 2026-07-31

## Domenique Dumont — Deux Paradis — *Antinote* (2025)

![Album cover](https://f4.bcbits.com/img/a2736876091_10.jpg)

**Genre:** Balearic · **Listen:** <a href="https://antinoterecordings.bandcamp.com/album/deux-paradis"><img src="https://www.google.com/s2/favicons?domain=bandcamp.com&sz=32" width="16" height="16" alt=""> Bandcamp</a>

Context paragraph.

**Dig:** Step back to [*Comme Ça*](https://antinoterecordings.bandcamp.com/album/comme-a).

## More listening

- **Venda — Skeleton EP** (*Sounds Of Sirius*, 2025) — One sentence. <a href="https://soundsofsiriusmusic.bandcamp.com/album/sosnz005-venda-skeleton-ep"><img src="https://www.google.com/s2/favicons?domain=bandcamp.com&sz=32" width="16" height="16" alt=""> Bandcamp</a>
"""


class TestExtractMusicBriefingUrls(unittest.TestCase):
    def test_extracts_markdown_html_and_covers_skips_favicons(self) -> None:
        urls = extract_music_briefing_urls(SAMPLE_BRIEFING)
        self.assertEqual(
            urls,
            [
                "https://f4.bcbits.com/img/a2736876091_10.jpg",
                "https://antinoterecordings.bandcamp.com/album/deux-paradis",
                "https://antinoterecordings.bandcamp.com/album/comme-a",
                "https://soundsofsiriusmusic.bandcamp.com/album/sosnz005-venda-skeleton-ep",
            ],
        )
        self.assertTrue(all("favicon" not in u for u in urls))

    def test_dedupes_repeated_urls(self) -> None:
        text = """
[one](https://example.com/a) and again [one](https://example.com/a/)
<a href="https://example.com/a">same</a>
"""
        urls = extract_music_briefing_urls(text)
        self.assertEqual(urls, ["https://example.com/a"])


class TestVerifyMusicBriefingUrls(unittest.TestCase):
    def test_reports_dead_urls(self) -> None:
        urls = [
            "https://antinoterecordings.bandcamp.com/album/deux-paradis",
            "https://antinoterecordings.bandcamp.com/album/comme-a",
        ]

        def fake_live(url: str, *, session=None):  # noqa: ANN001
            if "comme-a" in url and "atn020" not in url:
                return False, "HTTP 404"
            return True, ""

        with patch("verify_music_urls.check_url_live", side_effect=fake_live):
            live, dead = verify_music_briefing_urls(urls, sleep_ms=0)

        self.assertEqual(live, [urls[0]])
        self.assertEqual(len(dead), 1)
        self.assertEqual(dead[0][0], urls[1])
        self.assertIn("404", dead[0][1])

    def test_cli_fails_on_dead_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-07-31.md"
            path.write_text(SAMPLE_BRIEFING, encoding="utf-8")

            def fake_live(url: str, *, session=None):  # noqa: ANN001
                if "comme-a" in url:
                    return False, "HTTP 404"
                return True, ""

            with (
                patch("verify_music_urls.check_url_live", side_effect=fake_live),
                patch.object(
                    sys,
                    "argv",
                    ["verify_music_urls.py", "--briefing", str(path), "--sleep-ms", "0"],
                ),
            ):
                code = verify_music_urls.main()

        self.assertEqual(code, 1)

    def test_cli_ok_when_all_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-07-31.md"
            path.write_text(
                "**Dig:** [ok](https://antinoterecordings.bandcamp.com/album/deux-paradis)\n",
                encoding="utf-8",
            )

            with (
                patch("verify_music_urls.check_url_live", return_value=(True, "")),
                patch.object(
                    sys,
                    "argv",
                    ["verify_music_urls.py", "--briefing", str(path), "--sleep-ms", "0"],
                ),
            ):
                code = verify_music_urls.main()

        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
