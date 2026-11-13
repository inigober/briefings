#!/usr/bin/env python3
"""Tests for music-discovery OpenAI research pre-fetch helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_music_research import (  # noqa: E402
    MUSIC_MIN_BANDCAMP_URLS,
    MUSIC_MIN_UNIQUE_LABELS,
    MUSIC_SEARCH_MIN_CALLS,
    attach_bandcamp_urls,
    build_label_recovery_prompt,
    build_search_phase_prompt,
    build_search_recovery_prompt,
    build_structure_phase_prompt,
    clear_redundant_dig,
    compact_skip_list,
    enrich_candidate,
    extract_bandcamp_urls,
    is_bandcamp_listen_url,
    keys_match,
    needs_label_recovery,
    needs_search_recovery,
    normalize_candidate_url,
    release_key,
    salvage_bandcamp_url,
    section_counts,
    unique_label_count,
    unique_label_names,
    urls_are_same_page,
)
from fetch_openai_research import load_yaml  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestMusicResearchHelpers(unittest.TestCase):
    def setUp(self) -> None:
        self.sources_cfg = load_yaml(REPO_ROOT / "config/briefings/music-discovery/sources.yaml")
        self.taste = {
            "snapshot": "## Recent taste\n- Spray, Floorplan\n",
            "skip_lines": ["Roza Terenzi — Ministry of Wish (recommended)"],
            "known_label_lines": ["Radiant Love (70)"],
            "recent_taste_block": "Rekordbox artists: Spray",
            "releases_index": ["Papa Nugs — Move It Or Lose It EP"],
            "library_albums": [],
            "context": {},
            "known_label_threshold": 15,
        }

    def test_prompt_recent_window_follows_briefing_year(self) -> None:
        prompt = build_search_phase_prompt(
            date_str="2027-03-05",
            taste=self.taste,
            search_domains=self.sources_cfg.get("allowed_domains") or [],
        )
        self.assertIn("recent (2025–2027)", prompt)
        self.assertNotIn("2024–2026", prompt)

    def test_prompt_requires_web_search_and_forbids_invented_urls(self) -> None:
        prompt = build_search_phase_prompt(
            date_str="2026-08-14",
            taste=self.taste,
            search_domains=self.sources_cfg.get("allowed_domains") or [],
        )
        self.assertIn("PHASE 1", prompt)
        self.assertIn("web_search REQUIRED", prompt)
        self.assertIn(f"minimum {MUSIC_SEARCH_MIN_CALLS}", prompt)
        self.assertIn("never invent slugs", prompt.lower())
        self.assertIn("Roza Terenzi", prompt)
        self.assertIn("Radiant Love", prompt)
        self.assertIn("bandcamp.com", prompt)
        self.assertIn("Bandcamp:", prompt)
        self.assertIn("skip that release", prompt.lower())
        self.assertIn("/album/", prompt)
        self.assertIn(str(MUSIC_MIN_BANDCAMP_URLS), prompt)
        self.assertIn(str(MUSIC_MIN_UNIQUE_LABELS), prompt)
        self.assertIn("distinct labels", prompt)
        self.assertIn("at most two releases", prompt.lower())
        self.assertIn("Never copy this release", prompt)
        self.assertIn("dig_sentence", prompt)
        self.assertIn("why_candidate", prompt)
        self.assertIn("artist", prompt.lower())
        self.assertIn("label", prompt.lower())
        self.assertNotIn("Return JSON", prompt)

    def test_keys_match_fuzzy_release(self) -> None:
        self.assertTrue(
            keys_match(release_key("Air", "Moon Safari"), release_key("Air", "Moon Safari"))
        )
        self.assertTrue(
            keys_match(
                release_key("Papa Nugs", "Move It Or Lose It"),
                release_key("Papa Nugs", "Move It Or Lose It EP"),
            )
        )
        self.assertFalse(
            keys_match(release_key("Air", "Moon Safari"), release_key("Spray", "Moon Safari"))
        )

    def test_enrich_drops_skip_and_demotes_known_label(self) -> None:
        skip = [{"artist": "Roza Terenzi", "release": "Ministry of Wish"}]
        known = [{"name": "Radiant Love", "tracks": 70}]
        blocked = enrich_candidate(
            {
                "topic_ids": ["featured"],
                "artist": "Roza Terenzi",
                "release": "Ministry of Wish",
                "label": "Somewhere",
            },
            known_labels=known,
            threshold=15,
            skip_list=skip,
            library_albums=[],
            recent_releases=[],
        )
        self.assertEqual(blocked["blocked_reason"], "skip_list")

        demoted = enrich_candidate(
            {
                "topic_ids": ["featured"],
                "artist": "Someone",
                "release": "New EP",
                "label": "Radiant Love",
                "writeup_url": None,
            },
            known_labels=known,
            threshold=15,
            skip_list=[],
            library_albums=[],
            recent_releases=[],
        )
        self.assertTrue(demoted["known_label"])
        self.assertEqual(demoted["topic_ids"][0], "more_listening")

    def test_compact_skip_list(self) -> None:
        lines = compact_skip_list(
            [{"artist": "A", "release": "B", "status": "owned"}]
        )
        self.assertEqual(lines, ["A — B (owned)"])

    def test_section_counts(self) -> None:
        items = [
            {"topic_ids": ["featured"], "mode": "club"},
            {"topic_ids": ["featured"], "mode": "home"},
            {"topic_ids": ["more_listening"], "mode": "club"},
        ]
        counts = section_counts(items)
        self.assertEqual(counts["featured"], 2)
        self.assertEqual(counts["more_listening"], 1)
        self.assertEqual(counts["club"], 2)
        self.assertEqual(counts["home"], 1)

    def test_sources_include_bandcamp_and_writeups(self) -> None:
        domains = self.sources_cfg.get("allowed_domains") or []
        self.assertIn("bandcamp.com", domains)
        self.assertIn("ra.co", domains)
        self.assertIn("youtube.com", domains)


class TestSearchRecovery(unittest.TestCase):
    def test_needs_recovery_when_too_few_album_urls(self) -> None:
        thin = "Artist: A\nRelease: B\nBandcamp: https://a.bandcamp.com/album/b\n"
        self.assertTrue(needs_search_recovery(thin))
        many = "\n".join(
            f"Bandcamp: https://x{i}.bandcamp.com/album/r{i}" for i in range(12)
        )
        self.assertFalse(needs_search_recovery(many))

    def test_recovery_prompt_asks_for_more_album_urls(self) -> None:
        prompt = build_search_recovery_prompt(
            date_str="2026-09-11",
            previous_notes="Artist: Only\nBandcamp: https://only.bandcamp.com/album/one\n",
            have_urls=["https://only.bandcamp.com/album/one"],
            search_domains=["bandcamp.com", "ra.co"],
        )
        self.assertIn("PHASE 1 recovery", prompt)
        self.assertIn("2026-09-11", prompt)
        self.assertIn("https://only.bandcamp.com/album/one", prompt)
        self.assertIn(f"at least {MUSIC_MIN_BANDCAMP_URLS}", prompt)
        self.assertIn(f"minimum {MUSIC_SEARCH_MIN_CALLS}", prompt)
        self.assertIn("never invent slugs", prompt.lower())
        self.assertIn("bandcamp.com", prompt)
        self.assertIn("new labels", prompt.lower())


class TestUniqueLabels(unittest.TestCase):
    def test_counts_distinct_normalized_labels(self) -> None:
        items = [
            {"label": "Paranoid London"},
            {"label": "paranoid london"},
            {"label": "Incienso"},
            {"label": ""},
            {"label": "Balearic"},
        ]
        self.assertEqual(unique_label_count(items), 3)
        self.assertEqual(unique_label_names(items), ["Paranoid London", "Incienso", "Balearic"])
        self.assertTrue(needs_label_recovery(items))
        diverse = [{"label": f"Label {i}"} for i in range(MUSIC_MIN_UNIQUE_LABELS)]
        self.assertFalse(needs_label_recovery(diverse))

    def test_label_recovery_prompt_lists_used_imprints(self) -> None:
        prompt = build_label_recovery_prompt(
            date_str="2026-10-02",
            previous_notes="Artist: Paranoid London\nBandcamp: https://pl.bandcamp.com/album/x\n",
            have_labels=["Paranoid London", "Balearic"],
            have_urls=["https://pl.bandcamp.com/album/x"],
            search_domains=["bandcamp.com", "ra.co"],
        )
        self.assertIn("PHASE 1 label recovery", prompt)
        self.assertIn("Paranoid London", prompt)
        self.assertIn("Balearic", prompt)
        self.assertIn(str(MUSIC_MIN_UNIQUE_LABELS), prompt)
        self.assertIn("new labels", prompt.lower())
        self.assertIn("never invent slugs", prompt.lower())


class TestBandcampUrlSalvage(unittest.TestCase):
    NOTES = """
