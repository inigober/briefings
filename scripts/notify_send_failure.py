#!/usr/bin/env python3
"""Email an alert when the send-briefing-email workflow fails."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment,misc]


def log(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("BRIEFING_FROM_EMAIL") or "").strip()
    to_raw = (os.environ.get("BRIEFING_TO_EMAIL") or "").strip()
    run_url = (os.environ.get("GITHUB_RUN_URL") or "").strip()
    changed = (os.environ.get("CHANGED_FILES") or os.environ.get("BRIEFING_FILE") or "").strip()
    reason = (os.environ.get("SEND_FAILURE_REASON") or "verify or send step failed").strip()

    if not api_key or not from_addr or not to_raw:
        log("Send-failure alert skipped — RESEND_API_KEY / BRIEFING_* not set")
        return 0
    if requests is None:
        log("Send-failure alert skipped — requests not installed")
        return 0

    to_addrs = [part.strip() for part in to_raw.replace(";", ",").split(",") if part.strip()]
    files_html = ""
    if changed:
        items = "".join(f"<li><code>{path}</code></li>" for path in changed.split() if path)
        files_html = f"<p><strong>Briefing file(s):</strong></p><ul>{items}</ul>"

    run_html = f'<p>GitHub Actions run: <a href="{run_url}">{run_url}</a></p>' if run_url else ""
    subject = "[Briefing] Email send failed"
    if changed:
        first = changed.split()[0]
        subject = f"[Briefing] Email send failed — {first}"

    html = f"""<p><strong>A briefing was committed but the email send workflow failed.</strong></p>
<p>Reason: {reason}</p>
{files_html}
{run_html}
<p>Common causes: a dead/flaky Official Link or Listen URL during verify, or a Resend API error.</p>
<p>Fix the briefing if needed, then re-run <strong>Send briefing email</strong> from GitHub Actions
(workflow dispatch → optional file path), or wait for the daily undelivered-briefing check.</p>"""

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
    except requests.RequestException as exc:
        log(f"Warning: could not send send-failure alert: {exc}")
        return 1

    if response.ok:
        log("Send-failure alert email sent via Resend")
        return 0

    log(f"Warning: Resend alert failed ({response.status_code}): {response.text[:200]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
