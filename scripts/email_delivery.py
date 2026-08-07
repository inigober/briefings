#!/usr/bin/env python3
"""Track which briefing files were successfully emailed (send-failure recovery)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from briefing_paths import REPO_ROOT, is_test_briefing_path, load_manifest

DELIVERY_LOG_PATH = REPO_ROOT / "state" / "email_delivery.json"
DATE_IN_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_TRIM_DAYS = 90


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_delivery_log(path: Path = DELIVERY_LOG_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"started_at": utc_now_iso(), "deliveries": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"started_at": utc_now_iso(), "deliveries": []}
    data.setdefault("started_at", utc_now_iso())
    data.setdefault("deliveries", [])
    return data


def save_delivery_log(data: dict[str, Any], path: Path = DELIVERY_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def briefing_date_from_path(path: Path) -> str | None:
    match = DATE_IN_NAME_RE.search(path.name)
    return match.group(1) if match else None


def infer_type_from_path(path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        rel = path
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "briefings":
        type_id = parts[1]
        if type_id in load_manifest():
            return type_id
    return None


def delivered_paths(data: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for entry in data.get("deliveries") or []:
        raw = (entry.get("path") or "").strip()
        if raw:
            paths.add(raw.replace("\\", "/"))
    return paths


def record_delivery(
    briefing_path: Path,
    *,
    resend_id: str = "",
    subject: str = "",
    path: Path = DELIVERY_LOG_PATH,
) -> dict[str, Any]:
    """Append or refresh a delivery record for a briefing path."""
    data = load_delivery_log(path)
    try:
        rel = str(briefing_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        rel = str(briefing_path).replace("\\", "/")

    type_id = infer_type_from_path(briefing_path) or ""
    date_str = briefing_date_from_path(briefing_path) or ""
    entry = {
        "path": rel,
        "type": type_id,
        "date": date_str,
        "sent_at": utc_now_iso(),
        "resend_id": resend_id or "",
        "subject": subject or "",
    }

    deliveries = [
        d for d in (data.get("deliveries") or []) if (d.get("path") or "") != rel
    ]
    deliveries.append(entry)
    data["deliveries"] = trim_deliveries(deliveries)
    save_delivery_log(data, path)
    return entry


def trim_deliveries(
    deliveries: list[dict[str, Any]],
    *,
    keep_days: int = DEFAULT_TRIM_DAYS,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    kept: list[dict[str, Any]] = []
    for entry in deliveries:
        sent_raw = (entry.get("sent_at") or "").strip()
        try:
            sent_at = datetime.fromisoformat(sent_raw.replace("Z", "+00:00"))
        except ValueError:
            kept.append(entry)
            continue
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        if sent_at >= cutoff:
            kept.append(entry)
    return kept


def list_recent_briefings(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    repo_root: Path = REPO_ROOT,
) -> list[Path]:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
    found: list[Path] = []
    briefings_root = repo_root / "briefings"
    if not briefings_root.is_dir():
        return []
    for type_dir in sorted(briefings_root.iterdir()):
        if not type_dir.is_dir():
            continue
        for path in sorted(type_dir.glob("*.md")):
            if is_test_briefing_path(path) or path.name.startswith("_"):
                continue
            date_str = briefing_date_from_path(path)
            if not date_str:
                continue
            try:
                day = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if day >= cutoff:
                found.append(path)
    return found


def find_undelivered_briefings(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    log_path: Path = DELIVERY_LOG_PATH,
    repo_root: Path = REPO_ROOT,
) -> list[Path]:
    """Return recent production briefings with no delivery record.

    Only considers briefings on/after the log's ``started_at`` date so a fresh
    log does not re-send the whole archive.
    """
    data = load_delivery_log(log_path)
    delivered = delivered_paths(data)
    started_raw = (data.get("started_at") or "").strip()
    try:
        started = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        started_date = started.date()
    except ValueError:
        started_date = datetime.now(timezone.utc).date()

    undelivered: list[Path] = []
    for path in list_recent_briefings(lookback_days=lookback_days, repo_root=repo_root):
        date_str = briefing_date_from_path(path)
        if not date_str:
            continue
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
        if day < started_date:
            continue
        try:
            rel = str(path.resolve().relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel = str(path).replace("\\", "/")
        if rel not in delivered:
            undelivered.append(path)
    return undelivered