Artist: Maara
Release: Revenge from the Penthouse
Bandcamp: https://maara.bandcamp.com/album/revenge-from-the-penthouse

Artist: Black Sites
Release: R4
https://blacksites.bandcamp.com/album/r4

Daily write-up: https://daily.bandcamp.com/best-electronic/something
"""

    def test_listen_url_requires_artist_subdomain_album_path(self) -> None:
        self.assertTrue(
            is_bandcamp_listen_url("https://maara.bandcamp.com/album/revenge-from-the-penthouse")
        )
        self.assertFalse(is_bandcamp_listen_url(""))
        self.assertFalse(is_bandcamp_listen_url("https://daily.bandcamp.com/best-electronic/x"))
        self.assertFalse(is_bandcamp_listen_url("https://bandcamp.com/album/nope"))

    def test_normalize_strips_markdown(self) -> None:
        self.assertEqual(
            normalize_candidate_url("[Bandcamp](https://x.bandcamp.com/album/y)"),
            "https://x.bandcamp.com/album/y",
        )

    def test_extract_skips_daily(self) -> None:
        urls = extract_bandcamp_urls(self.NOTES)
        self.assertEqual(
            urls,
            [
                "https://maara.bandcamp.com/album/revenge-from-the-penthouse",
                "https://blacksites.bandcamp.com/album/r4",
            ],
        )

    def test_salvage_matches_slug_and_nearby_artist(self) -> None:
        used: set[str] = set()
        self.assertEqual(
            salvage_bandcamp_url("Maara", "Revenge from the Penthouse", self.NOTES, used=used),
            "https://maara.bandcamp.com/album/revenge-from-the-penthouse",
        )
        used.add("https://maara.bandcamp.com/album/revenge-from-the-penthouse")
        self.assertEqual(
            salvage_bandcamp_url("Black Sites", "R4", self.NOTES, used=used),
            "https://blacksites.bandcamp.com/album/r4",
        )

    def test_attach_fills_from_notes_and_dig_url(self) -> None:
        items = [
            {"artist": "Maara", "release": "Revenge from the Penthouse", "bandcamp_url": ""},
            {
                "artist": "Other",
                "release": "EP",
                "bandcamp_url": "",
                "dig_url": "https://other.bandcamp.com/album/ep",
            },
            {
                "artist": "Has One",
                "release": "Yes",
                "bandcamp_url": "https://has.bandcamp.com/album/yes",
            },
        ]
        salvaged = attach_bandcamp_urls(items, self.NOTES)
        self.assertEqual(salvaged, 2)
        self.assertEqual(
            items[0]["bandcamp_url"],
            "https://maara.bandcamp.com/album/revenge-from-the-penthouse",
        )
        self.assertEqual(items[1]["bandcamp_url"], "https://other.bandcamp.com/album/ep")
        self.assertEqual(items[2]["bandcamp_url"], "https://has.bandcamp.com/album/yes")

    def test_structure_prompt_forbids_self_dig(self) -> None:
        prompt = build_structure_phase_prompt(
            date_str="2026-08-14",
            research_notes="Artist: X\nBandcamp: https://x.bandcamp.com/album/y",
        )
        self.assertIn("different page from bandcamp_url", prompt)
        self.assertIn("artist and the label", prompt)
        self.assertIn("dig_sentence", prompt)
        self.assertIn("why_candidate", prompt)
        self.assertIn("another `/album/`", prompt)
        self.assertIn("unique labels", prompt)

    def test_clear_redundant_dig_blanks_self_and_empty(self) -> None:
        album = "https://label.bandcamp.com/album/same"
        self.assertTrue(urls_are_same_page(album, album + "/"))
        same = {
            "bandcamp_url": album,
            "dig_url": album + "/",
            "dig_sentence": "Stay with this album.",
        }
        self.assertTrue(clear_redundant_dig(same))
        self.assertEqual(same["dig_url"], "")
        self.assertEqual(same["dig_sentence"], "")

        distinct = {
            "bandcamp_url": album,
            "dig_url": "https://label.bandcamp.com/",
            "dig_sentence": "Browse the rest of the catalogue.",
        }
        self.assertFalse(clear_redundant_dig(distinct))
        self.assertEqual(distinct["dig_url"], "https://label.bandcamp.com/")

        empty = {"bandcamp_url": album, "dig_url": "", "dig_sentence": "Invented."}
        self.assertTrue(clear_redundant_dig(empty))
        self.assertEqual(empty["dig_sentence"], "")


if __name__ == "__main__":
    unittest.main()


class TestFilteredRecovery(unittest.TestCase):
    """2026-11-13 abort: 17 candidates, 12 owned/skipped/repeats, 5 left (need 10)."""

    @staticmethod
    def _item(n: int) -> dict:
        return {
            "topic_ids": ["featured"],
            "artist": f"Artist {n}",
            "release": f"Release {n}",
            "label": f"Label {n}",
            "bandcamp_url": f"https://label{n}.bandcamp.com/album/release-{n}",
        }

    def _taste(self, owned: range) -> dict:
        return {
            "releases_index": [],
            "library_albums": [
                {"artist": f"Artist {n}", "release": f"Release {n}"} for n in owned
            ],
            "context": {"skip_list": [], "known_labels": []},
            "known_label_threshold": 15,
        }

    def test_keep_reports_dropped_rows(self) -> None:
        from fetch_music_research import keep_music_candidates

        dropped: list[dict] = []
        kept, count, missing = keep_music_candidates(
            [self._item(n) for n in range(3)],
            notes="",
            taste=self._taste(range(2)),
            dropped_out=dropped,
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(count, 2)
        self.assertEqual(missing, 0)
        self.assertEqual({d["blocked_reason"] for d in dropped}, {"library_skip"})

    def test_prompt_lists_rejected_and_kept_releases(self) -> None:
        from fetch_music_research import build_filtered_recovery_prompt

        prompt = build_filtered_recovery_prompt(
            date_str="2026-11-13",
            kept=[self._item(1)],
            dropped=[dict(self._item(2), blocked_reason="library_skip")],
            search_domains=["bandcamp.com"],
        )
        self.assertIn("Artist 2 — Release 2 (library_skip)", prompt)
        self.assertIn("Artist 1 — Release 1", prompt)
        self.assertIn(f"at least {MUSIC_MIN_BANDCAMP_URLS - 1} more", prompt)
        self.assertIn("Never invent slugs", prompt)

    def test_fetch_all_runs_recovery_instead_of_aborting(self) -> None:
        from unittest import mock

        import fetch_music_research as fmr

        first = [self._item(n) for n in range(17)]  # 0-11 owned → 5 kept
        second = first + [self._item(n) for n in range(100, 106)]  # +6 new → 11 kept
        structured = iter([{"items": first}, {"items": second}])
        search_prompts: list[str] = []

        def fake_search(**kwargs):
            search_prompts.append(kwargs["prompt"])
            return "notes", object()

        with mock.patch.object(fmr, "make_client", return_value=object()), mock.patch.object(
            fmr, "fetch_web_research", side_effect=fake_search
        ), mock.patch.object(
            fmr, "count_web_search_calls", return_value=MUSIC_SEARCH_MIN_CALLS
        ), mock.patch.object(
            fmr, "extract_bandcamp_urls", return_value=[f"u{n}" for n in range(24)]
        ), mock.patch.object(
            fmr, "collect_response_urls", return_value=[]
        ), mock.patch.object(
            fmr, "fetch_structured", side_effect=lambda **_: (next(structured), object())
        ), mock.patch.object(
            fmr, "build_search_phase_prompt", return_value="phase 1 prompt"
        ), mock.patch.object(fmr, "log"):
            result = fmr.fetch_all_music(
                date_str="2026-11-13",
                model="test-model",
                taste=self._taste(range(12)),
                sources_cfg={"allowed_domains": ["bandcamp.com"]},
            )

        self.assertEqual(len(search_prompts), 2)
        self.assertIn("PHASE 1 filtered recovery", search_prompts[1])
        self.assertIn("Artist 0 — Release 0 (library_skip)", search_prompts[1])
        self.assertEqual(len(result["items"]), 11)

    def test_fetch_all_still_aborts_when_recovery_is_not_enough(self) -> None:
        from unittest import mock

        import fetch_music_research as fmr

        first = [self._item(n) for n in range(17)]
        structured = iter([{"items": first}, {"items": first}])
        with mock.patch.object(fmr, "make_client", return_value=object()), mock.patch.object(
            fmr, "fetch_web_research", return_value=("notes", object())
        ), mock.patch.object(
            fmr, "count_web_search_calls", return_value=MUSIC_SEARCH_MIN_CALLS
        ), mock.patch.object(
            fmr, "extract_bandcamp_urls", return_value=[f"u{n}" for n in range(24)]
        ), mock.patch.object(
            fmr, "collect_response_urls", return_value=[]
        ), mock.patch.object(
            fmr, "fetch_structured", side_effect=lambda **_: (next(structured), object())
        ), mock.patch.object(
            fmr, "build_search_phase_prompt", return_value="phase 1 prompt"
        ), mock.patch.object(fmr, "log"):
            with self.assertRaisesRegex(RuntimeError, "only 5 candidates"):
                fmr.fetch_all_music(
                    date_str="2026-11-13",
                    model="test-model",
                    taste=self._taste(range(12)),
                    sources_cfg={"allowed_domains": ["bandcamp.com"]},
                )


class TestReleasesIndex(unittest.TestCase):
    def test_exclude_date_skips_only_that_weeks_section(self) -> None:
        import tempfile

        from fetch_music_research import load_releases_index

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "releases_index.md").write_text(
                "# Music discovery — releases index\n\n"
                "Append `artist — release` after each run.\n\n"
                "## 2026-11-13\n\n- Cromby — Life and Death\n\n"
                "## 2026-11-06\n\n- Boulderhead — Dancing Rain\n",
                encoding="utf-8",
            )
            self.assertEqual(
                load_releases_index(Path(tmp)),
                ["Cromby — Life and Death", "Boulderhead — Dancing Rain"],
            )
            self.assertEqual(
                load_releases_index(Path(tmp), exclude_date="2026-11-13"),
                ["Boulderhead — Dancing Rain"],
            )
