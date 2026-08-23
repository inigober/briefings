#!/usr/bin/env python3
"""Alert when scheduled pre-fetch missed inbox/, or inbox is ready but the briefing is missing."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from briefing_paths import (  # noqa: E402
    REPO_ROOT,
    load_briefing_type,
    load_manifest,
    production_briefing_exists,
)
from cron_schedule import is_scheduled_on_date  # noqa: E402
from prefetch_dates import resolve_inbox_date_key  # noqa: E402

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment,misc]

PREFETCH_WORKFLOW_BY_TYPE: dict[str, str] = {
    "news": "news-prefetch.yml",
    "berlin-culture": "berlin-culture-prefetch.yml",
    "berlin-restaurants": "berlin-restaurants-prefetch.yml",
    "music-discovery": "music-discovery-prefetch.yml",
}


@dataclass(frozen=True)
class PrefetchStatus:
    type_id: str
    display_name: str
    date_str: str
    ok: bool
    detail: str
    kind: str = "prefetch"  # prefetch | synthesis | skip | ok


def log(message: str) -> None:
    print(message, flush=True)


def inbox_ready(bt, date_str: str) -> tuple[bool, str]:
    if bt.id == "music-discovery":
        synthesis = bt.inbox_path(date_str, "synthesis")
        raw = bt.inbox_path(date_str, "raw")
        context = bt.inbox_dir / f"{date_str}-context.json"
        if synthesis.exists():
            return True, f"found {synthesis.relative_to(REPO_ROOT)}"
        if raw.exists():
            return (
                False,
                f"found {raw.relative_to(REPO_ROOT)} only — slim step may have failed",
            )
        if context.exists():
            return (
                False,
                f"found {context.relative_to(REPO_ROOT)} but missing {date_str}-synthesis.json "
                "(OpenAI music research step may have failed)",
            )
        return False, f"missing {date_str}-synthesis.json (taste + research pre-fetch)"

    synthesis = bt.inbox_path(date_str, "synthesis")
    raw = bt.inbox_path(date_str, "raw")
    if synthesis.exists():
        return True, f"found {synthesis.relative_to(REPO_ROOT)}"
    if raw.exists():
        return (
            False,
            f"found {raw.relative_to(REPO_ROOT)} only — slim step may have failed",
        )
    return False, f"missing {date_str}-synthesis.json and {date_str}-raw.json"


def check_type(type_id: str, date_str: str) -> PrefetchStatus:
    bt = load_briefing_type(type_id)
    inbox_date = resolve_inbox_date_key(type_id, date_str)

    if type_id in ("news", "music-discovery"):
        day = datetime.strptime(date_str, "%Y-%m-%d")
        if not is_scheduled_on_date(bt.schedule_cron, day):
            return PrefetchStatus(
                type_id=type_id,
                display_name=bt.display_name,
                date_str=inbox_date,
                ok=True,
                detail="not scheduled today",
                kind="skip",
            )

    ok, detail = inbox_ready(bt, inbox_date)
    if not ok:
        return PrefetchStatus(
            type_id=type_id,
            display_name=bt.display_name,
            date_str=inbox_date,
            ok=False,
            detail=detail,
            kind="prefetch",
        )
    if not production_briefing_exists(bt, inbox_date):
        return PrefetchStatus(
            type_id=type_id,
            display_name=bt.display_name,
            date_str=inbox_date,
            ok=False,
            detail=(
                f"inbox ready ({detail}), briefing missing — "
                "enable Cursor Automation “Briefing synthesis” or re-run it"
            ),
            kind="synthesis",
        )
    return PrefetchStatus(
        type_id=type_id,
        display_name=bt.display_name,
        date_str=inbox_date,
        ok=True,
        detail=f"{detail}; briefing present",
        kind="ok",
    )


def types_for_profile(profile: str) -> tuple[str, ...]:
    if profile == "all":
        return tuple(sorted(load_manifest()))
    if profile == "restaurants":
        return ("berlin-restaurants",)
    return ("news", "berlin-culture")


def dispatch_prefetch_retries(missed: list[PrefetchStatus]) -> list[str]:
    """Re-trigger missed pre-fetch workflows via GitHub Actions API (CI only)."""
    if requests is None:
        log("  (Pre-fetch retry skipped — requests not installed)")
        return []

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not token or not repo:
        log("  (Pre-fetch retry skipped — GITHUB_TOKEN / GITHUB_REPOSITORY not set)")
        return []

    dispatched: list[str] = []
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    for status in missed:
        workflow_file = PREFETCH_WORKFLOW_BY_TYPE.get(status.type_id)
        if not workflow_file:
            continue
        url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_file}/dispatches"
        try:
            response = requests.post(
                url,
                headers=headers,
                json={"ref": "main"},
                timeout=30,
            )
        except requests.RequestException as exc:
            log(f"  Warning: could not dispatch {workflow_file}: {exc}")
            continue
        if response.status_code == 204:
            log(f"  Re-triggered {workflow_file} for {status.display_name}")
            dispatched.append(status.type_id)
        else:
            log(
                f"  Warning: dispatch {workflow_file} failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
    return dispatched


def send_health_alert(*, kind: str, items: list[PrefetchStatus]) -> None:
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("BRIEFING_FROM_EMAIL") or "").strip()
    to_raw = (os.environ.get("BRIEFING_TO_EMAIL") or "").strip()
    label = "pre-fetch" if kind == "prefetch" else "synthesis"
    if not api_key or not from_addr or not to_raw:
        log(f"  (Missed {label} email skipped — RESEND_API_KEY / BRIEFING_* not set)")
        return
    if requests is None:
        log(f"  (Missed {label} email skipped — requests not installed)")
        return

    to_addrs = [part.strip() for part in to_raw.split(",") if part.strip()]
    items_html = "".join(
        f"<li><strong>{status.display_name}</strong> ({status.type_id}) — "
        f"{status.date_str}: {status.detail}</li>"
        for status in items
    )
    if kind == "prefetch":
        subject = "[Briefing] Pre-fetch missed — " + ", ".join(s.type_id for s in items)
        html = f"""<p><strong>Scheduled pre-fetch did not land in the repo.</strong></p>
