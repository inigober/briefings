#!/usr/bin/env python3
"""Tests for culture briefing validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_culture_briefing import validate_briefing  # noqa: E402

CULTURE_BRIEFINGS_DIR = REPO_ROOT / "briefings/berlin-culture"


def latest_culture_briefing_path() -> Path | None:
    """Newest dated briefing (ignores *.test.md), matching CI validation."""
    candidates = sorted(
        p
        for p in CULTURE_BRIEFINGS_DIR.glob("*.md")
        if not p.name.endswith(".test.md")
    )
    return candidates[-1] if candidates else None


class TestValidateCultureBriefing(unittest.TestCase):
    def test_detects_duplicate_events(self) -> None:
        text = """# Berlin Culture Briefing — Week of June 17–23, 2026

## Top Picks

### Tirailleurs: Trials and Tribulations

**Venue:** HKW

**Date(s):** June 2026

**Time(s):** 19:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Tirailleurs](https://example.com/tirailleurs)

## Exhibitions Radar

### Tirailleurs: Trials and Tribulations

**Venue:** HKW

**Date(s):** June 2026

**Time(s):** 19:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Tirailleurs again](https://example.com/tirailleurs-exhib)
"""
        errors, warnings = validate_briefing(text)
        error_text = " ".join(errors)
        self.assertIn("Duplicate event", error_text)

    def test_latest_briefing_has_no_duplicate_errors(self) -> None:
        path = latest_culture_briefing_path()
        if path is None:
            self.skipTest("no culture briefings in repo")
        text = path.read_text(encoding="utf-8")
        errors, _warnings = validate_briefing(text)
        self.assertEqual(errors, [], f"{path.name} failed validation: {errors}")

    def test_clean_briefing_passes(self) -> None:
        text = """# Berlin Culture Briefing — Week of June 1–7, 2026

## Top Picks

### Show A

**Venue:** Venue One

**Date(s):** 4 June 2026

**Time(s):** 20:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show A](https://example.com/a)

## Exhibitions Radar

### Show B

**Venue:** Venue Two

**Date(s):** 1 May – 1 July 2026

**Time(s):** 11:00–19:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show B](https://example.com/b)

## Film & Screenings

### Show C

**Venue:** Kino Three

**Date(s):** 5 June 2026

**Time(s):** 21:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show C](https://example.com/c)

## Performing Arts

### Show D

**Venue:** Theatre Four

**Date(s):** 6 June 2026

**Time(s):** 19:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show D](https://example.com/d)

## Music

### Artist E

**Venue:** Club Five

**Date(s):** 7 June 2026

**Time(s):** 22:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Artist E](https://example.com/e)

## Wildcards

### Show F

**Venue:** Space Six

**Date(s):** 3 June 2026

**Time(s):** 18:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show F](https://example.com/f)
"""
        errors, warnings = validate_briefing(text)
        self.assertEqual(errors, [])
        self.assertFalse(any("Duplicate" in w for w in warnings))

    def test_exhibition_opening_only_dates_warn(self) -> None:
        text = """# Berlin Culture Briefing — Week of June 1–7, 2026

## Top Picks

### Show A

**Venue:** Venue One

**Date(s):** 4 June 2026

**Time(s):** 20:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show A](https://example.com/a)

## Exhibitions Radar

### Long Show

**Venue:** Venue Two

**Date(s):** Opening Thursday, 17 September 2026

**Time(s):** 19:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Long Show](https://example.com/b)

## Film & Screenings

### Show C

**Venue:** Kino Three

**Date(s):** 5 June 2026

**Time(s):** 21:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show C](https://example.com/c)

## Performing Arts

### Show D

**Venue:** Theatre Four

**Date(s):** 6 June 2026

**Time(s):** 19:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show D](https://example.com/d)

## Music

### Artist E

**Venue:** Club Five

**Date(s):** 7 June 2026

**Time(s):** 22:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Artist E](https://example.com/e)

## Wildcards

### Show F

**Venue:** Space Six

**Date(s):** 3 June 2026

**Time(s):** 18:00

**Short Context:** Context.

**Why It Fits:** Fit.

**Official Link:** [Show F](https://example.com/f)
"""
        errors, warnings = validate_briefing(text)
        self.assertEqual(errors, [])
        warning_text = " ".join(warnings)
        self.assertIn("missing a closing/end date", warning_text)
        self.assertIn("Long Show", warning_text)

    def test_exhibition_run_dates_do_not_warn(self) -> None:
        from validate_culture_briefing import exhibition_dates_missing_end

        self.assertFalse(
            exhibition_dates_missing_end("11 September – 22 November 2026 (opened 10 September)")
        )
        self.assertFalse(
            exhibition_dates_missing_end("3 July – 14 August 2026 (closes Thursday)")
        )
        self.assertTrue(
            exhibition_dates_missing_end("Opening Thursday, 17 September 2026")
        )
        self.assertTrue(exhibition_dates_missing_end("Saturday, 19 September 2026"))


if __name__ == "__main__":
    unittest.main()
