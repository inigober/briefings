#!/usr/bin/env python3
"""Quarterly reminder to bump the OpenAI pre-fetch model when a better mid-tier exists.

Source of truth is DEFAULT_MODEL in fetch_openai_research.py — not a GitHub Variable
(an override there can go stale). Policy: prefer a newer *sol* (or successor mid-tier)
that still supports web_search; skip nano/codex/ChatGPT SKUs, skip astra (more expensive),
skip luna as the default (too small for copy-exact Bandcamp research).

The 11:00 Berlin health check runs this with --email-if-due. Emails only on
1 Jan / 1 Apr / 1 Jul / 1 Oct so it does not mix with daily briefing mail.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from fetch_openai_research import DEFAULT_MODEL  # noqa: E402

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment,misc]

BERLIN = ZoneInfo("Europe/Berlin")
REVIEW_MONTHS = (1, 4, 7, 10)
MODELS_DOCS = "https://developers.openai.com/api/docs/models"
MODELS_API = "https://api.openai.com/v1/models"

# Mid-tier research models we would actually switch DEFAULT_MODEL to.
PREFERRED_TIERS = frozenset({"sol"})
# Capable but not the default (too expensive or too small).
SKIP_TIERS = frozenset({"astra", "luna", "cyber", "nano", "codex", "mini", "pro"})
SKIP_SUBSTRINGS = (
    "nano",
    "codex",
    "realtime",
    "transcribe",
    "tts",
    "image",
    "audio",
    "instruct",
    "preview",
    "computer-use",
    "chatgpt",
)

MODEL_ID_RE = re.compile(
    r"^gpt-(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:-(?P<tier>[a-z0-9]+))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedModel:
    model_id: str
    major: int
    minor: int
    tier: str

    @property
    def sort_key(self) -> tuple[int, int, str]:
        return (self.major, self.minor, self.tier)


def log(message: str) -> None:
    print(message, flush=True)


def berlin_today(now: datetime | None = None) -> date:
    stamp = now or datetime.now(tz=BERLIN)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=BERLIN)
    return stamp.astimezone(BERLIN).date()


def is_review_due(day: date) -> bool:
    return day.month in REVIEW_MONTHS and day.day == 1


def parse_model_id(model_id: str) -> ParsedModel | None:
    name = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", (model_id or "").strip())
    match = MODEL_ID_RE.match(name)
    if not match:
        return None
    minor = int(match.group("minor") or 0)
    tier = (match.group("tier") or "").lower()
    return ParsedModel(
        model_id=name,
        major=int(match.group("major")),
        minor=minor,
        tier=tier,
    )


def is_skipped_id(model_id: str) -> bool:
    lowered = model_id.lower()
    return any(part in lowered for part in SKIP_SUBSTRINGS)


def is_preferred_research_model(parsed: ParsedModel) -> bool:
    if is_skipped_id(parsed.model_id):
        return False
    if parsed.tier in SKIP_TIERS:
        return False
    # gpt-6.1-sol and a future gpt-7-sol (tier empty only if OpenAI drops suffixes).
    if parsed.tier in PREFERRED_TIERS:
        return True
    return False


def newer_than(candidate: ParsedModel, current: ParsedModel) -> bool:
    if candidate.sort_key[:2] > current.sort_key[:2]:
        return True
    if candidate.sort_key[:2] == current.sort_key[:2] and candidate.tier != current.tier:
        # Same version, different tier — only interesting if current is un-suffixed.
        return (not current.tier) and candidate.tier in PREFERRED_TIERS
    return False


def pick_candidates(current_id: str, listed_ids: list[str]) -> list[str]:
    current = parse_model_id(current_id)
    if current is None:
        return []
    found: list[ParsedModel] = []
    seen: set[str] = set()
    for raw in listed_ids:
        parsed = parse_model_id(raw)
        if parsed is None or parsed.model_id == current_id:
            continue
        if parsed.model_id in seen:
            continue
        seen.add(parsed.model_id)
        if not is_preferred_research_model(parsed):
            continue
        if newer_than(parsed, current):
            found.append(parsed)
    found.sort(key=lambda item: item.sort_key, reverse=True)
    return [item.model_id for item in found]


def list_openai_model_ids(api_key: str) -> list[str]:
    if requests is None:
        raise RuntimeError("requests is not installed")
    response = requests.get(
        MODELS_API,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or []
    ids: list[str] = []
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return ids


def review_html(*, current: str, candidates: list[str], listed: bool) -> str:
    candidate_bits = "".join(f"<li><code>{name}</code></li>" for name in candidates) or (
        "<li>(none listed that match the mid-tier rule)</li>"
    )
    listed_line = (
        "Live model list came from the OpenAI API."
        if listed
        else "OpenAI API was not queried (no key or request failed) — check the models page by hand."
    )
    return f"""<p>This is a <strong>quarterly ops reminder</strong>, not a briefing.</p>
