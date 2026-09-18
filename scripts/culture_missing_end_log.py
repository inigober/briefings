#!/usr/bin/env python3
"""Append-only log of exhibitions dropped because no closing date could be confirmed."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from culture_calendar import normalize_official_url  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_PATH = REPO_ROOT / "state/berlin-culture/missing_end_dates.md"

HEADER = """# Exhibitions dropped for missing closing date

Append-only audit log. One row when synthesis **drops** a show because inbox `dates` and the official page both lack a closing/end date. Do not invent a closing date. Do not mention these drops in the emailed briefing.

Keep this file across weeks (do not trim on the 8-week events_index cadence) so we can count how often it happens.

Format: `YYYY-MM-DD | title | venue | dates as found | official_url | notes`

"""


def _cell(value: str) -> str:
    return " ".join(str(value or "").replace("|", "/").split())


def format_log_row(
    *,
    date_str: str,
    title: str,
    venue: str,
    dates: str,
    url: str,
    notes: str = "",
) -> str:
    parts = [
        (date_str or "").strip(),
        _cell(title),
        _cell(venue),
        _cell(dates),
        _cell(url),
    ]
    note = _cell(notes)
    if note:
        parts.append(note)
    return " | ".join(parts)


def parse_log_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("Format:"):
            continue
        if " | " not in line:
            continue
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) < 5:
            continue
        rows.append(
            {
                "date": parts[0],
                "title": parts[1],
                "venue": parts[2],
                "dates": parts[3],
                "url": parts[4],
                "notes": parts[5] if len(parts) > 5 else "",
            }
        )
    return rows


def _row_key(date_str: str, url: str, title: str) -> tuple[str, str, str]:
    return (
        (date_str or "").strip(),
        normalize_official_url(url or ""),
        _cell(title).lower(),
    )


def append_missing_end_date_row(
    *,
    date_str: str,
    title: str,
    venue: str,
    dates: str,
    url: str,
    notes: str = "",
    path: Path | None = None,
) -> bool:
    """Append one row. Returns False when that date+URL (or title) is already logged."""
    log_path = path or DEFAULT_LOG_PATH
    existing = ""
    if log_path.is_file():
        existing = log_path.read_text(encoding="utf-8")
    if not existing.strip():
        existing = HEADER
    key = _row_key(date_str, url, title)
    for row in parse_log_rows(existing):
        if _row_key(row["date"], row["url"], row["title"]) == key:
            return False
    line = format_log_row(
        date_str=date_str,
        title=title,
        venue=venue,
        dates=dates,
        url=url,
        notes=notes,
    )
    body = existing.rstrip() + "\n" + line + "\n"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(body, encoding="utf-8")
    return True


def summarize_log(text: str) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for row in parse_log_rows(text):
        if row.get("date"):
            counts[row["date"]] += 1
    return sorted(counts.items())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log (or summarise) exhibitions dropped for a missing closing date."
    )
    parser.add_argument("--date", help="Briefing Tuesday YYYY-MM-DD")
    parser.add_argument("--title", help="Exhibition title")
    parser.add_argument("--venue", default="", help="Venue")
    parser.add_argument("--dates", default="", help="Date(s) string as found")
    parser.add_argument("--url", default="", help="Official URL")
    parser.add_argument("--notes", default="", help="Optional short note")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Log markdown path",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print counts per briefing date and exit",
    )
    args = parser.parse_args()

    if args.summary:
        text = args.path.read_text(encoding="utf-8") if args.path.is_file() else ""
        rows = summarize_log(text)
        if not rows:
            print("No dropped-missing-end-date rows yet.")
            return 0
        total = 0
        for date_str, count in rows:
            print(f"{date_str}: {count}")
            total += count
        print(f"total: {total}")
        return 0

    missing = [name for name in ("date", "title") if not getattr(args, name)]
    if missing:
        print(f"ERROR: --{' and --'.join(missing)} required unless --summary", file=sys.stderr)
        return 2

    added = append_missing_end_date_row(
        date_str=args.date,
        title=args.title,
        venue=args.venue,
        dates=args.dates,
        url=args.url,
        notes=args.notes,
        path=args.path,
    )
    if added:
        print(f"Logged missing closing date: {args.title}")
    else:
        print(f"Already logged for {args.date}: {args.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
