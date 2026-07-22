from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from scripts.news_relevance import (
    dedup_matches,
    item_theme_keys,
    load_dedup_entries,
    relevance_cfg,
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


def test_load_dedup_entries_respects_lookback_window() -> None:
    dedup_file = REPO_ROOT / "state/news/dedup_index.md"
    entries = load_dedup_entries(
        dedup_file,
        reference_date=date(2026, 6, 17),
        lookback_days=7,
    )
    assert entries
    assert all((date(2026, 6, 17) - date.fromisoformat(entry["date"])).days <= 7 for entry in entries)
