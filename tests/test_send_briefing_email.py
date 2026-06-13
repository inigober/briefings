from scripts.briefing_paths import load_briefing_type
from scripts.send_briefing_email import format_email_subject


def test_format_email_subject_adds_emoji():
    assert format_email_subject("News — 13 June 2026", "📰") == "📰 News — 13 June 2026"


def test_format_email_subject_idempotent():
    title = "📰 News — 13 June 2026"
    assert format_email_subject(title, "📰") == title


def test_format_email_subject_empty_emoji():
    assert format_email_subject("News — 13 June 2026", "") == "News — 13 June 2026"


def test_briefing_types_have_subject_emoji():
    assert load_briefing_type("news").email_subject_emoji == "📰"
    assert load_briefing_type("berlin-culture").email_subject_emoji == "🎭"
    assert load_briefing_type("berlin-restaurants").email_subject_emoji == "🍽️"
