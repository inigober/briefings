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
    assert_music_briefing_structure,
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

COMPLETE_BRIEFING = """# Music Discovery — Week of 2026-07-31

Intro sentence about the week.

## Artist One — Release One — *Label* (2025)

![Album cover](https://f4.bcbits.com/img/a1.jpg)

**Genre:** House · **Listen:** <a href="https://example.bandcamp.com/album/one">Bandcamp</a>

Context.

**Dig:** [next](https://example.bandcamp.com/album/dig1)

## Artist Two — Release Two — *Label Two* (2025)

![Album cover](https://f4.bcbits.com/img/a2.jpg)

**Genre:** Ambient · **Listen:** <a href="https://example.bandcamp.com/album/two">Bandcamp</a>

Context.

**Dig:** [next](https://example.bandcamp.com/album/dig2)

## Artist Three — Release Three — *Label Three* (2024)

![Album cover](https://f4.bcbits.com/img/a3.jpg)

**Genre:** Techno · **Listen:** <a href="https://example.bandcamp.com/album/three">Bandcamp</a>

Context.

**Dig:** [next](https://example.bandcamp.com/album/dig3)

## Artist Four — Release Four — *Label Four* (2023)

![Album cover](https://f4.bcbits.com/img/a4.jpg)

**Genre:** Balearic · **Listen:** <a href="https://example.bandcamp.com/album/four">Bandcamp</a>

Context.

**Dig:** [next](https://example.bandcamp.com/album/dig4)

## Artist Five — Release Five — *Label Five* (2025)

![Album cover](https://f4.bcbits.com/img/a5.jpg)

**Genre:** Electro · **Listen:** <a href="https://example.bandcamp.com/album/five">Bandcamp</a>

Context.

**Dig:** [next](https://example.bandcamp.com/album/dig5)

## Artist Six — Release Six — *Label Six* (2022)

![Album cover](https://f4.bcbits.com/img/a6.jpg)

**Genre:** Trance · **Listen:** <a href="https://example.bandcamp.com/album/six">Bandcamp</a>

Context.

**Dig:** [next](https://example.bandcamp.com/album/dig6)

## More listening

- **Extra One — A** (*L1*, 2025) — Sentence. <a href="https://example.bandcamp.com/album/e1">Bandcamp</a>
- **Extra Two — B** (*L2*, 2025) — Sentence. <a href="https://example.bandcamp.com/album/e2">Bandcamp</a>
- **Extra Three — C** (*L3*, 2024) — Sentence. <a href="https://example.bandcamp.com/album/e3">Bandcamp</a>
- **Extra Four — D** (*L4*, 2021) — Sentence. <a href="https://example.bandcamp.com/album/e4">Bandcamp</a>
"""

GAP_BRIEFING = """# Music Discovery — Week of 2026-08-14

This week's CI inbox only contains the taste-cache bridge.

## Selection note

No featured picks or More listening entries are published for this date.
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


class TestMusicBriefingStructure(unittest.TestCase):
    def test_complete_briefing_passes(self) -> None:
        self.assertEqual(assert_music_briefing_structure(COMPLETE_BRIEFING), [])

    def test_gap_briefing_fails(self) -> None:
        errors = assert_music_briefing_structure(GAP_BRIEFING)
        self.assertTrue(any("placeholder" in e or "featured" in e for e in errors))


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
            path.write_text(COMPLETE_BRIEFING, encoding="utf-8")

            def fake_live(url: str, *, session=None):  # noqa: ANN001
                if url.endswith("/album/two"):
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
            path.write_text(COMPLETE_BRIEFING, encoding="utf-8")

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


    def test_cli_fails_on_gap_briefing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-08-14.md"
            path.write_text(GAP_BRIEFING, encoding="utf-8")
            with patch.object(
                sys,
                "argv",
                ["verify_music_urls.py", "--briefing", str(path), "--sleep-ms", "0"],
            ):
                code = verify_music_urls.main()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
