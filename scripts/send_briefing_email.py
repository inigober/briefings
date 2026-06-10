#!/usr/bin/env python3
"""Render a briefing markdown file to styled HTML and send via Resend."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import markdown
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent

EMAIL_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  color: #1a1a1a;
  max-width: 680px;
  margin: 0 auto;
  padding: 24px 20px;
  background: #ffffff;
}
h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0 0 0.5rem;
  line-height: 1.3;
}
h2 {
  font-size: 1.125rem;
  font-weight: 700;
  margin: 1.75rem 0 0.75rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid #e5e5e5;
  color: #111;
}
h3 {
  font-size: 1rem;
  font-weight: 600;
  margin: 1.25rem 0 0.5rem;
  color: #222;
}
p { margin: 0.5rem 0 1rem; }
ul, ol { margin: 0.5rem 0 1rem; padding-left: 1.25rem; }
li { margin: 0.25rem 0; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
hr {
  border: none;
  border-top: 1px solid #e5e5e5;
  margin: 1.5rem 0;
}
blockquote {
  margin: 0.75rem 0 1rem;
  padding: 10px 14px;
  background: #f4f4f5;
  border-left: 3px solid #a1a1aa;
  border-radius: 4px;
  color: #3f3f46;
  font-size: 0.95rem;
}
blockquote p { margin: 0; }
em { color: #52525b; font-size: 0.875rem; }
"""


def extract_title(md_text: str, fallback: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def render_html(md_text: str) -> str:
    body = markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "smarty"],
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>{EMAIL_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


def send_resend(*, api_key: str, from_addr: str, to_addrs: list[str], subject: str, html: str) -> dict:
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
    if not response.ok:
        raise RuntimeError(f"Resend API error {response.status_code}: {response.text}")
    return response.json()


def resolve_briefing_path(explicit: str | None, changed_files: list[str]) -> Path:
    if explicit:
        path = Path(explicit)
        return path if path.is_absolute() else REPO_ROOT / path

    candidates: list[Path] = []
    for raw in changed_files:
        if raw.endswith(".md") and raw.startswith("briefings/"):
            candidates.append(REPO_ROOT / raw)

    if not candidates:
        briefings = sorted((REPO_ROOT / "briefings").glob("*.md"))
        if not briefings:
            raise FileNotFoundError("No briefing markdown files found")
        return briefings[-1]

    return sorted(candidates)[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Send briefing email via Resend")
    parser.add_argument("--file", help="Path to briefing markdown (default: latest or from CHANGED_FILES)")
    parser.add_argument("--dry-run", action="store_true", help="Write HTML preview only; do not send")
    args = parser.parse_args()

    changed_raw = os.environ.get("CHANGED_FILES", "")
    changed_files = [f.strip() for f in changed_raw.split() if f.strip()]

    try:
        briefing_path = resolve_briefing_path(args.file, changed_files)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not briefing_path.exists():
        print(f"Briefing not found: {briefing_path}", file=sys.stderr)
        return 1

    md_text = briefing_path.read_text(encoding="utf-8")
    title = extract_title(md_text, briefing_path.stem)
    html = render_html(md_text)

    if args.dry_run:
        preview = REPO_ROOT / "briefings" / f"{briefing_path.stem}.preview.html"
        preview.write_text(html, encoding="utf-8")
        print(f"Wrote preview: {preview}")
        return 0

    api_key = os.environ.get("RESEND_API_KEY")
    from_addr = os.environ.get("BRIEFING_FROM_EMAIL")
    to_raw = os.environ.get("BRIEFING_TO_EMAIL", "")

    if not api_key or not from_addr or not to_raw:
        print("RESEND_API_KEY, BRIEFING_FROM_EMAIL, and BRIEFING_TO_EMAIL are required", file=sys.stderr)
        return 1

    to_addrs = [e.strip() for e in re.split(r"[,;]", to_raw) if e.strip()]
    result = send_resend(
        api_key=api_key,
        from_addr=from_addr,
        to_addrs=to_addrs,
        subject=title,
        html=html,
    )
    print(f"Sent email for {briefing_path.name}: {result.get('id', result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
