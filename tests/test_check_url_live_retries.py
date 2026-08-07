#!/usr/bin/env python3
"""Tests for transient retry behavior in check_url_live."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import requests  # noqa: E402
from culture_url_verify import check_url_live  # noqa: E402


class TestCheckUrlLiveRetries(unittest.TestCase):
    def test_retries_connection_error_then_succeeds(self) -> None:
        session = MagicMock()
        live = MagicMock()
        live.status_code = 200
        session.head.side_effect = [
            requests.ConnectionError("Remote end closed"),
            live,
        ]
        with patch("culture_url_verify.time.sleep"):
            ok, note = check_url_live(
                "https://example.com/event",
                session=session,
                retries=3,
                retry_delay_seconds=0,
            )
        self.assertTrue(ok)
        self.assertEqual(note, "")
        self.assertEqual(session.head.call_count, 2)

    def test_does_not_retry_http_404(self) -> None:
        session = MagicMock()
        dead = MagicMock()
        dead.status_code = 404
        session.head.return_value = dead
        # GET fallback also 404
        get_resp = MagicMock()
        get_resp.status_code = 404
        get_resp.iter_content.return_value = iter([])
        session.get.return_value = get_resp
        with patch("culture_url_verify.time.sleep"):
            ok, note = check_url_live(
                "https://example.com/missing",
                session=session,
                retries=3,
                retry_delay_seconds=0,
            )
        self.assertFalse(ok)
        self.assertIn("404", note)
        self.assertEqual(session.head.call_count, 1)


if __name__ == "__main__":
    unittest.main()
