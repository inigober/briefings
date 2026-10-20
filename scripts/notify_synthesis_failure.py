#!/usr/bin/env python3
"""Email an alert when the synthesize-briefing workflow fails."""

from __future__ import annotations

import html
import os
import sys

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment,misc]


def log(message: str) -> None:
    print(message, flush=True)


def build_message(type_id: str, date: str, reason: str, run_url: str) -> tuple[str, str]:
    esc = html.escape
    subject = f"[Briefing] Synthesis failed — {type_id or 'unknown'} {date or ''}".strip()
    run_html = (
        f'<p>GitHub Actions run: <a href="{esc(run_url)}">{esc(run_url)}</a></p>' if run_url else ""
    )
    body = f"""<p><strong>Claude synthesis failed.</strong></p>
<p>Type: <code>{esc(type_id or 'unknown')}</code> · Date: <code>{esc(date or 'unknown')}</code></p>
<p>Trigger reason: {esc(reason or '(none)')}</p>
{run_html}
<p>Check the Actions log. After fixing, re-run <strong>Synthesize briefing</strong>
(Actions → Run workflow, mode <code>backup</code>).</p>"""
    return subject, body


def main() -> int:
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("BRIEFING_FROM_EMAIL") or "").strip()
    to_raw = (os.environ.get("BRIEFING_TO_EMAIL") or "").strip()
    if not api_key or not from_addr or not to_raw:
        log("Synthesis-failure alert skipped — RESEND_API_KEY / BRIEFING_* not set")
        return 0
    if requests is None:
        log("Synthesis-failure alert skipped — requests not installed")
        return 0

    subject, body = build_message(
        os.environ.get("TYPE", ""),
        os.environ.get("DATE", ""),
        os.environ.get("REASON", ""),
        os.environ.get("GITHUB_RUN_URL", ""),
    )
    to_addrs = [p.strip() for p in to_raw.replace(";", ",").split(",") if p.strip()]
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": from_addr, "to": to_addrs, "subject": subject, "html": body},
            timeout=30,
        )
    except requests.RequestException as exc:
        log(f"Warning: could not send synthesis-failure alert: {exc}")
        return 1
    if response.ok:
        log("Synthesis-failure alert email sent via Resend")
        return 0
    log(f"Warning: Resend alert failed ({response.status_code}): {response.text[:200]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
