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
from culture_url_verify import check_url_live, is_transient_verify_note  # noqa: E402


def _ok_response() -> MagicMock:
    live = MagicMock()
    live.status_code = 200
    return live


def _http_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.iter_content.return_value = iter([])
    return resp


class TestCheckUrlLiveRetries(unittest.TestCase):
    def test_head_timeout_falls_back_to_get(self) -> None:
        session = MagicMock()
        session.head.side_effect = requests.ConnectTimeout("connect timed out")
        session.get.return_value = _ok_response()
        with patch("culture_url_verify.time.sleep"):
            ok, note = check_url_live(
                "https://www.smb.museum/exhibition",
                session=session,
                retries=3,
                retry_delay_seconds=0,
            )
        self.assertTrue(ok)
        self.assertEqual(note, "")
        self.assertEqual(session.head.call_count, 1)
        self.assertEqual(session.get.call_count, 1)

    def test_retries_connection_error_then_succeeds(self) -> None:
        session = MagicMock()
        session.head.side_effect = [
            requests.ConnectionError("Remote end closed"),
            _ok_response(),
        ]
        session.get.side_effect = requests.ConnectionError("Remote end closed")
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
        session.head.return_value = _http_response(404)
        session.get.return_value = _http_response(404)
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


class TestTransientVerifyNote(unittest.TestCase):
    def test_connection_pool_timeout_is_transient(self) -> None:
        note = (
            "HTTPSConnectionPool(host='www.smb.museum', port=443): "
            "Max retries exceeded with url: /en/museums-institutions/hamburger-"
        )
        self.assertTrue(is_transient_verify_note(note))

    def test_http_503_is_transient(self) -> None:
        self.assertTrue(is_transient_verify_note("HTTP 503"))

    def test_http_404_is_not_transient(self) -> None:
        self.assertFalse(is_transient_verify_note("HTTP 404"))

    def test_invalid_scheme_is_not_transient(self) -> None:
        self.assertFalse(is_transient_verify_note("invalid scheme"))


if __name__ == "__main__":
    unittest.main()
