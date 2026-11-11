from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from scripts.news_relevance import (
    dedup_matches,
    item_theme_keys,
    load_dedup_entries,
    relevance_cfg,
    running_stories_on_cooldown,
    score_editorial_relevance,
)
from scripts.slim_inbox_for_synthesis import build_news_synthesis_inbox, pick_top_news

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_CFG = yaml.safe_load(
    (REPO_ROOT / "config/briefings/news/sources.yaml").read_text(encoding="utf-8")
)
TOPICS_CFG = yaml.safe_load(
    (REPO_ROOT / "config/briefings/news/topics.yaml").read_text(encoding="utf-8")
)
SPAIN_TOPIC = next(topic for topic in TOPICS_CFG["topics"] if topic["id"] == "spain")


def _rss_item(
    *,
    headline: str,
    section: str = "spain",
    url: str = "https://elpais.com/espana/story.html",
    summary: str = "",
    publisher: str = "EL PAÍS",
) -> dict:
    return {
        "id": url,
        "topic_ids": [section],
        "headline": headline,
        "summary": summary,
        "ingestion_source": "rss",
        "material_development": True,
        "sources": [
            {
                "publisher": publisher,
                "url": url,
                "published_at": "2026-06-17",
            }
        ],
    }


def test_noise_patterns_reduce_editorial_score() -> None:
    noisy = _rss_item(headline="Fußball-WM: Messi mit Gala zum Klose-Rekord")
    clean = _rss_item(
        headline="Madrid hospital budget crisis deepens",
        summary="Regional health spending and infrastructure under pressure.",
    )
    noisy_score, noisy_notes = score_editorial_relevance(
        noisy,
        section_id="germany",
        topic_cfg=TOPICS_CFG["topics"][1],
        sources_cfg=SOURCES_CFG,
        dedup_entries=[],
    )
    clean_score, _ = score_editorial_relevance(
        clean,
        section_id="spain",
        topic_cfg=SPAIN_TOPIC,
        sources_cfg=SOURCES_CFG,
        dedup_entries=[],
    )
    assert noisy_score < clean_score
    assert any(note.startswith("noise:") for note in noisy_notes)


def test_avoid_unless_material_penalizes_without_material_trigger() -> None:
    item = _rss_item(
        headline="Housing protests continue across Spanish cities",
        summary="Tenants repeat demands as debate continues in parliament.",
    )
    score, notes = score_editorial_relevance(
        item,
        section_id="spain",
        topic_cfg=SPAIN_TOPIC,
        sources_cfg=SOURCES_CFG,
        dedup_entries=[],
    )
    assert score < 0
    assert any("avoid_unless_material" in note for note in notes)


def test_material_trigger_overrides_avoid_penalty() -> None:
    item = _rss_item(
        headline="Court ruling on housing protests reshapes rental law",
        summary="Judges issue major ruling after resignation of regional minister.",
    )
    score, notes = score_editorial_relevance(
        item,
        section_id="spain",
        topic_cfg=SPAIN_TOPIC,
        sources_cfg=SOURCES_CFG,
        dedup_entries=[],
    )
    assert score > 0
    assert any(note.startswith("material:") for note in notes)


def test_dedup_matches_recent_topic_slug_tokens() -> None:
    dedup_entries = [
        {
            "slug": "spain-zapatero-audiencia-nacional-appearance",
            "section": "spain",
            "tokens": ["zapatero", "audiencia", "nacional", "appearance"],
            "date": "2026-06-16",
        }
    ]
    item = _rss_item(
        headline="Zapatero appears before Audiencia Nacional judge",
        summary="Former prime minister testifies in Plus Ultra probe.",
    )
    assert dedup_matches(item, dedup_entries) == ["spain-zapatero-audiencia-nacional-appearance"]


def test_pick_top_news_enforces_one_theme_per_section() -> None:
    items = [
        _rss_item(
            headline="Radiografía de un cole achicharrado: más de 37 grados",
            summary="School classrooms over 37C in Madrid.",
        ),
        _rss_item(
            headline="Barcelona refrigerates 84 schools",
            summary="Tourism tax funds classroom air conditioning.",
            url="https://elpais.com/espana/catalunya/barcelona-schools.html",
        ),
        _rss_item(
            headline="Celebrity gossip roundup",
            summary="Soft news without structural keywords.",
            url="https://elpais.com/sociedad/gossip.html",
        ),
    ]
    picked, rejections = pick_top_news(
        items,
        2,
        section_id="spain",
        topic_cfg=SPAIN_TOPIC,
        sources_cfg=SOURCES_CFG,
        dedup_entries=[],
    )
    school_themes = {
        theme
        for item in picked
        for theme in item_theme_keys(item, relevance_cfg(SOURCES_CFG))
        if theme == "school_heat"
    }
    assert len(school_themes) <= 1
    assert any(rejection["reason"].startswith("theme_cap:school_heat") for rejection in rejections)


