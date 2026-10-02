#!/usr/bin/env python3
"""Music synthesis-inbox slim should keep distinct labels first."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from slim_inbox_for_synthesis import pick_top_music  # noqa: E402


def _item(
    label: str,
    *,
    score_boost: bool = False,
    artist: str | None = None,
    release: str | None = None,
) -> dict:
    return {
        "verified": True,
        "label": label,
        "artist": artist or label,
        "release": release or f"{label} LP",
        "youtube_url": "https://music.youtube.com/playlist?list=x" if score_boost else None,
        "writeup_url": "https://ra.co/reviews/x" if score_boost else None,
        "reception_ok": True,
        "cover_url": "https://f4.bcbits.com/img/x.jpg",
        "bandcamp_url": f"https://{label.split()[0].lower()}.bandcamp.com/album/x",
    }


class TestPickTopMusicLabelDiversity(unittest.TestCase):
    def test_keeps_one_row_per_label_before_duplicates(self) -> None:
        items = [
            _item("Paranoid London", score_boost=True, release="7001"),
            _item("Paranoid London", release="7002"),
            _item("Paranoid London", release="Arseholes"),
            _item("Paranoid London", release="Vicious Games"),
            _item("Incienso", score_boost=True),
            _item("Balearic"),
            _item("Leo Zero Studio"),
        ]
        picked = pick_top_music(items, cap=4)
        labels = [row["label"] for row in picked]
        self.assertEqual(len(picked), 4)
        self.assertEqual(len(set(labels)), 4)
        self.assertIn("Paranoid London", labels)
        self.assertIn("Incienso", labels)
        self.assertIn("Balearic", labels)
        self.assertIn("Leo Zero Studio", labels)

    def test_fills_cap_with_duplicates_only_after_unique_pool(self) -> None:
        items = [
            _item("Paranoid London", score_boost=True, release="7001"),
            _item("Paranoid London", release="7002"),
            _item("Incienso"),
        ]
        picked = pick_top_music(items, cap=3)
        labels = [row["label"] for row in picked]
        self.assertEqual(len(picked), 3)
        self.assertEqual(labels.count("Paranoid London"), 2)
        self.assertEqual(labels.count("Incienso"), 1)
