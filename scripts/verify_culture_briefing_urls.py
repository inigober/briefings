#!/usr/bin/env python3
"""HTTP-verify Official Link URLs in a berlin-culture briefing (post-synthesis guard)."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
from datetime import datetime, timezone

import requests

from briefing_paths import load_briefing_type
from culture_url_verify import check_url_live, is_transient_verify_note
from validate_culture_briefing import parse_entries

DEFAULT_SECOND_PASS_DELAY_SECONDS = 3.0

OFFICIAL_LINK_RE = re.compile(
    r"^\*\*Official Link:\*\*\s*\[[^\]]*\]\((https?://[^)\s]+)\)",
    re.MULTILINE,
)


def log(message: str) -> None:
    print(message, flush=True)


def extract_official_link_urls(text: str) -> list[str]:
    """Return unique Official Link URLs in document order."""
    urls: list[str] = []
    seen: set[str] = set()
    for match in OFFICIAL_LINK_RE.finditer(text or ""):
        raw = match.group(1).strip().rstrip(".,;")
        key = raw.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        urls.append(raw)
    return urls


def verify_culture_briefing_urls(
    urls: list[str],
    *,
    session: requests.Session | None = None,
    sleep_ms: int = 80,
    second_pass_delay_seconds: float = DEFAULT_SECOND_PASS_DELAY_SECONDS,
) -> tuple[list[str], list[tuple[str, str]]]:
    sess = session or requests.Session()
    live: list[str] = []
    dead: list[tuple[str, str]] = []
    for index, url in enumerate(urls):
        if index and sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)
        ok, note = check_url_live(url, session=sess)
        if ok:
            live.append(url)
        else:
            dead.append((url, note or "unreachable"))

    transient = [(url, note) for url, note in dead if is_transient_verify_note(note)]
    if not transient:
        return live, dead

    if second_pass_delay_seconds > 0:
        time.sleep(second_pass_delay_seconds)

    still_dead: list[tuple[str, str]] = []
    recovered = 0
    for url, note in dead:
        if not is_transient_verify_note(note):
            still_dead.append((url, note))
            continue
        ok, retry_note = check_url_live(url, session=sess)
        if ok:
            live.append(url)
            recovered += 1
        else:
            still_dead.append((url, retry_note or note))
    if recovered:
        log(f"Second pass recovered {recovered} previously unreachable Official Link(s)")
    return live, still_dead


def resolve_briefing_path(
    *,
    briefing_type: str,
    briefing_path: Path | None,
    date_str: str | None,
) -> Path:
    briefing = load_briefing_type(briefing_type)
    if briefing_path:
        resolved = briefing_path
    else:
        resolved_date = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resolved = briefing.briefing_path(resolved_date)
    if not resolved.is_file():
        raise FileNotFoundError(f"Briefing not found: {resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HTTP-verify berlin-culture Official Link URLs"
    )
    parser.add_argument("--type", default="berlin-culture")
    parser.add_argument("--date", help="YYYY-MM-DD Tuesday briefing date")
    parser.add_argument("--briefing", type=Path, help="Path to briefing markdown")
    parser.add_argument(
        "--sleep-ms",
        type=int,
        default=80,
        help="Delay between HTTP checks (default: 80ms)",
    )
    parser.add_argument(
        "--second-pass-delay",
        type=float,
        default=DEFAULT_SECOND_PASS_DELAY_SECONDS,
        help="Seconds to wait before re-checking timed-out Official Links (default: 3)",
    )
    parser.add_argument(
        "--skip-missing-check",
        action="store_true",
        help="Do not fail when an entry lacks an Official Link",
    )
    args = parser.parse_args()

    try:
        briefing_path = resolve_briefing_path(
            briefing_type=args.type,
            briefing_path=args.briefing,
            date_str=args.date,
        )
    except (FileNotFoundError, ValueError) as exc:
        log(str(exc))
        return 1

    text = briefing_path.read_text(encoding="utf-8")
    entries = parse_entries(text)
    missing = [e["title"] for e in entries if not (e.get("official_url") or "").strip()]
    if missing and not args.skip_missing_check:
        log(f"FAIL: {len(missing)} entr(y/ies) missing Official Link in {briefing_path.name}:")
        for title in missing:
            log(f"  - {title}")
        return 1

    urls = extract_official_link_urls(text)
    if not urls:
        log(f"No Official Link URLs found in {briefing_path.name}")
        return 1 if entries else 0

    log(f"HTTP-checking {len(urls)} Official Link(s) in {briefing_path}...")
    second_pass_delay = args.second_pass_delay
    if args.sleep_ms <= 0 and args.second_pass_delay == DEFAULT_SECOND_PASS_DELAY_SECONDS:
        # Tests pass --sleep-ms 0; keep the run fast and skip the pause.
        second_pass_delay = 0.0
    live, dead = verify_culture_briefing_urls(
        urls,
        sleep_ms=args.sleep_ms,
        second_pass_delay_seconds=second_pass_delay,
    )

    if dead:
        log(f"FAIL: {len(dead)} unreachable Official Link(s) in {briefing_path.name}:")
        for url, note in dead:
            log(f"  - {url} ({note})")
        log("Fix or replace dead Official Links before commit/send.")
        return 1

    log(f"OK: {len(live)} Official Link(s) in {briefing_path.name} are reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