def test_pick_top_news_caps_per_publisher() -> None:
    items = [
        _rss_item(
            headline=f"eldiario story {i}",
            summary="Structural Spanish politics update with new legislation.",
            url=f"https://www.eldiario.es/politica/story-{i}.html",
            publisher="eldiario.es",
        )
        for i in range(8)
    ] + [
        _rss_item(
            headline="El País alternative angle",
            summary="Infrastructure fund unlocks new rail spending.",
            url="https://elpais.com/economia/rail.html",
            publisher="EL PAÍS",
        ),
        _rss_item(
            headline="La Vanguardia third outlet",
            summary="Catalonia housing reform advances in parliament.",
            url="https://www.lavanguardia.com/politica/housing.html",
            publisher="La Vanguardia",
        ),
    ]
    cfg = dict(SOURCES_CFG)
    cfg["news_relevance"] = {
        **(SOURCES_CFG.get("news_relevance") or {}),
        "section_max_per_publisher": 3,
    }
    picked, rejections = pick_top_news(
        items,
        6,
        section_id="spain",
        topic_cfg=SPAIN_TOPIC,
        sources_cfg=cfg,
        dedup_entries=[],
    )
    domains = [
        (item.get("sources") or [{}])[0].get("url", "")
        for item in picked
    ]
    eldiario_count = sum(1 for url in domains if "eldiario.es" in url)
    assert eldiario_count <= 3
    assert any("elpais.com" in url for url in domains)
    assert any(rejection["reason"].startswith("publisher_cap:") for rejection in rejections)


def test_build_news_synthesis_inbox_includes_editorial_context(tmp_path: Path) -> None:
    dedup_path = tmp_path / "dedup_index.md"
    dedup_path.write_text(
        "\n".join(
            [
                "## 2026-06-16",
                "- **spain-zapatero-audiencia-nacional-appearance** — Zapatero hearing",
            ]
        ),
        encoding="utf-8",
    )
    raw = {
        "date": "2026-06-17",
        "inbox_dir": "inbox/news",
        "items": [
            _rss_item(headline="Zapatero declara ante el juez"),
            _rss_item(
                headline="Infrastructure fund unlocks new rail spending",
                summary="Major investment in Spanish transport corridors.",
                url="https://elpais.com/economia/rail.html",
            ),
        ],
    }
    payload = build_news_synthesis_inbox(
        raw,
        sources_cfg=SOURCES_CFG,
        topics_cfg=TOPICS_CFG,
        dedup_path=dedup_path,
    )
    assert "editorial_context" in payload
    assert payload["editorial_context"]["recent_topics"]
    assert isinstance(payload["editorial_context"]["rejected_candidates"], list)
    assert all("relevance_score" in item for item in payload["items"])


def test_ceuta_running_story_cooldown_penalizes_repeat() -> None:
    item = _rss_item(
        headline="Prosecutors are investigating abuse in a Ceuta girls' shelter",
        summary="Minors-court file on a state-run shelter in Ceuta.",
    )
    recent = [
        {
            "slug": "spain-audiencia-nacional-ceuta-port-camp",
            "section": "spain",
            "tokens": ["audiencia", "nacional", "ceuta", "port", "camp"],
            "date": "2026-09-18",
        }
    ]
    cool_score, cool_notes = score_editorial_relevance(
        item,
        section_id="spain",
        topic_cfg=SPAIN_TOPIC,
        sources_cfg=SOURCES_CFG,
        dedup_entries=recent,
        reference_date=date(2026, 9, 19),
    )
    fresh_score, fresh_notes = score_editorial_relevance(
        item,
        section_id="spain",
        topic_cfg=SPAIN_TOPIC,
        sources_cfg=SOURCES_CFG,
        dedup_entries=[],
        reference_date=date(2026, 9, 19),
    )
    assert cool_score < fresh_score
    assert any("running_story:ceuta_enclave" in note for note in cool_notes)
    assert not any("running_story:ceuta_enclave:-" in note for note in fresh_notes)
    active = running_stories_on_cooldown(SPAIN_TOPIC, recent, date(2026, 9, 19))
    assert active and active[0]["id"] == "ceuta_enclave"
    assert active[0]["skip_until"] == "2026-09-21"


