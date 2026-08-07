#!/usr/bin/env python3
"""Find briefings on main that never emailed; alert and optionally re-trigger send."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from email_delivery import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    find_undelivered_briefings,
)
from briefing_paths import REPO_ROOT  # noqa: E402

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment,misc]

SEND_WORKFLOW = "send-briefing-email.yml"


def log(message: str) -> None:
    print(message, flush=True)


def dispatch_send_retries(paths: list[Path]) -> list[str]:
    if requests is None:
        log("  (Send retry skipped — requests not installed)")
        return []

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    repo = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if not token or not repo:
        log("  (Send retry skipped — GITHUB_TOKEN / GITHUB_REPOSITORY not set)")
        return []

    dispatched: list[str] = []
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{SEND_WORKFLOW}/dispatches"

    for path in paths:
        try:
            rel = str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            rel = str(path).replace("\\", "/")
        try:
            response = requests.post(
                url,
                headers=headers,
                json={"ref": "main", "inputs": {"file": rel}},
                timeout=30,
            )
        except requests.RequestException as exc:
            log(f"  Warning: could not dispatch send for {rel}: {exc}")
            continue
        if response.status_code == 204:
            log(f"  Re-triggered send for {rel}")
            dispatched.append(rel)
        else:
            log(
                f"  Warning: dispatch send for {rel} failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
    return dispatched


def send_undelivered_alert(paths: list[Path]) -> None:
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("BRIEFING_FROM_EMAIL") or "").strip()
    to_raw = (os.environ.get("BRIEFING_TO_EMAIL") or "").strip()
    if not api_key or not from_addr or not to_raw:
        log("  (Undelivered email alert skipped — RESEND_API_KEY / BRIEFING_* not set)")
        return
    if requests is None:
        log("  (Undelivered email alert skipped — requests not installed)")
        return

    to_addrs = [part.strip() for part in to_raw.replace(";", ",").split(",") if part.strip()]
    items = []
    for path in paths:
        try:
            rel = str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            rel = str(path).replace("\\", "/")
        items.append(f"<li><code>{rel}</code></li>")
    subject = "[Briefing] Undelivered briefing(s) on main"
    html = f"""<p><strong>These briefings are on <code>main</code> but were never emailed successfully:</strong></p>
<ul>{''.join(items)}</ul>
<p>The health check will try to re-trigger <code>send-briefing-email.yml</code> for each file.
If verify still fails (dead link), fix the briefing and push, or re-run send manually.</p>"""

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
            log("  Undelivered-briefing alert email sent via Resend")
        else:
            log(
                f"  Warning: Resend alert failed ({response.status_code}): "
                f"{response.text[:200]}"
            )
    except requests.RequestException as exc:
        log(f"  Warning: could not send undelivered alert: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Alert (and optionally re-send) briefings that never emailed"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Only consider briefings from the last N days (default {DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print undelivered paths only; do not alert or re-trigger send",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Re-dispatch send-briefing-email.yml for each undelivered file",
    )
    args = parser.parse_args()

    undelivered = find_undelivered_briefings(lookback_days=args.lookback_days)
    if not undelivered:
        log("All recent briefings have delivery records")
        return 0

    for path in undelivered:
        try:
            rel = str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            rel = str(path).replace("\\", "/")
        log(f"  UNDELIVERED: {rel}")
        print(f"::error title=Undelivered briefing::{rel}", flush=True)

    if not args.dry_run:
        send_undelivered_alert(undelivered)
        if args.retry:
            dispatch_send_retries(undelivered)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
