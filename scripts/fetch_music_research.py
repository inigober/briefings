#!/usr/bin/env python3
"""Pre-fetch music-discovery release candidates via OpenAI web_search.

Taste cache is already in inbox/ (materialize_music_inbox.py). This step finds
Bandcamp / YouTube / cover / Dig URLs so Codex synthesis does not need to browse.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from briefing_paths import REPO_ROOT, load_briefing_type
from fetch_openai_research import (
    DEFAULT_MODEL,
    fetch_structured,
    fetch_web_research,
    load_yaml,
    log,
    make_client,
    resolve_model,
)
from music_dates import normalize_friday_run_date
from openai_spend import (
    MUSIC_FETCH_BUDGET_RESERVE_USD,
    DailySpendLedger,
    SpendCapExceeded,
    count_web_search_calls,
    handle_cap_abort,
    resolve_daily_cap,
    usage_from_response,
)

MUSIC_SEARCH_MIN_CALLS = 4
MUSIC_SEARCH_MAX_TOOL_CALLS = 8
MUSIC_MIN_CANDIDATES = 16

MUSIC_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "topic_ids": {"type": "array", "items": {"type": "string"}},
        "artist": {"type": "string"},
        "release": {"type": "string"},
        "label": {"type": "string"},
        "year": {"type": "integer"},
        "mode": {"type": "string", "enum": ["club", "home"]},
        "era": {"type": "string", "enum": ["recent", "aged-well"]},
        "genre": {"type": "string"},
        "context": {"type": "string"},
        "cover_url": {"type": "string"},
        "bandcamp_url": {"type": "string"},
        "youtube_url": {"type": ["string", "null"]},
        "dig_sentence": {"type": "string"},
        "dig_url": {"type": "string"},
        "writeup_url": {"type": ["string", "null"]},
        "writeup_source": {"type": ["string", "null"]},
        "reception_ok": {"type": "boolean"},
        "why_candidate": {"type": "string"},
    },
    "required": [
        "id",
        "topic_ids",
        "artist",
        "release",
        "label",
        "year",
        "mode",
        "era",
        "genre",
        "context",
        "cover_url",
        "bandcamp_url",
        "youtube_url",
        "dig_sentence",
        "dig_url",
        "writeup_url",
        "writeup_source",
        "reception_ok",
        "why_candidate",
    ],
    "additionalProperties": False,
}

COMBINED_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": MUSIC_CANDIDATE_SCHEMA},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "search_notes": {"type": "string"},
    },
    "required": ["items", "gaps", "search_notes"],
    "additionalProperties": False,
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def release_key(artist: str, release: str) -> tuple[str, str]:
    return _norm(artist), _norm(release)


def keys_match(left: tuple[str, str], right: tuple[str, str]) -> bool:
    """Fuzzy artist + release match (substring on release, exact-ish artist)."""
    la, lr = left
    ra, rr = right
    if not la or not lr or not ra or not rr:
        return False
    if la != ra:
        return False
    return lr == rr or lr in rr or rr in lr


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_releases_index(state_dir: Path) -> list[str]:
    path = state_dir / "releases_index.md"
    if not path.is_file():
        return []
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
    return lines


def compact_skip_list(skip_list: list[dict]) -> list[str]:
    lines: list[str] = []
    for item in skip_list:
        artist = (item.get("artist") or "").strip()
        release = (item.get("release") or "").strip()
        status = (item.get("status") or "").strip()
        if artist and release:
            extra = f" ({status})" if status else ""
            lines.append(f"{artist} — {release}{extra}")
    return lines


def compact_known_labels(known: list[dict], *, limit: int = 40) -> list[str]:
    lines: list[str] = []
    for item in known[:limit]:
        name = (item.get("name") or "").strip()
        tracks = item.get("tracks")
        if name:
            lines.append(f"{name} ({tracks})" if tracks is not None else name)
    return lines


def compact_recent_taste(recent: dict) -> str:
    rekordbox = recent.get("rekordbox") or {}
    spotify = recent.get("spotify") or {}
    artists = ", ".join(
        (a.get("name") or "")
        for a in (rekordbox.get("top_artists") or [])[:12]
        if a.get("name")
    )
    genres = ", ".join(
        (g.get("name") or "")
        for g in (rekordbox.get("top_genres") or [])[:10]
        if g.get("name")
    )
    labels = ", ".join(
        (lab.get("name") or "")
        for lab in (rekordbox.get("top_labels") or [])[:10]
        if lab.get("name")
    )
    liked = ", ".join(
        (a.get("name") or "")
        for a in (spotify.get("liked_artists") or [])[:12]
        if a.get("name")
    )
    now_4w = (
        spotify.get("listening_now_4w")
        or spotify.get("now")
        or liked
        or ""
    )
    if isinstance(now_4w, list):
        now_line = ", ".join(str(x) for x in now_4w[:12])
    else:
        now_line = str(now_4w)
    return (
        f"Rekordbox artists: {artists or '(none)'}\n"
        f"Rekordbox genres: {genres or '(none)'}\n"
        f"Rekordbox labels: {labels or '(none)'}\n"
        f"Spotify listening now: {now_line or '(none)'}"
    )


def load_taste_bundle(inbox_dir: Path, date_str: str, state_dir: Path) -> dict[str, Any]:
    context = load_json(inbox_dir / f"{date_str}-context.json")
    snapshot_path = inbox_dir / f"{date_str}-taste-snapshot.md"
    snapshot = snapshot_path.read_text(encoding="utf-8") if snapshot_path.is_file() else ""
    return {
        "context": context,
        "snapshot": snapshot,
        "skip_lines": compact_skip_list(context.get("skip_list") or []),
        "known_label_lines": compact_known_labels(context.get("known_labels") or []),
        "known_label_threshold": int(context.get("known_label_threshold") or 15),
        "recent_taste_block": compact_recent_taste(context.get("recent_taste") or {}),
        "releases_index": load_releases_index(state_dir),
        "library_albums": (context.get("library_skip") or {}).get("albums") or [],
    }


def build_search_phase_prompt(
    *,
    date_str: str,
    taste: dict[str, Any],
    search_domains: list[str],
) -> str:
    skip = "\n".join(f"- {line}" for line in taste["skip_lines"]) or "- (none)"
    known = "\n".join(f"- {line}" for line in taste["known_label_lines"]) or "- (none)"
    repeats = "\n".join(f"- {line}" for line in taste["releases_index"][:40]) or "- (none)"
    snapshot = (taste.get("snapshot") or "").strip()
    if len(snapshot) > 12000:
        snapshot = snapshot[:12000] + "\n…(truncated)…"
    domains = "\n".join(f"- {d}" for d in search_domains)
    return f"""You are researching candidates for a weekly personal music discovery briefing. PHASE 1: web research only.