def test_ceuta_theme_cluster_caps_same_day() -> None:
    cfg = relevance_cfg(SOURCES_CFG)
    item = _rss_item(headline="Interior prepara centros en Ceuta y Melilla")
    assert "ceuta_enclave" in item_theme_keys(item, cfg)


def test_load_dedup_entries_respects_lookback_window() -> None:
    dedup_file = REPO_ROOT / "state/news/dedup_index.md"
    entries = load_dedup_entries(
        dedup_file,
        reference_date=date(2026, 6, 17),
        lookback_days=7,
    )
    assert entries
    assert all((date(2026, 6, 17) - date.fromisoformat(entry["date"])).days <= 7 for entry in entries)


import unittest


class TestCeutaRunningStory(unittest.TestCase):
    def test_cooldown_penalizes_repeat(self) -> None:
        test_ceuta_running_story_cooldown_penalizes_repeat()

    def test_theme_cluster_includes_ceuta(self) -> None:
        test_ceuta_theme_cluster_caps_same_day()


if __name__ == "__main__":
    unittest.main()


def _berlin_score(item: dict) -> tuple[int, list[str]]:
    berlin = next(topic for topic in TOPICS_CFG["topics"] if topic["id"] == "berlin")
    return score_editorial_relevance(
        item,
        section_id="berlin",
        topic_cfg=berlin,
        sources_cfg=SOURCES_CFG,
        dedup_entries=[],
    )


def test_sport_story_is_demoted() -> None:
    sport = _rss_item(
        headline="Hertha vor Pokalspiel: Ein seliger Trainer",
        section="berlin",
        url="https://www.rbb24.de/sport/beitrag/2026/10/fussball-dfb-pokal-hertha.html",
        publisher="rbb24",
    )
    other = _rss_item(
        headline="Redmann warnt vor Protesten am 31. Oktober",
        section="berlin",
        url="https://www.rbb24.de/politik/beitrag/2026/10/redmann-proteste.html",
        publisher="rbb24",
    )
    sport_score, sport_notes = _berlin_score(sport)
    other_score, _ = _berlin_score(other)
    assert sport_score <= other_score - 30
    assert "sport:-30" in sport_notes


def test_sport_with_geopolitical_angle_is_not_demoted() -> None:
    item = _rss_item(
        headline="Olympic boycott: governments weigh sanctions on Russian athletes",
        section="berlin",
        url="https://www.rbb24.de/sport/beitrag/2026/10/olympia-boykott.html",
        publisher="rbb24",
    )
    _, notes = _berlin_score(item)
    assert "sport:geopolitical_exempt" in notes
    assert not any(note.startswith("sport:-") for note in notes)


def test_transport_is_not_mistaken_for_sport() -> None:
    item = _rss_item(
        headline="BVG: Transport strike announced",
        section="berlin",
        url="https://www.rbb24.de/politik/beitrag/2026/10/bvg-streik.html",
        publisher="rbb24",
    )
    _, notes = _berlin_score(item)
    assert not any(note.startswith("sport") for note in notes)


BERLIN_TOPIC = next(topic for topic in TOPICS_CFG["topics"] if topic["id"] == "berlin")


def _berlin_score(item: dict) -> tuple[int, list[str]]:
    return score_editorial_relevance(
        item,
        section_id="berlin",
        topic_cfg=BERLIN_TOPIC,
        sources_cfg=SOURCES_CFG,
        dedup_entries=[],
        reference_date=date(2026, 6, 17),
    )