<ul>{items_html}</ul>
<p>Check GitHub Actions for the matching <code>*-prefetch.yml</code> workflow, then run it manually if needed.</p>
<p>Repo: <code>inigober/briefings</code> → Actions → choose workflow → <strong>Run workflow</strong>.</p>"""
    else:
        subject = "[Briefing] Synthesis missing — " + ", ".join(s.type_id for s in items)
        html = f"""<p><strong>Inbox is ready but the production briefing is missing.</strong></p>
<ul>{items_html}</ul>
<p>Cursor Automation <strong>Briefing synthesis</strong> did not write <code>briefings/{{type}}/YYYY-MM-DD.md</code>.</p>
<ol>
<li>Open <a href="https://cursor.com/automations">cursor.com/automations</a> and confirm <strong>Briefing synthesis</strong> is enabled (push to <code>main</code>).</li>
<li>Re-run that automation, or re-run the matching <code>*-prefetch.yml</code> workflow so a fresh inbox push retriggers it.</li>
</ol>
<p>This check does not call OpenAI and cannot start Cursor from GitHub Actions.</p>"""

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
                "html": html,
            },
            timeout=30,
        )
        if response.ok:
            log(f"  Missed {label} alert email sent via Resend")
        else:
            log(
                f"  Warning: Resend alert failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
    except requests.RequestException as exc:
        log(f"  Warning: could not send missed {label} email: {exc}")


def send_missed_alert(missed: list[PrefetchStatus]) -> None:
    """Backward-compatible wrapper for pre-fetch-only alerts."""
    send_health_alert(kind="prefetch", items=missed)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check scheduled pre-fetch landed, and that a briefing exists when inbox is ready"
    )
    parser.add_argument(
        "--date",
        help="UTC date to check (YYYY-MM-DD; default: today UTC)",
    )
    parser.add_argument(
        "--profile",
        choices=("all", "morning", "restaurants"),
        default="all",
        help="all = every briefing type scheduled today; morning = news + culture; restaurants = Thursday only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results only; do not send alert email or re-trigger workflows",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Re-dispatch missed pre-fetch workflows via GitHub Actions API",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    known = set(load_manifest())
    for type_id in types_for_profile(args.profile):
        if type_id not in known:
            log(f"Unknown briefing type in profile: {type_id}")
            return 1

    problems: list[PrefetchStatus] = []
    for type_id in types_for_profile(args.profile):
        status = check_type(type_id, date_str)
        if status.kind == "skip" or status.detail == "not scheduled today":
            log(f"  {status.display_name}: skip ({status.detail})")
            continue
        if status.ok:
            log(f"  {status.display_name}: ok ({status.detail})")
        elif status.kind == "synthesis":
            log(f"  {status.display_name}: SYNTHESIS MISSING ({status.detail})")
            problems.append(status)
        else:
            log(f"  {status.display_name}: MISSED ({status.detail})")
            problems.append(status)

    if not problems:
        return 0

    prefetch_missed = [s for s in problems if s.kind == "prefetch"]
    synthesis_missed = [s for s in problems if s.kind == "synthesis"]

    for status in prefetch_missed:
        print(
            f"::error title=Pre-fetch missed::{status.display_name} {status.date_str} — "
            f"{status.detail}",
            flush=True,
        )
    for status in synthesis_missed:
        print(
            f"::error title=Synthesis missing::{status.display_name} {status.date_str} — "
            f"{status.detail}",
            flush=True,
        )

    if not args.dry_run:
        if args.retry and prefetch_missed:
            dispatch_prefetch_retries(prefetch_missed)
        if prefetch_missed:
            send_health_alert(kind="prefetch", items=prefetch_missed)
        if synthesis_missed:
            send_health_alert(kind="synthesis", items=synthesis_missed)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