Briefing Friday date: {date_str}
Target: at least {MUSIC_MIN_CANDIDATES} release candidates with **exact live URLs copied from search results**.
Mix: roughly half club/DJ-floor and half home listening; mix recent (2024–2026) and aged-well records.
Need enough extras that synthesis can pick **6 featured (3 club + 3 home) + 4 More listening**.

## Reader taste (weight recent 24 months)
{taste.get("recent_taste_block") or "(see snapshot)"}

## Taste snapshot (read this)
{snapshot or "(missing — use recent taste block)"}

## Skip — never recommend
{skip}

## Familiar labels (demote to More listening unless a trusted write-up singles the release out)
{known}

## Already in recent briefings (avoid same artist + release)
{repeats}

## Your task (web_search REQUIRED — minimum {MUSIC_SEARCH_MIN_CALLS} searches)
You MUST call web_search at least {MUSIC_SEARCH_MIN_CALLS} times before answering. Suggested split:
1. Bandcamp Daily / recent album pages that fit club taste (prog house, techno, trance, italo, electro, chunker/hard house)
2. Bandcamp Daily / RA / Wire home-listening (ambient, balearic, experimental, downtempo, world)
3. Aged-well / catalogue records that still captivate (not obvious canon primers)
4. YouTube / YouTube Music **album or release playlist** lookup for the strongest candidates