class BerlinLocalityTest(unittest.TestCase):
    """Berlin slice ranking (unittest-style so CI's `unittest discover` runs it)."""

    def test_berlin_locality_demotes_world_wire_copy_from_city_feed(self) -> None:
        local = _rss_item(
            section="berlin",
            headline="13 Jahre altes Mädchen aus Marzahn vermisst",
            url="https://www.rbb24.de/panorama/beitrag/2026/11/marzahn.html",
            publisher="rbb24",
        )
        world = _rss_item(
            section="berlin",
            headline="Starkregen in Gaza: 70.000 Zelte überflutet",
            url="https://www.berliner-zeitung.de/article/starkregen-in-gaza-10573786",
            publisher="Berliner Zeitung",
        )
        local_score, local_notes = _berlin_score(local)
        world_score, world_notes = _berlin_score(world)
        self.assertTrue(any(n.startswith("locality:+") for n in local_notes))
        self.assertTrue(any(n.startswith("locality_missing:") for n in world_notes))
        self.assertTrue(local_score - world_score >= 30)

    def test_berlin_off_area_headline_is_demoted_unless_berlin_named(self) -> None:
        brandenburg = _rss_item(
            section="berlin",
            headline="Potsdam: Blaulichtgottesdienst erinnert an Einsatzkräfte",
            url="https://www.tagesspiegel.de/berlin/dpa-potsdam-gottesdienst.html",
            publisher="Tagesspiegel",
        )
        shared = _rss_item(
            section="berlin",
            headline="Razzien in Berlin und Brandenburg: Ermittler finden Drogen",
            url="https://www.rbb24.de/panorama/razzia.html",
            publisher="rbb24",
        )
        _, brandenburg_notes = _berlin_score(brandenburg)
        _, shared_notes = _berlin_score(shared)
        self.assertTrue(any(n.startswith("off_area:") for n in brandenburg_notes))
        self.assertFalse(any(n.startswith("off_area:") for n in shared_notes))

    def test_berlin_locality_terms_do_not_match_inside_other_words(self) -> None:
        # "mitte" is deliberately not a term: it would match "Mittwoch".
        item = _rss_item(
            section="berlin",
            headline="Am Mittwoch beginnt die Tarifrunde",
            url="https://www.berliner-zeitung.de/article/tarifrunde-1.html",
        )
        _, notes = _berlin_score(item)
        self.assertTrue(any(n.startswith("locality_missing:") for n in notes))

    def test_berlin_stale_weekly_recap_is_demoted(self) -> None:
        fresh = _rss_item(section="berlin", headline="Berlin news", url="https://20percent.berlin/p/a")
        stale = _rss_item(section="berlin", headline="Berlin news", url="https://20percent.berlin/p/b")
        stale["sources"][0]["published_at"] = "2026-06-12"
        fresh_score, _ = _berlin_score(fresh)
        stale_score, stale_notes = _berlin_score(stale)
        self.assertTrue(any(n.startswith("stale:5d") for n in stale_notes))
        self.assertTrue(stale_score < fresh_score)

    def test_berlin_listings_are_demoted(self) -> None:
        news = _rss_item(section="berlin", headline="Schönhauser Allee bridge in Berlin to be demolished")
        listing = _rss_item(section="berlin", headline="What to do this weekend: Berlin's best events")
        news_score, _ = _berlin_score(news)
        listing_score, listing_notes = _berlin_score(listing)
        self.assertTrue(any(n.startswith("avoid_unless_material") for n in listing_notes))
        self.assertTrue(listing_score < news_score)

    def test_locality_is_inactive_for_sections_without_config(self) -> None:
        item = _rss_item(headline="Feijóo descarta coalición con Vox")
        _, notes = score_editorial_relevance(
            item,
            section_id="spain",
            topic_cfg=SPAIN_TOPIC,
            sources_cfg=SOURCES_CFG,
            dedup_entries=[],
            reference_date=date(2026, 6, 17),
        )
        self.assertFalse(any(n.startswith(("locality", "off_area", "stale")) for n in notes))


class SportPlaceNameTest(unittest.TestCase):
    """Place names such as "Sportforum" must not trigger the sport penalty."""

    def test_place_name_does_not_count_as_sport(self) -> None:
        item = _rss_item(
            section="berlin",
            headline="Massiver Gasaustritt unweit des Berliner Sportforums gestoppt",
            summary="Bei Bauarbeiten in Alt-Hohenschönhausen hat ein Bagger eine Gasleitung beschädigt.",
            url="https://www.tagesspiegel.de/berlin/gasaustritt-unweit-des-berliner-sportforums-gestoppt.html",
        )
        _, notes = _berlin_score(item)
        self.assertFalse(any(n.startswith("sport") for n in notes))

    def test_sport_story_at_a_sport_venue_is_still_sport(self) -> None:
        item = _rss_item(
            section="berlin",
            headline="Eisbären Berlin gewinnen im Sportforum",
            summary="Eishockey: klarer Heimsieg.",
            url="https://www.rbb24.de/sport/eisbaeren.html",
        )
        _, notes = _berlin_score(item)
        self.assertIn("sport:-30", notes)
