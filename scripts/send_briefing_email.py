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

INSIGHT_MARKERS = ("💡", "🧭")

EMAIL_CSS = """
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.65;
  color: #1a1a1a;
  max-width: 600px;
  margin: 0 auto;
  padding: 24px 16px;
  background: #ffffff;
  -webkit-text-size-adjust: 100%;
}
p { margin: 0 0 12px; }
ul, ol { margin: 0 0 20px; padding: 0; }
.story { margin: 0 0 28px; padding: 0; }
.story p { margin: 0 0 10px; padding: 0; text-indent: 0; }
ol.themes { padding-left: 20px; margin: 0 0 20px; }
ol.themes > li { margin: 0 0 14px; }
a { color: #2563eb; text-decoration: none; }
hr {
  border: none;
  border-top: 1px solid #e8e8e8;
  margin: 28px 0;
}
.research-accessed {
  margin: 0 0 20px;
  font-size: 14px;
  color: #71717a;
  font-style: italic;
}
.footnotes {
  margin-top: 32px;
  padding-top: 16px;
  border-top: 1px solid #e8e8e8;
  font-size: 13px;
  color: #71717a;
  line-height: 1.5;
}
.footnotes p { margin: 0 0 6px; }
"""

H1_STYLE = (
    "font-size:28px;font-weight:700;margin:0 0 8px;line-height:1.25;"
    "color:#111111;letter-spacing:-0.02em;"
)
H2_STYLE = (
    "font-size:20px;font-weight:700;margin:32px 0 14px;padding:0;"
    "color:#111111;line-height:1.3;"
)
HR_STYLE = "border:none;border-top:1px solid #e8e8e8;margin:28px 0;"
H3_STYLE = "font-size:17px;font-weight:600;margin:20px 0 10px;color:#222222;"

INSIGHT_STYLE_PLAIN = "margin:14px 0 0;font-weight:500;color:#1a1a1a;"
CONTEXT_STYLE_PLAIN = "margin:10px 0 0;color:#52525b;"
INSIGHT_STYLE_CALLOUT = (
    "margin:14px 0 0;padding:10px 14px;background:#f4f4f5;"
    "border-left:3px solid #71717a;border-radius:4px;font-weight:500;color:#1a1a1a;"
)
CONTEXT_STYLE_CALLOUT = (
    "margin:10px 0 0;padding:10px 14px;background:#fafafa;"
    "border-left:3px solid #d4d4d8;border-radius:4px;color:#52525b;"
)


def extract_title(md_text: str, fallback: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def extract_preheader(md_text: str, max_len: int = 100) -> str:
    """Short inbox-preview line from What Matters Today themes, else first headline."""
    in_themes = False
    snippets: list[str] = []

    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and "What Matters Today" in stripped:
            in_themes = True
            continue
        if in_themes and stripped.startswith("## "):
            break
        if in_themes and re.match(r"^\d+\.\s+", stripped):
            text = re.sub(r"^\d+\.\s*", "", stripped)
            text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
            text = text.split(".")[0].strip()
            if text:
                snippets.append(text)

    if snippets:
        return " · ".join(snippets[:2])[:max_len]

    for line in md_text.splitlines():
        match = re.match(r"^\*\s+\*\*(.+?)\*\*", line.strip())
        if match:
            return match.group(1)[:max_len]

    title = extract_title(md_text, "Daily Briefing")
    return title.replace("Daily Briefing — ", "")[:max_len]


def parse_footnotes(md_text: str) -> dict[str, tuple[str, str]]:
    footnotes: dict[str, tuple[str, str]] = {}
    for line in md_text.splitlines():
        match = re.match(r'^\[(\d+)\]:\s+(\S+)(?:\s+"([^"]*)")?', line.strip())
        if match:
            footnotes[match.group(1)] = (match.group(2), match.group(3) or "")
    return footnotes


def linkify_footnote_refs(text: str, footnotes: dict[str, tuple[str, str]]) -> str:
    def repl(match: re.Match[str]) -> str:
        label, num = match.group(1), match.group(2)
        if num in footnotes:
            url, _ = footnotes[num]
            return f'<a href="{url}" style="color:#2563eb;text-decoration:none;">{label}</a>'
        return match.group(0)

    return re.sub(r"\[([^\]]+)\]\[(\d+)\]", repl, text)


def linkify_inline_markdown(text: str) -> str:
    return re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" style="color:#2563eb;text-decoration:none;">\1</a>',
        text,
    )


def format_story_body(text: str, footnotes: dict[str, tuple[str, str]]) -> str:
    return linkify_inline_markdown(linkify_footnote_refs(text, footnotes))