For each candidate record:
- artist, release, label, year, club-or-home, recent-or-aged-well, genre
- **bandcamp_url copied exactly** from search (prefer `/album/…`; never invent slugs)
- **cover_url** — omit or leave empty unless you copied a real `f4.bcbits.com` / `bcbits.com` image URL from the page. Do **not** invent image IDs. A later step hydrates covers from Bandcamp HTML, or iTunes / Cover Art Archive when GitHub gets a Bandcamp bot page.
- **youtube_url** album/playlist when you find a live one; otherwise omit
- **dig_url** — one related live Bandcamp (or label) URL for further digging
- trusted write-up URL if used for the reception gate (RA, Bandcamp Daily, The Wire, Mixmag, Fact, Pitchfork, DJ Mag, Boomkat, etc.)
- one-paragraph context (why it captivates; place the artist/label)
- reception_ok: true if ≥ ~4 weeks old OR you copied a trusted write-up URL

Rules:
- Do **not** guess Bandcamp paths from titles.
- Do **not** recommend skip-list or recent-briefing repeats.
- Owned-library filtering happens in Python after this step; still avoid snapshot saved albums.
- Familiar-label catalogue filler → More listening unless a write-up elevates it.
- Captivation bar: skip anonymous DJ-tool 12"s and textbook canon primers.
- Never Apple Music. Prefer Bandcamp album URLs over Spotify.

## Output format
Return detailed research notes in plain text — **NOT JSON**.
Every candidate MUST include the exact bandcamp_url (and cover/youtube/dig URLs) copied from web_search results.
web_search allowed domains:
{domains}
"""


def build_structure_phase_prompt(
    *,
    date_str: str,
    research_notes: str,
) -> str:
    return f"""You are structuring music-discovery pre-fetch candidates. PHASE 2: JSON only.

Briefing Friday date: {date_str}

## Rules (strict)
- Convert ONLY releases documented in the web research notes below into JSON items.
- Copy bandcamp_url, cover_url, youtube_url, dig_url, and writeup_url **verbatim** — do not modify, guess, or construct URLs.
- Do NOT use web_search. Do NOT add releases missing from the notes.
- topic_ids: `featured` or `more_listening` (familiar labels → more_listening unless a write-up elevates them).
- mode: `club` or `home`. era: `recent` or `aged-well`.
- youtube_url / writeup_url / writeup_source: null when missing.
- year: integer. reception_ok: true only if age ≥ ~4 weeks or a writeup_url is present.
- id: kebab-case `artist-release` slug.
- If fewer than {MUSIC_MIN_CANDIDATES} solid candidates, list gaps — never invent filler.

## Web research notes (from Phase 1 web_search)
{research_notes}

