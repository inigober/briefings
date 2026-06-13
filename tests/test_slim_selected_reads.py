from __future__ import annotations

from datetime import date

from scripts.slim_inbox_for_synthesis import (
    item_is_fresh_enough,
    pick_diversified_selected_reads,
    selected_reads_max_age_days,
)


def _item(
    *,
    publisher: str,
    url: str,
    published_at: str,
    headline: str = "Headline",
) -> dict:
    return {
        "id": url,
        "headline": headline,
        "summary": "",
        "ingestion_source": "rss",
        "material_development": True,
        "sources": [
            {
                "publisher": publisher,
                "url": url,
                "published_at": published_at,
            }
        ],
    }


SOURCES_CFG = {
    "long_form_features": ["theguardian.com", "ft.com"],
    "think_tanks": ["ifo.de"],
    "specialist_publications": ["restofworld.org", "foreignpolicy.com"],
    "news_analysis": ["politico.eu", "bloomberg.com"],
    "selected_reads_max_age_days": 30,
    "selected_reads_max_per_publisher": 2,
}


def test_selected_reads_max_age_days_defaults_to_30() -> None:
    assert selected_reads_max_age_days({}) == 30


def test_item_is_fresh_enough_rejects_articles_older_than_one_month() -> None:
    item = _item(
        publisher="Bloomberg",
        url="https://www.bloomberg.com/news/articles/2024-06-07/stale",
        published_at="2024-06-07",
    )
    assert not item_is_fresh_enough(
        item,
        reference_date=date(2026, 6, 13),
        max_age_days=30,
    )


def test_pick_diversified_selected_reads_limits_publishers_and_categories() -> None:
    items = [
        _item(
            publisher="The Guardian",
            url="https://www.theguardian.com/world/2026/jun/13/a",
            published_at="2026-06-13",
            headline="Guardian A",
        ),
        _item(
            publisher="The Guardian",
            url="https://www.theguardian.com/world/2026/jun/13/b",
            published_at="2026-06-13",
            headline="Guardian B",
        ),
        _item(
            publisher="The Guardian",
            url="https://www.theguardian.com/world/2026/jun/13/c",
            published_at="2026-06-13",
            headline="Guardian C",
        ),
        _item(
            publisher="Rest of World",
            url="https://restofworld.org/2026/spacex-ipo/",
            published_at="2026-06-12",
            headline="Rest of World feature",
        ),
        _item(
            publisher="Foreign Policy",
            url="https://foreignpolicy.com/2026/06/12/analysis/",
            published_at="2026-06-12",
            headline="Foreign Policy analysis",
        ),
        _item(
            publisher="Financial Times",
            url="https://www.ft.com/content/abc123",
            published_at="2026-06-12",
            headline="FT long-form",
        ),
        _item(
            publisher="Politico Europe",
            url="https://www.politico.eu/article/example/",
            published_at="2026-06-12",
            headline="Politico report",
        ),
        _item(
            publisher="Bloomberg",
            url="https://www.bloomberg.com/news/articles/2024-06-07/stale",
            published_at="2024-06-07",
            headline="Stale Bloomberg",
        ),
    ]

    picked = pick_diversified_selected_reads(
        items,
        8,
        SOURCES_CFG,
        reference_date=date(2026, 6, 13),
    )
    publishers = [item["sources"][0]["publisher"] for item in picked]

    assert len(picked) >= 5
    assert len(set(publishers)) >= 4
    assert publishers.count("The Guardian") <= 2
    assert "Rest of World" in publishers
    assert "Bloomberg" not in publishers
