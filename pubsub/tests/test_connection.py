"""Unit tests for pubsub.connection.connect_redis."""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import MagicMock, patch, PropertyMock

from pubsub.connection import connect_redis


# ── Helpers ──────────────────────────────────────────────────────────

def _make_mock_redis(fail_count: int = 0):
    """Return a mock Redis class whose ``ping`` fails *fail_count* times."""
    mock_client = MagicMock()
    call_count = {"n": 0}

    import redis as _redis

    def _ping():
        call_count["n"] += 1
        if call_count["n"] <= fail_count:
            raise _redis.exceptions.ConnectionError("not ready")

    mock_client.ping = _ping
    return mock_client


# ── Tests ────────────────────────────────────────────────────────────

class TestConnectSuccess:
    """Connection succeeds on the first attempt."""

    @patch("pubsub.connection.redis.Redis")
    def test_returns_client(self, mock_redis_cls):
        mock_client = MagicMock()
        mock_redis_cls.return_value = mock_client

        client = connect_redis(host="localhost", port=6379, retries=3, delay=0)

        assert client is mock_client
        mock_client.ping.assert_called_once()

    @patch("pubsub.connection.redis.Redis")
    def test_decode_responses_enabled(self, mock_redis_cls):
        mock_client = MagicMock()
        mock_redis_cls.return_value = mock_client

        connect_redis(host="localhost", port=6379, retries=1, delay=0)

        mock_redis_cls.assert_called_once_with(
            host="localhost", port=6379, decode_responses=True,
        )


class TestConnectRetry:
    """Connection succeeds after transient failures."""

    @patch("pubsub.connection.time.sleep")
    @patch("pubsub.connection.redis.Redis")
    def test_succeeds_after_failures(self, mock_redis_cls, mock_sleep):
        mock_client = _make_mock_redis(fail_count=2)
        mock_redis_cls.return_value = mock_client

        client = connect_redis(host="h", port=1, retries=5, delay=1)

        assert client is mock_client
        # Two failures → two sleeps
        assert mock_sleep.call_count == 2

    @patch("pubsub.connection.time.sleep")
    @patch("pubsub.connection.redis.Redis")
    def test_exponential_backoff(self, mock_redis_cls, mock_sleep):
        mock_client = _make_mock_redis(fail_count=3)
        mock_redis_cls.return_value = mock_client

        connect_redis(host="h", port=1, retries=5, delay=2)

        # Delays: 2*1=2, 2*2=4, 2*4=8
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert delays == [2.0, 4.0, 8.0]


class TestConnectFailure:
    """Connection exhausts retries and raises RuntimeError."""

    @patch("pubsub.connection.time.sleep")
    @patch("pubsub.connection.redis.Redis")
    def test_raises_runtime_error(self, mock_redis_cls, mock_sleep):
        mock_client = _make_mock_redis(fail_count=999)
        mock_redis_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="Could not connect"):
            connect_redis(host="h", port=1, retries=3, delay=0)

    @patch("pubsub.connection.time.sleep")
    @patch("pubsub.connection.redis.Redis")
    def test_attempts_exact_retry_count(self, mock_redis_cls, mock_sleep):
        mock_client = _make_mock_redis(fail_count=999)
        mock_redis_cls.return_value = mock_client

        with pytest.raises(RuntimeError):
            connect_redis(host="h", port=1, retries=4, delay=0)

        assert mock_sleep.call_count == 4