Return JSON: items, gaps, search_notes."""


def is_known_label(label: str, known: list[dict], *, threshold: int) -> bool:
    name = _norm(label)
    if not name:
        return False
    for item in known:
        other = _norm(item.get("name") or "")
        tracks = int(item.get("tracks") or 0)
        if other and other == name and tracks >= threshold:
            return True
    return False


def matches_skip_or_library(
    artist: str,
    release: str,
    *,
    skip_list: list[dict],
    library_albums: list[dict],
    recent_releases: list[str],
) -> str | None:
    key = release_key(artist, release)
    for item in skip_list:
        if keys_match(key, release_key(item.get("artist") or "", item.get("release") or "")):
            return "skip_list"
    for item in library_albums:
        if keys_match(key, release_key(item.get("artist") or "", item.get("release") or "")):
            return "library_skip"
    for line in recent_releases:
        # "Artist — Release"
        if "—" in line:
            left, right = line.split("—", 1)
        elif "-" in line:
            left, right = line.split("-", 1)
        else:
            continue
        if keys_match(key, release_key(left, right)):
            return "releases_index"
    return None


def enrich_candidate(
    item: dict,
    *,
    known_labels: list[dict],
    threshold: int,
    skip_list: list[dict],
    library_albums: list[dict],
    recent_releases: list[str],
) -> dict:
    topic_ids = [t for t in (item.get("topic_ids") or []) if t]
    if topic_ids and topic_ids[0] in ("featured", "more_listening"):
        section = topic_ids[0]
    else:
        section = "featured"
    extra = [t for t in topic_ids if t != section]
    item["topic_ids"] = [section, *extra]
    item["ingestion_source"] = "openai"
    item["known_label"] = is_known_label(
        item.get("label") or "", known_labels, threshold=threshold
    )
    if item["known_label"] and section == "featured" and not item.get("writeup_url"):
        item["topic_ids"] = ["more_listening"]
    blocked = matches_skip_or_library(
        item.get("artist") or "",
        item.get("release") or "",
        skip_list=skip_list,
        library_albums=library_albums,
        recent_releases=recent_releases,
    )
    item["blocked_reason"] = blocked
    item["verified"] = False
    item["url_live"] = None
    item["url_verify_notes"] = "Pending HTTP verification"
    return item


def section_counts(items: list[dict]) -> dict[str, int]:
    counts = {"featured": 0, "more_listening": 0, "club": 0, "home": 0}
    for item in items:
        topic = (item.get("topic_ids") or ["featured"])[0]
        if topic in counts:
            counts[topic] += 1
        mode = item.get("mode")
        if mode in counts:
            counts[mode] += 1
    return counts


def fetch_all_music(
    *,
    date_str: str,
    model: str,
    taste: dict[str, Any],
    sources_cfg: dict,
    spend_ledger: DailySpendLedger | None = None,
) -> dict:
    date_str, _ = normalize_friday_run_date(date_str)
    allowed = sources_cfg.get("allowed_domains") or []

    if spend_ledger and spend_ledger.cap_enabled():
        log(
            f"  Daily spend cap: ${spend_ledger.cap_usd:.2f} "
            f"(already spent today: ${spend_ledger.spent_usd:.4f})"
        )
        spend_ledger.assert_not_over_cap()

    if spend_ledger and not spend_ledger.try_reserve_section_budget(
        reserve_usd=MUSIC_FETCH_BUDGET_RESERVE_USD
    ):
        raise RuntimeError("Insufficient daily OpenAI budget remaining")

    client = make_client()
    search_prompt = build_search_phase_prompt(
        date_str=date_str,
        taste=taste,
        search_domains=allowed,
    )
    log("  Phase 1: web_search for music-discovery candidates...")
    notes, search_response = fetch_web_research(
        client=client,
        model=model,
        prompt=search_prompt,
        domains=allowed,
        require_web_search=True,
        max_tool_calls=MUSIC_SEARCH_MAX_TOOL_CALLS,
        search_context_size="medium",
    )
    web_search_calls = count_web_search_calls(search_response)
    log(f"    phase 1: {web_search_calls} web_search call(s), {len(notes)} chars")
    if spend_ledger:
        usage = usage_from_response(
            response=search_response, model=model, section="music_search"
        )
        spend_ledger.record_usage(usage)
        spend_ledger.assert_not_over_cap()
    if web_search_calls < MUSIC_SEARCH_MIN_CALLS:
        raise RuntimeError(
            f"Music pre-fetch aborted: {web_search_calls} web_search calls "
            f"(minimum {MUSIC_SEARCH_MIN_CALLS} required)."
        )

    structure_prompt = build_structure_phase_prompt(
        date_str=date_str, research_notes=notes
    )
    log("  Phase 2: structure candidates as JSON (no web_search)...")
    result, structure_response = fetch_structured(
        client=client,
        model=model,
        prompt=structure_prompt,
        schema=COMBINED_RESULT_SCHEMA,
        schema_name="music_combined",
        domains=[],
        enable_web_search=False,
    )
    if spend_ledger:
        usage = usage_from_response(
            response=structure_response, model=model, section="music_structure"
        )
        spend_ledger.record_usage(usage)
        spend_ledger.assert_not_over_cap()

    context = taste.get("context") or {}
    raw_items = result.get("items") or []
    items = [
        enrich_candidate(
            dict(item),
            known_labels=context.get("known_labels") or [],
            threshold=int(taste.get("known_label_threshold") or 15),
            skip_list=context.get("skip_list") or [],
            library_albums=taste.get("library_albums") or [],
            recent_releases=taste.get("releases_index") or [],
        )
        for item in raw_items
    ]
    kept = [item for item in items if not item.get("blocked_reason")]
    dropped = len(items) - len(kept)
    if dropped:
        log(f"  Dropped {dropped} skip/library/repeat matches")
    counts = section_counts(kept)
    log(f"  Combined fetch done ({len(kept)} candidates) — {counts}")

    return {
        "briefing_type": "music-discovery",
        "date": date_str,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "fetch_mode": "search_then_structure",
        "items": kept,
        "dropped_count": dropped,
        "gaps": result.get("gaps") or [],
        "section_counts": counts,
        "verified_count": 0,
        "search_notes": result.get("search_notes") or "",
        "phase1_web_search_calls": web_search_calls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch music-discovery research via OpenAI web_search"
    )
    parser.add_argument("--type", default="music-discovery")
    parser.add_argument("--date", help="YYYY-MM-DD Friday run date (default: today UTC)")
    parser.add_argument("--model", default=None, help=f"Override model (default: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="Print phase-1 prompt only")
    args = parser.parse_args()

    briefing = load_briefing_type(args.type)
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    original = date_str
    date_str, _ = normalize_friday_run_date(date_str)
    if date_str != original:
        log(
            f"  Warning: {original} is not a Friday — using previous Friday "
            f"{date_str} for file naming"
        )

    sources_cfg = load_yaml(briefing.sources_path)
    taste = load_taste_bundle(briefing.inbox_dir, date_str, briefing.state_dir)
    if not taste["snapshot"] and not taste["context"]:
        log(
            f"Missing taste inbox for {date_str}. "
            "Run materialize_music_inbox.py first."
        )
        return 1

    if args.dry_run:
        log(
            build_search_phase_prompt(
                date_str=date_str,
                taste=taste,
                search_domains=sources_cfg.get("allowed_domains") or [],
            )
        )
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        log("OPENAI_API_KEY is not set")
        return 1

    model = resolve_model(args.model)
    inbox_dir = briefing.inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = inbox_dir / f"{date_str}-raw.json"

    cap_usd = resolve_daily_cap()
    spend_path = inbox_dir / f"{date_str}-spend.json"
    spend_ledger = DailySpendLedger.load_or_create(
        spend_path, date_str=date_str, cap_usd=cap_usd
    )

    log(f"Fetching music-discovery research for {date_str} with model {model}...")
    try:
        payload = fetch_all_music(
            date_str=date_str,
            model=model,
            taste=taste,
            sources_cfg=sources_cfg,
            spend_ledger=spend_ledger,
        )
    except SpendCapExceeded as exc:
        handle_cap_abort(
            ledger=spend_ledger,
            spend_path=spend_path,
            error_path=inbox_dir / f"{date_str}-spend-cap.error.txt",
            briefing_label=briefing.display_name,
            date_str=date_str,
        )
        log(str(exc))
        return 1
    except Exception as exc:
        spend_ledger.save(spend_path)
        err_path = inbox_dir / f"{date_str}-raw.error.txt"
        err_path.write_text(str(exc) + "\n", encoding="utf-8")
        log(str(exc))
        return 1

    spend_ledger.save(spend_path)
    if spend_ledger.cap_enabled():
        log(
            f"  Run spend total: ${spend_ledger.spent_usd:.4f} "
            f"(daily cap ${spend_ledger.cap_usd:.2f})"
        )

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(
        f"Wrote {out_path} ({len(payload.get('items') or [])} candidates; "
        "run verify_music_inbox_urls.py next)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
