#!/usr/bin/env python3
"""Load briefing type paths and metadata from config/briefings.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "briefings.yaml"


@dataclass(frozen=True)
class BriefingType:
    id: str
    display_name: str
    schedule_cron: str
    inbox_dir: Path
    output_dir: Path
    state_dir: Path
    config_dir: Path
    synthesis_prompt: Path
    style_rule: Path
    prefetch_rss: bool
    prefetch_wordpress: bool
    prefetch_merge_script: str
    prefetch_slim: bool
    email_preheader_section: str
    email_subject_emoji: str

    @property
    def topics_path(self) -> Path:
        return self.config_dir / "topics.yaml"

    @property
    def sources_path(self) -> Path:
        return self.config_dir / "sources.yaml"

    def inbox_path(self, date_str: str, suffix: str) -> Path:
        return self.inbox_dir / f"{date_str}-{suffix}.json"

    def briefing_path(self, date_str: str) -> Path:
        return self.output_dir / f"{date_str}.md"


def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("briefings") or {}


def load_briefing_type(type_id: str) -> BriefingType:
    briefings = load_manifest()
    if type_id not in briefings:
        known = ", ".join(sorted(briefings)) or "(none)"
        raise ValueError(f"Unknown briefing type '{type_id}'. Known: {known}")

    cfg = briefings[type_id]
    prefetch = cfg.get("prefetch") or {}
    email = cfg.get("email") or {}

    def p(rel: str) -> Path:
        return REPO_ROOT / rel

    return BriefingType(
        id=type_id,
        display_name=cfg.get("display_name") or type_id,
        schedule_cron=cfg.get("schedule_cron") or "",
        inbox_dir=p(cfg["inbox_dir"]),
        output_dir=p(cfg["output_dir"]),
        state_dir=p(cfg["state_dir"]),
        config_dir=p(cfg["config_dir"]),
        synthesis_prompt=p(cfg["synthesis_prompt"]),
        style_rule=p(cfg["style_rule"]),
        prefetch_rss=bool(prefetch.get("rss")),
        prefetch_wordpress=bool(prefetch.get("wordpress")),
        prefetch_merge_script=str(prefetch.get("merge_script") or ""),
        prefetch_slim=bool(prefetch.get("slim", True)),
        email_preheader_section=str(email.get("preheader_section") or ""),
        email_subject_emoji=str(email.get("subject_emoji") or "").strip(),
    )


def infer_type_from_briefing_path(path: Path) -> str | None:
    """Infer briefing type from path like briefings/news/2026-06-11.md."""
    try:
        rel = path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = path
    parts = Path(rel).parts
    if len(parts) >= 2 and parts[0] == "briefings":
        type_id = parts[1]
        if type_id in load_manifest():
            return type_id
    return None
