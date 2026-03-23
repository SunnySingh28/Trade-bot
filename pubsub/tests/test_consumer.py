"""Unit tests for pubsub.consumer.StreamConsumer."""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import MagicMock, call

from pubsub.consumer import StreamConsumer


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    return MagicMock()


# ── poll() ───────────────────────────────────────────────────────────

class TestPoll:
    def test_returns_parsed_entries(self, mock_redis):
        mock_redis.xread.return_value = [
            ("price:EURUSD", [
                ("1-0", {"symbol": "EURUSD", "close": "1.08"}),
                ("2-0", {"symbol": "EURUSD", "close": "1.09"}),
            ]),
        ]
        consumer = StreamConsumer(mock_redis, {"price:EURUSD": "0"})

        entries = consumer.poll()

        assert len(entries) == 2
        assert entries[0] == ("price:EURUSD", "1-0", {"symbol": "EURUSD", "close": "1.08"})
        assert entries[1] == ("price:EURUSD", "2-0", {"symbol": "EURUSD", "close": "1.09"})

    def test_advances_cursor(self, mock_redis):
        mock_redis.xread.return_value = [
            ("price:EURUSD", [
                ("5-0", {"a": "b"}),
            ]),
        ]
        consumer = StreamConsumer(mock_redis, {"price:EURUSD": "0"})

        consumer.poll()

        assert consumer.cursors["price:EURUSD"] == "5-0"

    def test_returns_empty_on_timeout(self, mock_redis):
        mock_redis.xread.return_value = None
        consumer = StreamConsumer(mock_redis, {"price:EURUSD": "0"})

        entries = consumer.poll()

        assert entries == []

    def test_multi_stream(self, mock_redis):
        mock_redis.xread.return_value = [
            ("price:EURUSD", [("1-0", {"x": "1"})]),
            ("signal:ema_crossover", [("2-0", {"y": "2"})]),
        ]
        consumer = StreamConsumer(
            mock_redis,
            {"price:EURUSD": "0", "signal:ema_crossover": "0"},
        )

        entries = consumer.poll()

        assert len(entries) == 2
        assert consumer.cursors["price:EURUSD"] == "1-0"
        assert consumer.cursors["signal:ema_crossover"] == "2-0"

    def test_xread_called_with_correct_params(self, mock_redis):
        mock_redis.xread.return_value = None
        consumer = StreamConsumer(
            mock_redis,
            {"price:EURUSD": "0"},
            block_ms=1000,
            count=50,
        )

        consumer.poll()

        mock_redis.xread.assert_called_once_with(
            {"price:EURUSD": "0"}, block=1000, count=50,
        )


# ── consume() ────────────────────────────────────────────────────────

class TestConsume:
    def test_invokes_callback_per_message(self, mock_redis):
        call_log = []

        # First poll returns two messages, second poll triggers stop.
        mock_redis.xread.side_effect = [
            [("price:EURUSD", [
                ("1-0", {"a": "1"}),
                ("2-0", {"a": "2"}),
            ])],
            None,
        ]

        consumer = StreamConsumer(mock_redis, {"price:EURUSD": "0"})
        poll_count = {"n": 0}

        def stop():
            poll_count["n"] += 1
            return poll_count["n"] >= 2

        consumer.consume(lambda s, m, f: call_log.append((s, m, f)), stop=stop)

        assert len(call_log) == 2
        assert call_log[0] == ("price:EURUSD", "1-0", {"a": "1"})
        assert call_log[1] == ("price:EURUSD", "2-0", {"a": "2"})

    def test_stops_when_stop_returns_true(self, mock_redis):
        mock_redis.xread.return_value = None
        consumer = StreamConsumer(mock_redis, {"price:EURUSD": "0"})

        consumer.consume(lambda s, m, f: None, stop=lambda: True)

        # Should have polled once and then stopped
        assert mock_redis.xread.call_count == 1


# ── cursors property ─────────────────────────────────────────────────

class TestCursors:
    def test_returns_copy(self, mock_redis):
        consumer = StreamConsumer(mock_redis, {"price:EURUSD": "0"})
        cursors = consumer.cursors
        cursors["price:EURUSD"] = "MODIFIED"

        assert consumer.cursors["price:EURUSD"] == "0"