def is_insight_line(text: str) -> bool:
    return text.startswith(INSIGHT_MARKERS)


def is_context_line(text: str) -> bool:
    return text.startswith("🧩")


def is_research_accessed_line(text: str) -> bool:
    inner = text.strip().strip("_*")
    return inner.lower().startswith("research accessed")


def _insight_html(text: str, use_callouts: bool) -> str:
    style = INSIGHT_STYLE_CALLOUT if use_callouts else INSIGHT_STYLE_PLAIN
    return f'<p class="insight" style="{style}">{text}</p>'


def _context_html(text: str, use_callouts: bool) -> str:
    style = CONTEXT_STYLE_CALLOUT if use_callouts else CONTEXT_STYLE_PLAIN
    return f'<p class="context" style="{style}">{text}</p>'


def _story_block_html(
    lines: list[str], footnotes: dict[str, tuple[str, str]], use_callouts: bool
) -> str:
    parts: list[str] = ['<div class="story" style="margin:0 0 28px;padding:0;">']
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if is_research_accessed_line(stripped):
            inner = stripped.strip("_*")
            parts.append(
                f'<p class="research-accessed" style="margin:0 0 20px;font-size:14px;'
                f'color:#71717a;font-style:italic;">{inner}</p>'
            )
            continue
        if stripped.startswith("* **") or stripped.startswith("- **"):
            title_match = re.match(r"^[*-]\s+\*\*(.+?)\*\*:?\s*(.*)", stripped)
            if title_match:
                title, remainder = title_match.group(1), title_match.group(2).strip()
                parts.append(f'<p style="margin:0 0 10px;font-weight:700;">{title}</p>')
                if remainder:
                    parts.append(
                        f'<p style="margin:0 0 10px;">{format_story_body(remainder, footnotes)}</p>'
                    )
            else:
                parts.append(f'<p style="margin:0 0 10px;font-weight:700;">{stripped}</p>')
            continue
        if is_insight_line(stripped):
            parts.append(_insight_html(stripped, use_callouts))
        elif is_context_line(stripped):
            parts.append(_context_html(stripped, use_callouts))
        else:
            body = format_story_body(stripped, footnotes)
            parts.append(f'<p style="margin:0 0 10px;">{body}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def preprocess_briefing_markdown(
    md_text: str, footnotes: dict[str, tuple[str, str]], use_callouts: bool
) -> str:
    out: list[str] = []
    story_lines: list[str] = []
    i = 0
    lines = md_text.splitlines()

    def flush_story() -> None:
        nonlocal story_lines
        if story_lines:
            out.append(_story_block_html(story_lines, footnotes, use_callouts))
            story_lines = []

    while i < len(lines):
        stripped = lines[i].strip()

        if stripped.startswith("[") and "]: http" in stripped:
            flush_story()
            i += 1
            continue

        if stripped.startswith("# ") or stripped.startswith("## ") or stripped == "---":
            flush_story()
            out.append(stripped)
            i += 1
            continue

        if re.match(r"^\d+\.\s", stripped):
            flush_story()
            out.append(stripped)
            i += 1
            continue

        if is_research_accessed_line(stripped):
            flush_story()
            story_lines = [lines[i]]
            i += 1
            continue

        if (stripped.startswith("* **") or stripped.startswith("- **")) and not stripped.startswith(
            "## "
        ):
            flush_story()
            story_lines = [lines[i]]
            i += 1
            continue

        if story_lines:
            if stripped.startswith("* ") and not stripped.startswith("* **"):
                flush_story()
                out.append(stripped)
            elif stripped == "":
                pass
            else:
                story_lines.append(lines[i])
            i += 1
            continue

        if stripped.startswith("* ") or stripped.startswith("- "):
            out.append(stripped)
        elif stripped:
            out.append(stripped)
        i += 1

    flush_story()
    return "\n".join(out)


def normalize_horizontal_rules(md_text: str) -> str:
    """Remove markdown --- lines; section dividers are inserted in HTML between sections."""
    return "\n".join(line for line in md_text.splitlines() if line.strip() != "---")


def insert_section_dividers(html: str) -> str:
    """Light hr between sections only — not after title, not before the first section."""
    hr = f'<hr style="{HR_STYLE}" />'
    html = re.sub(r"<hr\s*/?>", "", html)
    marker = '<h2 style="'
    parts = html.split(marker)
    if len(parts) <= 1:
        return html
    result = parts[0] + marker + parts[1]
    for part in parts[2:]:
        result += hr + "\n" + marker + part
    return result


