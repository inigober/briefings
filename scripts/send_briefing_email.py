#!/usr/bin/env python3
"""Render a briefing markdown file to styled HTML and send via Resend."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

import markdown
import requests

from briefing_paths import REPO_ROOT, infer_type_from_briefing_path, load_briefing_type

INSIGHT_MARKERS = ("💡", "🧭")

CULTURE_SECTION_EMOJI: dict[str, str] = {
    "Top Picks": "🔥",
    "Exhibitions Radar": "🖼️",
    "Film & Screenings": "🎬",
    "Performing Arts": "🎭",
    "Music": "🎧",
    "Wildcards": "🧪",
    "Advance Radar": "📡",
}

CULTURE_META_FIELDS: dict[str, str] = {
    "Venue": "📍",
    "Date(s)": "🗓️",
    "Time(s)": "⏰",
}

# Culture palette: body darkest, meta/callout/footer stepped down — all dark gray for readability.
CULTURE_COLOR_BODY = "#1a1a1a"
CULTURE_COLOR_META = "#52525b"
CULTURE_COLOR_CALLOUT = "#3f3f46"
CULTURE_COLOR_LABEL = "#57534e"
CULTURE_COLOR_FOOTER = "#6b7280"
CULTURE_COLOR_BORDER = "#9ca3af"

CULTURE_LINK_STYLE = (
    f"color:{CULTURE_COLOR_BODY};text-decoration:underline;text-underline-offset:2px;"
)
CULTURE_TITLE_LINK_STYLE = (
    "color:#111111;text-decoration:underline;text-underline-offset:3px;"
)
CULTURE_META_STYLE = (
    f"margin:0 0 6px;padding:0;font-size:14px;color:{CULTURE_COLOR_META};line-height:1.5;"
)
CULTURE_CONTEXT_STYLE = (
    f"margin:12px 0 0;padding:0;font-size:16px;color:{CULTURE_COLOR_BODY};line-height:1.65;"
)
CULTURE_FOOTER_TEXT = "Sent by AI with love from Berlin."
CULTURE_WHY_CALLOUT_STYLE = (
    "margin:14px 0 0;padding:10px 14px;background:#f4f4f5;"
    f"border-left:3px solid {CULTURE_COLOR_BORDER};border-radius:4px;"
    f"font-size:14px;color:{CULTURE_COLOR_CALLOUT};line-height:1.55;"
)
CULTURE_WHY_LABEL_STYLE = f"font-size:12px;font-weight:600;color:{CULTURE_COLOR_LABEL};"
CULTURE_WHY_MINIMAL_STYLE = (
    f"margin:14px 0 0;padding:0;font-size:14px;color:{CULTURE_COLOR_CALLOUT};"
    "line-height:1.55;font-style:italic;"
)

CULTURE_FIELD_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*)")
CULTURE_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

RESTAURANT_ENTRY_RE = re.compile(
    r"^###\s+(.+?)\s+—\s+(.+?)\s+—\s+(€+|€€+|€€€+|€€€€+)"
    r"(?:\s+\((good value|potentially overpriced)\))?$"
)
RESTAURANT_STRONGEST_BETS = "This week's strongest bets"
RESTAURANT_META_FIELDS = ("Hours", "Rating", "Maps")
RESTAURANT_FOOTER_TEXT = "Sent by AI with love from Berlin."
RESTAURANT_TITLE_LINK_STYLE = (
    "color:#111111;text-decoration:underline;text-underline-offset:3px;"
)
RESTAURANT_META_STYLE = (
    f"margin:0 0 10px;padding:0;font-size:14px;color:{CULTURE_COLOR_META};line-height:1.5;"
)
RESTAURANT_BODY_STYLE = (
    f"margin:0;padding:0;font-size:16px;color:{CULTURE_COLOR_BODY};line-height:1.65;"
)

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
.culture-meta { margin: 0 0 0; padding: 0; list-style: none; }
.culture-meta li { margin: 0 0 6px; padding: 0; }
.culture-entry { margin: 0 0 8px; }
.culture-footer {
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid #e8e8e8;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
  font-style: italic;
}
.restaurant-entry { margin: 0 0 8px; }
.restaurant-footer {
  margin-top: 40px;
  padding-top: 20px;
  border-top: 1px solid #e8e8e8;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
  font-style: italic;
}
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


def extract_preheader(md_text: str, section_name: str = "What Matters Today", max_len: int = 100) -> str:
    """Short inbox-preview line from a named section, else first headline."""
    in_section = False
    snippets: list[str] = []

    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("## ", "### ")) and section_name in stripped:
            in_section = True
            continue
        if in_section and stripped.startswith(("## ", "### ")):
            break
        if in_section and re.match(r"^\d+\.\s+", stripped):
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
        h3 = re.match(r"^###\s+(.+)", stripped := line.strip())
        if h3:
            return h3.group(1)[:max_len]

    title = extract_title(md_text, "Briefing")
    for prefix in (
        "News Briefing — ",
        "Berlin Culture Briefing — ",
        "Berlin Restaurant Briefing — ",
        "Daily Briefing — ",
    ):
        if title.startswith(prefix):
            return title.replace(prefix, "")[:max_len]
    return title[:max_len]


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


@dataclass
class CultureEntry:
    title: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class CultureSection:
    name: str
    entries: list[CultureEntry] = field(default_factory=list)


def parse_culture_briefing(md_text: str) -> tuple[str, list[str], list[CultureSection]]:
    """Parse structured culture markdown into title, intro paragraphs, and sections."""
    body_md, _ = split_footnotes(md_text)
    title = ""
    intro: list[str] = []
    sections: list[CultureSection] = []
    current_section: CultureSection | None = None
    current_entry: CultureEntry | None = None
    past_title = False

    for line in body_md.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue

        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip()
            past_title = True
            continue

        if stripped.startswith("## "):
            current_section = CultureSection(name=stripped[3:].strip())
            sections.append(current_section)
            current_entry = None
            continue

        if stripped.startswith("### "):
            if current_section is None:
                current_section = CultureSection(name="")
                sections.append(current_section)
            current_entry = CultureEntry(title=stripped[4:].strip())
            current_section.entries.append(current_entry)
            continue

        field_match = CULTURE_FIELD_RE.match(stripped)
        if field_match and current_entry is not None:
            current_entry.fields[field_match.group(1).strip()] = field_match.group(2).strip()
            continue

        if past_title and current_section is None:
            intro.append(stripped)

    return title, intro, sections


def _parse_official_url(value: str) -> str | None:
    link_match = CULTURE_LINK_RE.search(value)
    if link_match:
        return link_match.group(2)
    stripped = value.strip()
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return stripped
    return None


def _email_link(text: str, url: str, *, style: str = CULTURE_LINK_STYLE) -> str:
    return f'<a href="{url}" style="{style}">{text}</a>'


def _google_maps_url(venue: str) -> str:
    query = quote_plus(f"{venue}, Berlin, Germany")
    return f"https://www.google.com/maps/search/?api=1&query={query}"


def _culture_meta_line(
    emoji: str, content: str, footnotes: dict[str, tuple[str, str]], *, linked: str | None = None
) -> str:
    body = linked if linked is not None else format_story_body(content, footnotes)
    return f'<li style="{CULTURE_META_STYLE}">{emoji} {body}</li>'


def _culture_venue_line(venue: str, footnotes: dict[str, tuple[str, str]]) -> str:
    label = format_story_body(venue, footnotes)
    maps_url = _google_maps_url(venue)
    linked = _email_link(label, maps_url)
    return _culture_meta_line("📍", venue, footnotes, linked=linked)


def _culture_why_html(
    why: str, footnotes: dict[str, tuple[str, str]], *, style: str
) -> str:
    body = format_story_body(why, footnotes)
    if style == "minimal":
        return (
            f'<p style="{CULTURE_WHY_MINIMAL_STYLE}">'
            f'<span style="font-style:normal;font-weight:600;color:{CULTURE_COLOR_LABEL};">'
            f"Why it fits · </span>{body}</p>"
        )
    return (
        f'<div style="{CULTURE_WHY_CALLOUT_STYLE}">'
        f'<div style="{CULTURE_WHY_LABEL_STYLE}">WHY IT FITS</div>'
        f"<div style=\"margin:4px 0 0;\">{body}</div></div>"
    )


def render_culture_entry_html(
    entry: CultureEntry,
    *,
    number: int | None,
    footnotes: dict[str, tuple[str, str]],
    why_style: str = "callout",
) -> str:
    title = format_story_body(entry.title, footnotes)
    official_url = _parse_official_url(entry.fields.get("Official Link", ""))
    if official_url:
        title = _email_link(title, official_url, style=CULTURE_TITLE_LINK_STYLE)

    prefix = f"{number}. " if number is not None else ""
    heading = f"{prefix}{title}"

    parts = [
        '<div class="culture-entry" style="margin:0 0 8px;">',
        f'<h3 style="{H3_STYLE}">{heading}</h3>',
        '<ul class="culture-meta" style="margin:0;padding:0;list-style:none;">',
    ]

    for field_name, emoji in CULTURE_META_FIELDS.items():
        value = entry.fields.get(field_name, "").strip()
        if not value:
            continue
        if field_name == "Venue":
            parts.append(_culture_venue_line(value, footnotes))
        else:
            parts.append(_culture_meta_line(emoji, value, footnotes))

    parts.append("</ul>")

    context = entry.fields.get("Short Context", "").strip()
    if context:
        body = format_story_body(context, footnotes)
        parts.append(f'<p style="{CULTURE_CONTEXT_STYLE}">{body}</p>')

    why = entry.fields.get("Why It Fits", "").strip()
    if why:
        parts.append(_culture_why_html(why, footnotes, style=why_style))

    parts.append("</div>")
    return "\n".join(parts)


def render_culture_footer_html() -> str:
    return (
        f'<div class="culture-footer" style="margin-top:40px;padding-top:20px;'
        f'border-top:1px solid #e8e8e8;text-align:center;font-size:13px;'
        f'color:{CULTURE_COLOR_FOOTER};font-style:italic;">{CULTURE_FOOTER_TEXT}</div>'
    )


def render_culture_body_html(md_text: str, *, why_style: str = "callout") -> str:
    footnotes = parse_footnotes(md_text)
    title, intro, sections = parse_culture_briefing(md_text)
    hr = f'<hr style="{HR_STYLE}" />'
    parts: list[str] = []

    if title:
        parts.append(f'<h1 style="{H1_STYLE}">{title}</h1>')

    for paragraph in intro:
        body = format_story_body(paragraph, footnotes)
        parts.append(f'<p style="margin:0 0 16px;">{body}</p>')

    if intro:
        parts.append(hr)

    item_number = 0
    for section_index, section in enumerate(sections):
        if section_index > 0:
            parts.append(hr)

        emoji = CULTURE_SECTION_EMOJI.get(section.name, "")
        section_label = f"{emoji} {section.name}".strip()
        parts.append(f'<h2 style="{H2_STYLE}">{section_label}</h2>')

        numbered = section.name != "Advance Radar"
        for entry_index, entry in enumerate(section.entries):
            if entry_index > 0:
                parts.append(hr)

            number: int | None = None
            if numbered:
                item_number += 1
                number = item_number

            parts.append(
                render_culture_entry_html(
                    entry, number=number, footnotes=footnotes, why_style=why_style
                )
            )

    parts.append(render_culture_footer_html())
    return "\n".join(parts)


@dataclass
class RestaurantEntry:
    name: str
    neighborhood: str
    price_tier: str
    value_label: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    body_paragraphs: list[str] = field(default_factory=list)


@dataclass
class RestaurantBriefing:
    title: str
    intro: list[str] = field(default_factory=list)
    entries: list[RestaurantEntry] = field(default_factory=list)
    strongest_bets_intro: str = ""
    strongest_bets: list[str] = field(default_factory=list)


def parse_restaurant_briefing(md_text: str) -> RestaurantBriefing:
    """Parse restaurant markdown into title, intro, entries, and strongest bets."""
    body_md, _ = split_footnotes(md_text)
    briefing = RestaurantBriefing(title="")
    current_entry: RestaurantEntry | None = None
    past_title = False
    in_strongest_bets = False

    for line in body_md.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "---":
            continue

        if stripped.startswith("# ") and not stripped.startswith("## "):
            briefing.title = stripped[2:].strip()
            past_title = True
            continue

        if stripped.startswith("## "):
            continue

        entry_match = RESTAURANT_ENTRY_RE.match(stripped)
        if entry_match:
            in_strongest_bets = False
            current_entry = RestaurantEntry(
                name=entry_match.group(1).strip(),
                neighborhood=entry_match.group(2).strip(),
                price_tier=entry_match.group(3).strip(),
                value_label=entry_match.group(4),
            )
            briefing.entries.append(current_entry)
            continue

        if stripped.startswith("### ") and RESTAURANT_STRONGEST_BETS in stripped:
            in_strongest_bets = True
            current_entry = None
            continue

        field_match = CULTURE_FIELD_RE.match(stripped)
        if field_match and current_entry is not None:
            field_name = field_match.group(1).strip()
            if field_name in RESTAURANT_META_FIELDS:
                current_entry.fields[field_name] = field_match.group(2).strip()
            continue

        if in_strongest_bets:
            list_match = re.match(r"^\d+\.\s+(.+)", stripped)
            if list_match:
                briefing.strongest_bets.append(list_match.group(1).strip())
            elif not briefing.strongest_bets:
                briefing.strongest_bets_intro = stripped
            continue

        if current_entry is not None:
            current_entry.body_paragraphs.append(stripped)
            continue

        if past_title:
            briefing.intro.append(stripped)

    return briefing


def _split_restaurant_title(title: str) -> tuple[str, str | None]:
    marker = " — Week of "
    if marker in title:
        main, week = title.split(marker, 1)
        return main.strip(), f"Week of {week.strip()}"
    return title, None


def render_restaurant_title_html(title: str) -> str:
    main, week = _split_restaurant_title(title)
    parts = [f'<h1 style="{H1_STYLE}">', f'<span style="display:block;">{main}</span>']
    if week:
        week_style = (
            "display:block;font-size:20px;font-weight:600;margin-top:8px;"
            "color:#444444;line-height:1.3;"
        )
        parts.append(f'<span style="{week_style}">{week}</span>')
    parts.append("</h1>")
    return "".join(parts)


def _restaurant_maps_url(entry: RestaurantEntry) -> str:
    maps_value = entry.fields.get("Maps", "").strip()
    if maps_value:
        parsed = _parse_official_url(maps_value)
        if parsed:
            return parsed
        if maps_value.startswith("http"):
            return maps_value
    return _google_maps_url(f"{entry.name}, {entry.neighborhood}")


def _format_restaurant_rating(value: str) -> str:
    match = re.search(r"(\d+\.?\d*)", value)
    if not match:
        return value
    rating = match.group(1)
    reviews = re.search(r"\((\d+)\)", value)
    if reviews:
        return f"⭐ {rating} · {reviews.group(1)} reviews"
    return f"⭐ {rating}"


def _restaurant_location_line_html(
    entry: RestaurantEntry, *, maps_url: str, footnotes: dict[str, tuple[str, str]]
) -> str:
    chunks: list[str] = []
    linked_hood = _email_link(entry.neighborhood, maps_url, style=RESTAURANT_TITLE_LINK_STYLE)
    chunks.append(f"📍 {linked_hood}")
    price = entry.price_tier
    if entry.value_label:
        price = f"{price} ({entry.value_label})"
    chunks.append(price)
    rating = entry.fields.get("Rating", "").strip()
    if rating:
        chunks.append(_format_restaurant_rating(rating))
    return f'<p style="{RESTAURANT_META_STYLE}">{" · ".join(chunks)}</p>'


def _restaurant_hours_line_html(
    entry: RestaurantEntry, footnotes: dict[str, tuple[str, str]]
) -> str:
    hours = entry.fields.get("Hours", "").strip()
    if not hours:
        return ""
    body = format_story_body(hours, footnotes)
    return f'<p style="{RESTAURANT_META_STYLE}">🕐 {body}</p>'


def render_restaurant_entry_html(
    entry: RestaurantEntry, *, footnotes: dict[str, tuple[str, str]]
) -> str:
    maps_url = _restaurant_maps_url(entry)

    parts = [
        '<div class="restaurant-entry" style="margin:0 0 8px;">',
        f'<h3 style="{H3_STYLE}">{entry.name}</h3>',
        _restaurant_location_line_html(entry, maps_url=maps_url, footnotes=footnotes),
    ]
    hours_line = _restaurant_hours_line_html(entry, footnotes)
    if hours_line:
        parts.append(hours_line)
    for paragraph in entry.body_paragraphs:
        body = format_story_body(paragraph, footnotes)
        parts.append(f'<p style="{RESTAURANT_BODY_STYLE}">{body}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def render_restaurant_footer_html() -> str:
    return (
        f'<div class="restaurant-footer" style="margin-top:40px;padding-top:20px;'
        f'border-top:1px solid #e8e8e8;text-align:center;font-size:13px;'
        f'color:{CULTURE_COLOR_FOOTER};font-style:italic;">{RESTAURANT_FOOTER_TEXT}</div>'
    )


def render_restaurant_body_html(md_text: str) -> str:
    footnotes = parse_footnotes(md_text)
    briefing = parse_restaurant_briefing(md_text)
    hr = f'<hr style="{HR_STYLE}" />'
    parts: list[str] = []

    if briefing.title:
        parts.append(render_restaurant_title_html(briefing.title))

    for paragraph in briefing.intro:
        body = format_story_body(paragraph, footnotes)
        parts.append(f'<p style="margin:0 0 16px;">{body}</p>')

    if briefing.intro:
        parts.append(hr)

    for entry_index, entry in enumerate(briefing.entries):
        if entry_index > 0:
            parts.append(hr)
        parts.append(render_restaurant_entry_html(entry, footnotes=footnotes))

    if briefing.strongest_bets:
        parts.append(hr)
        parts.append(f'<h3 style="{H3_STYLE}">🏆 {RESTAURANT_STRONGEST_BETS}</h3>')
        if briefing.strongest_bets_intro:
            intro_body = format_story_body(briefing.strongest_bets_intro, footnotes)
            parts.append(f'<p style="margin:0 0 12px;">{intro_body}</p>')
        items = "".join(
            f'<li style="margin:0 0 10px;">{format_story_body(bet, footnotes)}</li>'
            for bet in briefing.strongest_bets
        )
        parts.append(
            f'<ol style="margin:0 0 20px;padding-left:20px;color:{CULTURE_COLOR_BODY};">{items}</ol>'
        )

    parts.append(render_restaurant_footer_html())
    return "\n".join(parts)


def render_restaurant_html(md_text: str, *, preheader_section: str = "This week's strongest bets") -> str:
    preheader = extract_preheader(md_text, section_name=preheader_section)
    body_html = render_restaurant_body_html(md_text)
    _, footnotes_md = split_footnotes(md_text)
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


def render_culture_html(
    md_text: str, *, preheader_section: str = "Top Picks", why_style: str = "callout"
) -> str:
    preheader = extract_preheader(md_text, section_name=preheader_section)
    body_html = render_culture_body_html(md_text, why_style=why_style)
    _, footnotes_md = split_footnotes(md_text)
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


def render_html(
    md_text: str,
    *,
    use_callouts: bool = True,
    preheader_section: str = "What Matters Today",
    briefing_type: str | None = None,
    culture_why_style: str = "callout",
) -> str:
    if briefing_type == "berlin-culture":
        return render_culture_html(
            md_text,
            preheader_section=preheader_section,
            why_style=culture_why_style,
        )
    if briefing_type == "berlin-restaurants":
        return render_restaurant_html(md_text, preheader_section=preheader_section)
    footnotes = parse_footnotes(md_text)
    body_md, footnotes_md = split_footnotes(md_text)
    body_md = normalize_horizontal_rules(body_md)
    prepared = preprocess_briefing_markdown(body_md, footnotes, use_callouts)
    preheader = extract_preheader(md_text, section_name=preheader_section)

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


def resolve_briefing_paths(explicit: str | None, changed_files: list[str]) -> list[Path]:
    if explicit:
        path = Path(explicit)
        return [path if path.is_absolute() else REPO_ROOT / path]

    candidates: list[Path] = []
    for raw in changed_files:
        if raw.endswith(".md") and raw.startswith("briefings/"):
            candidates.append(REPO_ROOT / raw)

    if not candidates:
        raise FileNotFoundError(
            "No briefing file specified and CHANGED_FILES is empty. "
            "Pass --file or fix changed-file detection in the workflow."
        )

    return sorted(candidates)


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
        briefing_paths = resolve_briefing_paths(args.file, changed_files)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    use_callouts_env = os.environ.get("BRIEFING_EMAIL_CALLOUTS", "true").lower() not in (
        "0",
        "false",
        "no",
    )
    use_callouts = (not args.no_callouts) and use_callouts_env
    callout_modes = [False, True] if args.dry_run and args.compare else [use_callouts]

    api_key = os.environ.get("RESEND_API_KEY")
    from_addr = os.environ.get("BRIEFING_FROM_EMAIL")
    to_raw = os.environ.get("BRIEFING_TO_EMAIL", "")

    if not args.dry_run and (not api_key or not from_addr or not to_raw):
        print("RESEND_API_KEY, BRIEFING_FROM_EMAIL, and BRIEFING_TO_EMAIL are required", file=sys.stderr)
        return 1

    to_addrs = [e.strip() for e in re.split(r"[,;]", to_raw) if e.strip()]

    for briefing_path in briefing_paths:
        if not briefing_path.exists():
            print(f"Briefing not found: {briefing_path}", file=sys.stderr)
            return 1

        print(f"Using briefing file: {briefing_path.relative_to(REPO_ROOT)}")
        md_text = briefing_path.read_text(encoding="utf-8")
        title = extract_title(md_text, briefing_path.stem)
        type_id = infer_type_from_briefing_path(briefing_path)
        preheader_section = "What Matters Today"
        if type_id:
            preheader_section = load_briefing_type(type_id).email_preheader_section or preheader_section

        if args.dry_run:
            previews: list[Path] = []
            if type_id == "berlin-culture":
                culture_variants: list[tuple[str, str, str]] = [("callout", ".preview", "callout why-it-fits")]
                if args.compare:
                    culture_variants.append(("minimal", ".preview-minimal", "minimal why-it-fits"))
                for why_style, suffix, label in culture_variants:
                    html = render_html(
                        md_text,
                        use_callouts=use_callouts,
                        preheader_section=preheader_section,
                        briefing_type=type_id,
                        culture_why_style=why_style,
                    )
                    preview = briefing_path.parent / f"{briefing_path.stem}{suffix}.html"
                    preview.write_text(html, encoding="utf-8")
                    previews.append(preview)
                    print(f"Wrote {label} preview: {preview}")
                    print(f"  file://{preview.resolve()}")
            elif type_id == "berlin-restaurants":
                html = render_html(
                    md_text,
                    use_callouts=use_callouts,
                    preheader_section=preheader_section,
                    briefing_type=type_id,
                )
                preview = briefing_path.parent / f"{briefing_path.stem}.preview.html"
                preview.write_text(html, encoding="utf-8")
                previews.append(preview)
                print(f"Wrote restaurant preview: {preview}")
                print(f"  file://{preview.resolve()}")
            else:
                for use_callouts in callout_modes if args.compare else callout_modes:
                    suffix = ".preview-callouts" if use_callouts else ".preview"
                    html = render_html(
                        md_text,
                        use_callouts=use_callouts,
                        preheader_section=preheader_section,
                        briefing_type=type_id,
                    )
                    preview = briefing_path.parent / f"{briefing_path.stem}{suffix}.html"
                    preview.write_text(html, encoding="utf-8")
                    previews.append(preview)
                    label = "callout boxes" if use_callouts else "plain"
                    print(f"Wrote {label} preview: {preview}")
                    print(f"  file://{preview.resolve()}")

            if args.open:
                import subprocess

                for preview in previews:
                    subprocess.run(["open", str(preview.resolve())], check=False)
            continue

        html = render_html(
            md_text,
            use_callouts=use_callouts,
            preheader_section=preheader_section,
            briefing_type=type_id,
        )
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