<p>Pre-fetch currently uses <code>{current}</code> from <code>scripts/fetch_openai_research.py</code>
(<code>DEFAULT_MODEL</code>). There is no GitHub Actions variable for the model — keep it that way
unless you want an override that can go stale.</p>
<p><strong>Policy:</strong> switch when OpenAI ships a newer mid-tier that is at least as capable
and slightly cheaper (today that means a newer <code>*-sol</code> with web_search). Skip
ChatGPT nano/codex SKUs, skip <code>astra</code> (more expensive), skip <code>luna</code> as
the default (too small for copy-exact Bandcamp URLs).</p>
<p>Candidates the API listed that look newer than <code>{current}</code>:</p>
<ul>{candidate_bits}</ul>
<p>{listed_line}</p>
<p>To change: edit <code>DEFAULT_MODEL</code> in <code>scripts/fetch_openai_research.py</code>,
the workflow fallbacks, <code>.env.example</code>, and the spend table in
<code>scripts/openai_spend.py</code>. Then merge.</p>
<p>Catalog: <a href="{MODELS_DOCS}">{MODELS_DOCS}</a></p>"""


def send_review_email(*, current: str, candidates: list[str], listed: bool) -> None:
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("BRIEFING_FROM_EMAIL") or "").strip()
    to_raw = (os.environ.get("BRIEFING_TO_EMAIL") or "").strip()
    if not api_key or not from_addr or not to_raw:
        log("  (Model review email skipped — RESEND_API_KEY / BRIEFING_* not set)")
        return
    if requests is None:
        log("  (Model review email skipped — requests not installed)")
        return
    to_addrs = [part.strip() for part in to_raw.split(",") if part.strip()]
    subject = f"[Briefing] Quarterly OpenAI model review — currently {current}"
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_addr,
                "to": to_addrs,
                "subject": subject,
                "html": review_html(
                    current=current, candidates=candidates, listed=listed
                ),
            },
            timeout=30,
        )
        if response.ok:
            log("  OpenAI model review email sent via Resend")
        else:
            log(
                f"  Warning: Resend model review failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
    except requests.RequestException as exc:
        log(f"  Warning: could not send model review email: {exc}")


def build_report(
    *,
    current: str,
    due: bool,
    candidates: list[str],
    listed: bool,
) -> dict[str, Any]:
    return {
        "current": current,
        "review_due": due,
        "candidates": candidates,
        "listed_from_api": listed,
        "policy": "newer mid-tier sol (web_search); skip nano/codex/astra/luna-as-default",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Quarterly OpenAI pre-fetch model review")
    parser.add_argument(
        "--date",
        help="YYYY-MM-DD in Europe/Berlin (default: today Berlin)",
    )
    parser.add_argument(
        "--email-if-due",
        action="store_true",
        help="Send the Resend reminder on 1 Jan / 1 Apr / 1 Jul / 1 Oct",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    if args.date:
        day = date.fromisoformat(args.date)
    else:
        day = berlin_today()
    due = is_review_due(day)
    current = DEFAULT_MODEL
    env_override = (os.environ.get("OPENAI_RESEARCH_MODEL") or "").strip()
    if env_override and env_override != current:
        log(
            f"  Warning: OPENAI_RESEARCH_MODEL={env_override!r} overrides "
            f"DEFAULT_MODEL={current!r} — prefer the code default so this review stays accurate"
        )

    listed = False
    candidates: list[str] = []
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if api_key:
        try:
            listed_ids = list_openai_model_ids(api_key)
            listed = True
            candidates = pick_candidates(current, listed_ids)
            log(f"  OpenAI API listed {len(listed_ids)} models; {len(candidates)} newer mid-tier candidate(s)")
        except Exception as exc:
            log(f"  Warning: could not list OpenAI models: {exc}")
    else:
        log("  OPENAI_API_KEY not set — candidate list skipped")

    log(f"  DEFAULT_MODEL={current} review_due={due} ({day.isoformat()})")
    if candidates:
        log("  Candidates: " + ", ".join(candidates))

    report = build_report(
        current=current, due=due, candidates=candidates, listed=listed
    )
    if args.json:
        print(json.dumps(report, indent=2))

    if args.email_if_due and due:
        send_review_email(current=current, candidates=candidates, listed=listed)
    elif args.email_if_due:
        log("  Not a quarterly review day — no email")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
