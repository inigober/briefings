#!/usr/bin/env python3
"""Tests for email delivery log and undelivered detection."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from email_delivery import (  # noqa: E402
    find_undelivered_briefings,
    load_delivery_log,
    record_delivery,
)


class TestEmailDelivery(unittest.TestCase):
    def test_record_and_find_undelivered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            briefings = root / "briefings" / "berlin-culture"
            briefings.mkdir(parents=True)
            delivered = briefings / "2026-08-06.md"
            missing = briefings / "2026-08-04.md"
            delivered.write_text("# ok\n", encoding="utf-8")
            missing.write_text("# missing email\n", encoding="utf-8")

            log_path = root / "state" / "email_delivery.json"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "started_at": "2026-08-04T00:00:00+00:00",
                        "deliveries": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                patch("email_delivery.REPO_ROOT", root),
                patch("email_delivery.load_manifest", return_value={"berlin-culture": {}}),
            ):
                record_delivery(
                    delivered,
                    resend_id="abc",
                    subject="Culture",
                    path=log_path,
                )
                data = load_delivery_log(log_path)
                self.assertEqual(len(data["deliveries"]), 1)
                self.assertEqual(
                    data["deliveries"][0]["path"],
                    "briefings/berlin-culture/2026-08-06.md",
                )

                undelivered = find_undelivered_briefings(
                    lookback_days=30,
                    log_path=log_path,
                    repo_root=root,
                )
                self.assertEqual(
                    [p.name for p in undelivered],
                    ["2026-08-04.md"],
                )


if __name__ == "__main__":
    unittest.main()