def split_footnotes(md_text: str) -> tuple[str, str]:
    body_lines: list[str] = []
    footnote_lines: list[str] = []
    for line in md_text.splitlines():
        if re.match(r"^\[\d+\]:\s+https?://", line.strip()):
            footnote_lines.append(line.strip())
        else:
            body_lines.append(line)
    return "\n".join(body_lines).strip(), "\n".join(footnote_lines)


def apply_inline_heading_styles(html: str) -> str:
    html = re.sub(r"<h1>", f'<h1 style="{H1_STYLE}">', html)
    html = re.sub(r"<h2>", f'<h2 style="{H2_STYLE}">', html)
    html = re.sub(r"<h3>", f'<h3 style="{H3_STYLE}">', html)
    return html


def enhance_compass_paragraphs(html: str, use_callouts: bool) -> str:
    for marker in INSIGHT_MARKERS:
        plain = INSIGHT_STYLE_PLAIN
        callout = INSIGHT_STYLE_CALLOUT
        style = callout if use_callouts else plain
        html = re.sub(
            rf"<p>({re.escape(marker)}[^<]*)</p>",
            rf'<p class="insight" style="{style}">\1</p>',
            html,
        )
    ctx_style = CONTEXT_STYLE_CALLOUT if use_callouts else CONTEXT_STYLE_PLAIN
    html = re.sub(
        r"<p>(🧩[^<]*)</p>",
        rf'<p class="context" style="{ctx_style}">\1</p>',
        html,
    )
    return html


def render_footnotes_html(footnote_md: str) -> str:
    if not footnote_md.strip():
        return ""
    items = markdown.markdown(footnote_md, extensions=["extra"])
    items = items.replace("<p>", '<p style="margin:0 0 6px;">')
    return f'<div class="footnotes">{items}</div>'


def render_preheader_html(preheader: str) -> str:
    if not preheader:
        return ""
    return (
        '<div style="display:none;font-size:1px;line-height:1px;max-height:0;'
        'max-width:0;opacity:0;overflow:hidden;mso-hide:all;">'
        f"{preheader}"
        "</div>"
    )


def render_html(md_text: str, *, use_callouts: bool = True) -> str:
    footnotes = parse_footnotes(md_text)
    body_md, footnotes_md = split_footnotes(md_text)
    body_md = normalize_horizontal_rules(body_md)
    prepared = preprocess_briefing_markdown(body_md, footnotes, use_callouts)
    preheader = extract_preheader(md_text)

    body_html = markdown.markdown(
        prepared,
        extensions=["extra", "sane_lists", "smarty"],
    )
    body_html = apply_inline_heading_styles(body_html)
    body_html = enhance_compass_paragraphs(body_html, use_callouts)
    body_html = insert_section_dividers(body_html)
    body_html = re.sub(
        r"(<h2[^>]*>What Matters Today[^<]*</h2>\s*)<ol>",
        r'\1<ol class="themes">',
        body_html,
        count=1,
    )

    footnotes_html = render_footnotes_html(footnotes_md)
    preheader_html = render_preheader_html(preheader)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="supported-color-schemes" content="light">
  <style>{EMAIL_CSS}</style>
</head>
<body>
{preheader_html}
{body_html}
{footnotes_html}
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
    parser.add_argument(
        "--no-callouts",
        action="store_true",
        help="Disable gray callout boxes (callouts are on by default)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="With --dry-run, write both plain and callout previews",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open preview(s) in default browser after dry-run (macOS)",
    )
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

    use_callouts_env = os.environ.get("BRIEFING_EMAIL_CALLOUTS", "true").lower() not in (
        "0",
        "false",
        "no",
    )
    use_callouts = (not args.no_callouts) and use_callouts_env
    callout_modes = [False, True] if args.dry_run and args.compare else [use_callouts]

    if args.dry_run:
        previews: list[Path] = []
        for use_callouts in callout_modes if args.compare else callout_modes:
            suffix = ".preview-callouts" if use_callouts else ".preview"
            html = render_html(md_text, use_callouts=use_callouts)
            preview = REPO_ROOT / "briefings" / f"{briefing_path.stem}{suffix}.html"
            preview.write_text(html, encoding="utf-8")
            previews.append(preview)
            label = "callout boxes" if use_callouts else "plain"
            print(f"Wrote {label} preview: {preview}")
            print(f"  file://{preview.resolve()}")

        if args.open:
            import subprocess

            for preview in previews:
                subprocess.run(["open", str(preview.resolve())], check=False)
        return 0

    html = render_html(md_text, use_callouts=use_callouts)

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
