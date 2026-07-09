#!/usr/bin/env python3
"""Alert when a scheduled pre-fetch did not land in inbox/ by the health-check time."""

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

from briefing_paths import REPO_ROOT, load_briefing_type, load_manifest  # noqa: E402
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
}


@dataclass(frozen=True)
class PrefetchStatus:
    type_id: str
    display_name: str
    date_str: str
    ok: bool
    detail: str


def log(message: str) -> None:
    print(message, flush=True)


def inbox_ready(bt, date_str: str) -> tuple[bool, str]:
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

    if type_id == "news":
        day = datetime.strptime(date_str, "%Y-%m-%d")
        if not is_scheduled_on_date(bt.schedule_cron, day):
            return PrefetchStatus(
                type_id=type_id,
                display_name=bt.display_name,
                date_str=inbox_date,
                ok=True,
                detail="not scheduled today",
            )

    ok, detail = inbox_ready(bt, inbox_date)
    return PrefetchStatus(
        type_id=type_id,
        display_name=bt.display_name,
        date_str=inbox_date,
        ok=ok,
        detail=detail,
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


def send_missed_alert(missed: list[PrefetchStatus]) -> None:
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("BRIEFING_FROM_EMAIL") or "").strip()
    to_raw = (os.environ.get("BRIEFING_TO_EMAIL") or "").strip()
    if not api_key or not from_addr or not to_raw:
        log("  (Missed pre-fetch email skipped — RESEND_API_KEY / BRIEFING_* not set)")
        return
    if requests is None:
        log("  (Missed pre-fetch email skipped — requests not installed)")
        return

    to_addrs = [part.strip() for part in to_raw.split(",") if part.strip()]
    items_html = "".join(
        f"<li><strong>{status.display_name}</strong> ({status.type_id}) — "
        f"{status.date_str}: {status.detail}</li>"
        for status in missed
    )
    subject = "[Briefing] Pre-fetch missed — " + ", ".join(s.type_id for s in missed)
    html = f"""<p><strong>Scheduled pre-fetch did not land in the repo.</strong></p>
<ul>{items_html}</ul>
<p>Check GitHub Actions for the matching <code>*-prefetch.yml</code> workflow, then run it manually if needed.</p>
<p>Repo: <code>inigober/briefings</code> → Actions → choose workflow → <strong>Run workflow</strong>.</p>"""

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
            log("  Missed pre-fetch alert email sent via Resend")
        else:
            log(
                f"  Warning: Resend alert failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
    except requests.RequestException as exc:
        log(f"  Warning: could not send missed pre-fetch email: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check scheduled pre-fetch landed in inbox/")
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

    missed: list[PrefetchStatus] = []
    for type_id in types_for_profile(args.profile):
        status = check_type(type_id, date_str)
        if status.detail == "not scheduled today":
            log(f"  {status.display_name}: skip ({status.detail})")
            continue
        if status.ok:
            log(f"  {status.display_name}: ok ({status.detail})")
        else:
            log(f"  {status.display_name}: MISSED ({status.detail})")
            missed.append(status)

    if not missed:
        return 0

    for status in missed:
        print(
            f"::error title=Pre-fetch missed::{status.display_name} {status.date_str} — "
            f"{status.detail}",
            flush=True,
        )

    if not args.dry_run:
        if args.retry:
            dispatch_prefetch_retries(missed)
        send_missed_alert(missed)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
