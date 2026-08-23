#!/usr/bin/env python3
"""Unit tests for OpenAI Responses retry/backoff."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_openai_research import (  # noqa: E402
    create_response_with_retry,
    is_retryable_openai_error,
    retry_delay_seconds,
)


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class TestOpenAIRetry(unittest.TestCase):
    def test_retries_then_succeeds(self) -> None:
        client = MagicMock()
        client.responses.create.side_effect = [RuntimeError("429"), RuntimeError("429"), "ok"]
        with (
            patch("fetch_openai_research.is_retryable_openai_error", return_value=True),
            patch("fetch_openai_research.time.sleep") as slept,
        ):
            result = create_response_with_retry(client, model="gpt-5.4")
        self.assertEqual(result, "ok")
        self.assertEqual(client.responses.create.call_count, 3)
        self.assertEqual(slept.call_count, 2)

    def test_non_retryable_raises_immediately(self) -> None:
        client = MagicMock()
        client.responses.create.side_effect = ValueError("bad request")
        with patch("fetch_openai_research.is_retryable_openai_error", return_value=False):
            with self.assertRaises(ValueError):
                create_response_with_retry(client, model="gpt-5.4")
        self.assertEqual(client.responses.create.call_count, 1)

    def test_retry_delay_honors_retry_after(self) -> None:
        exc = RuntimeError("slow down")
        exc.response = MagicMock()
        exc.response.headers = {"Retry-After": "8"}
        self.assertGreaterEqual(retry_delay_seconds(exc, 1), 8.0)

    def test_generic_errors_are_not_retryable(self) -> None:
        self.assertFalse(is_retryable_openai_error(ValueError("nope")))
        self.assertFalse(is_retryable_openai_error(_StatusError(400)))


if __name__ == "__main__":
    unittest.main()
