"""Unit tests for pubsub.publisher.StreamPublisher."""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import MagicMock, patch

import redis as _redis

from pubsub.publisher import StreamPublisher


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def publisher(mock_redis):
    return StreamPublisher(mock_redis)


SAMPLE_CANDLE = {
    "symbol": "EURUSD",
    "source": "binance",
    "timestamp": 1718000000,
    "open": 1.0821,
    "high": 1.0834,
    "low": 1.0819,
    "close": 1.0829,
    "volume": 1024.0,
}

SAMPLE_SIGNAL = {
    "symbol": "EURUSD",
    "strategy_id": "ema_crossover",
    "type": 1,
    "timestamp": 1718000000,
    "message": "EMA20 crossed above EMA50, close=1.0829",
}


# ── Generic publish ─────────────────────────────────────────────────

class TestPublish:
    def test_calls_xadd_with_stringified_values(self, publisher, mock_redis):
        mock_redis.xadd.return_value = "1718000000-0"

        result = publisher.publish("test:stream", {"key": 42, "val": 3.14})

        mock_redis.xadd.assert_called_once_with(
            "test:stream", {"key": "42", "val": "3.14"},
        )
        assert result == "1718000000-0"

    def test_returns_none_on_redis_error(self, publisher, mock_redis):
        mock_redis.xadd.side_effect = _redis.exceptions.RedisError("boom")

        result = publisher.publish("stream", {"a": "b"})

        assert result is None

    def test_does_not_raise_on_redis_error(self, publisher, mock_redis):
        mock_redis.xadd.side_effect = _redis.exceptions.RedisError("boom")

        # Should not raise
        publisher.publish("stream", {"a": "b"})


# ── Convenience methods ──────────────────────────────────────────────

class TestPublishPrice:
    def test_derives_stream_from_symbol(self, publisher, mock_redis):
        mock_redis.xadd.return_value = "id-1"

        publisher.publish_price(SAMPLE_CANDLE)

        stream_arg = mock_redis.xadd.call_args[0][0]
        assert stream_arg == "price:EURUSD"

    def test_returns_message_id(self, publisher, mock_redis):
        mock_redis.xadd.return_value = "id-1"

        result = publisher.publish_price(SAMPLE_CANDLE)
        assert result == "id-1"


class TestPublishSignal:
    def test_derives_stream_from_strategy_id(self, publisher, mock_redis):
        mock_redis.xadd.return_value = "id-2"

        publisher.publish_signal(SAMPLE_SIGNAL)

        stream_arg = mock_redis.xadd.call_args[0][0]
        assert stream_arg == "signal:ema_crossover"

    def test_stringifies_signal_fields(self, publisher, mock_redis):
        mock_redis.xadd.return_value = "id-2"

        publisher.publish_signal(SAMPLE_SIGNAL)

        payload = mock_redis.xadd.call_args[0][1]
        assert payload["type"] == "1"
        assert payload["timestamp"] == "1718000000"
