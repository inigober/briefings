"""Editorial relevance scoring for news synthesis inbox slimming."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEDUP_LINE_RE = re.compile(r"^- \*\*(?P<slug>[^*]+)\*\*")
DEDUP_DATE_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})")

DEFAULT_RELEVANCE_CFG: dict[str, Any] = {
    "priority_keyword_boost": 6,
    "priority_keyword_cap": 24,
    "avoid_keyword_penalty": 18,
    "material_override_boost": 25,
    "not_material_penalty": 10,
    "noise_penalty": 40,
    "dedup_token_penalty": 15,
    "dedup_min_matching_tokens": 2,
    "dedup_lookback_days": 7,
    "publisher_priority_boost": 8,
    "audit_rank_multiplier": 2,
    "noise_title_patterns": [
        "fußball-wm",
        "fußball wm",
        "weltmeisterschaft",
        "wettervorhersage",
        "bilder des tages",
        "liveticker",
        "pressestimmen",
        "restaurant",
        "tennis open",
        "serena",
        "fotografie:",
        "militärmusik",
    ],
    "theme_cluster_keywords": {
        "school_heat": [
            "school",
            "classroom",
            "climatiz",
            "aula",
            "cole achicharr",
            "refrigerated",
            "air-condition",
        ],
        "zapatero_plus_ultra": [
            "zapatero",
            "plus ultra",
            "leire díez",
            "leire diez",
        ],
        "eu_institutions": [
            "von der leyen",
            "european commission",
            "brussels playbook",
            "kallas",
        ],
        "world_cup": [
            "world cup",
            "fußball-wm",
            "messi",
            "mbappé",
            "mbappe",
            "ronaldo",
            "seleccionador",
        ],
        "memorial_ceremony": [
            "mahnmal",
            "memorial",
            "gedenkt",
            "inaugurat",
        ],
        "paid_heritage_entry": [
            "eintrittsgeld",
            "paid entry",
            "admission fee",
        ],
        "obituary": [
            " dies ",
            "died aged",
            "dies at",
            "obituary",
            "muere a los",
            "fallece",
        ],
    },
}


def relevance_cfg(sources_cfg: dict) -> dict[str, Any]:
    merged = dict(DEFAULT_RELEVANCE_CFG)
    custom = sources_cfg.get("news_relevance") or {}
    merged.update(custom)
    if custom.get("theme_cluster_keywords"):
        themes = dict(DEFAULT_RELEVANCE_CFG["theme_cluster_keywords"])
        themes.update(custom["theme_cluster_keywords"])
        merged["theme_cluster_keywords"] = themes
    return merged


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def item_search_text(item: dict) -> str:
    parts = [item.get("headline") or "", item.get("summary") or ""]
    url = ""
    for src in item.get("sources") or []:
        url = src.get("url") or ""
        if url:
            break
    if url:
        parts.append(urlparse(url).path.replace("-", " ").replace("/", " "))
    return normalize_text(" ".join(parts))


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        if not isinstance(keyword, str):
            continue
        needle = normalize_text(keyword)
        if needle and needle in text:
            hits.append(keyword)
    return hits


def load_dedup_entries(
    dedup_path: Path,
    *,
    reference_date: date,
    lookback_days: int,
) -> list[dict]:
    if not dedup_path.is_file():
        return []

    entries: list[dict] = []
    current_date: date | None = None

    for line in dedup_path.read_text(encoding="utf-8").splitlines():
        date_match = DEDUP_DATE_RE.match(line.strip())
        if date_match:
            try:
                current_date = date.fromisoformat(date_match.group(1))
            except ValueError:
                current_date = None
            continue

        slug_match = DEDUP_LINE_RE.match(line.strip())
        if not slug_match or current_date is None:
            continue
        if (reference_date - current_date).days > lookback_days:
            continue

        slug = slug_match.group("slug").strip()
        parts = [part for part in slug.split("-") if part]
        section = parts[0] if parts else ""
        tokens = [part for part in parts[1:] if len(part) > 2]
        entries.append(
            {
                "slug": slug,
                "section": section,
                "tokens": tokens,
                "date": current_date.isoformat(),
            }
        )
    return entries


def item_theme_keys(item: dict, cfg: dict) -> list[str]:
    text = item_search_text(item)
    themes: list[str] = []
    for theme, patterns in (cfg.get("theme_cluster_keywords") or {}).items():
        if keyword_hits(text, patterns):
            themes.append(theme)
    return themes


def dedup_matches(item: dict, dedup_entries: list[dict]) -> list[str]:
    text = item_search_text(item)
    text_tokens = {token for token in re.split(r"[^a-z0-9]+", text) if len(token) > 2}
    matched: list[str] = []
    min_tokens = int(DEFAULT_RELEVANCE_CFG["dedup_min_matching_tokens"])

    for entry in dedup_entries:
        overlap = [token for token in entry["tokens"] if token in text_tokens]
        if len(overlap) >= min_tokens:
            matched.append(entry["slug"])
    return matched


def score_editorial_relevance(
    item: dict,
    *,
    section_id: str,
    topic_cfg: dict,
    sources_cfg: dict,
    dedup_entries: list[dict],
) -> tuple[int, list[str]]:
    """Return editorial score delta and human-readable scoring notes."""
    cfg = relevance_cfg(sources_cfg)
    text = item_search_text(item)
    score = 0
    notes: list[str] = []

    priority_hits = keyword_hits(text, topic_cfg.get("priority_categories") or [])
    if priority_hits:
        boost = min(
            len(priority_hits) * int(cfg["priority_keyword_boost"]),
            int(cfg["priority_keyword_cap"]),
        )
        score += boost
        notes.append(f"priority:+{boost}")

    material_hits = keyword_hits(text, topic_cfg.get("material_return_examples") or [])
    is_material = bool(material_hits)
    if is_material:
        score += int(cfg["material_override_boost"])
        notes.append(f"material:+{cfg['material_override_boost']}")

    avoid_hits = keyword_hits(text, topic_cfg.get("avoid_unless_material") or [])
    if avoid_hits and not is_material:
        penalty = len(avoid_hits) * int(cfg["avoid_keyword_penalty"])
        score -= penalty
        notes.append(f"avoid_unless_material:-{penalty}")

    not_material_hits = keyword_hits(text, topic_cfg.get("not_material") or [])
    if not_material_hits and not is_material:
        penalty = len(not_material_hits) * int(cfg["not_material_penalty"])
        score -= penalty
        notes.append(f"not_material:-{penalty}")

    noise_hits = keyword_hits(text, cfg.get("noise_title_patterns") or [])
    if noise_hits:
        score -= int(cfg["noise_penalty"])
        notes.append(f"noise:-{cfg['noise_penalty']}")

    dedup_slugs = dedup_matches(item, dedup_entries)
    if dedup_slugs and not is_material:
        penalty = len(dedup_slugs) * int(cfg["dedup_token_penalty"])
        score -= penalty
        notes.append(f"dedup:-{penalty} ({', '.join(dedup_slugs[:3])})")

    domain = ""
    for src in item.get("sources") or []:
        url = src.get("url") or ""
        if url.startswith("http"):
            domain = urlparse(url).netloc.lower().removeprefix("www.")
            break
    if domain:
        priorities = sources_cfg.get("source_priorities") or {}
        section_domains = priorities.get(section_id) or priorities.get("international") or []
        for index, preferred in enumerate(section_domains):
            if domain == preferred or domain.endswith(f".{preferred}"):
                boost = max(int(cfg["publisher_priority_boost"]) - index, 2)
                score += boost
                notes.append(f"publisher:+{boost}")
                break

    return score, notes


def score_news_item_with_context(
    item: dict,
    *,
    section_id: str,
    topic_cfg: dict,
    sources_cfg: dict,
    dedup_entries: list[dict],
) -> tuple[int, list[str]]:
    """Base ingest score plus editorial relevance for a section."""
    score = 0
    notes: list[str] = []
    source = item.get("ingestion_source") or "openai"
    url_live = item.get("url_live")

    if source in ("rss", "wordpress"):
        score += 35
        notes.append("feed:+35")
    elif url_live == "live":
        score += 18
    elif url_live == "paywalled":
        score += 8
    elif url_live == "dead":
        score -= 80
    elif source == "openai":
        score -= 15

    if item.get("verified") and url_live != "dead":
        score += 12
    elif item.get("verified") is False and source == "openai":
        score -= 20

    if (item.get("why_it_matters") or "").strip():
        score += 8
    if (item.get("broader_context") or "").strip():
        score += 8
    if item.get("is_structural"):
        score += 5
    if item.get("material_development"):
        score += 5
    if item.get("is_follow_up"):
        score += 1

    editorial_score, editorial_notes = score_editorial_relevance(
        item,
        section_id=section_id,
        topic_cfg=topic_cfg,
        sources_cfg=sources_cfg,
        dedup_entries=dedup_entries,
    )
    score += editorial_score
    notes.extend(editorial_notes)
    return score, notes
