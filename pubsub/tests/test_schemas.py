"""Unit tests for pubsub.schemas — PriceMessage, SignalMessage, validators."""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pubsub.schemas import (
    PriceMessage,
    SignalMessage,
    validate_price_message,
    validate_signal_message,
)


# ── PriceMessage ─────────────────────────────────────────────────────

class TestPriceMessageRoundTrip:
    def test_to_stream_dict_all_strings(self):
        msg = PriceMessage(
            symbol="EURUSD", source="binance", timestamp=1718000000,
            open=1.0821, high=1.0834, low=1.0819, close=1.0829, volume=1024.0,
        )
        d = msg.to_stream_dict()

        assert all(isinstance(v, str) for v in d.values())
        assert d["timestamp"] == "1718000000"
        assert d["open"] == "1.0821"

    def test_from_stream_dict_typed(self):
        raw = {
            "symbol": "EURUSD", "source": "binance", "timestamp": "1718000000",
            "open": "1.0821", "high": "1.0834", "low": "1.0819",
            "close": "1.0829", "volume": "1024.0",
        }
        msg = PriceMessage.from_stream_dict(raw)

        assert msg.symbol == "EURUSD"
        assert msg.timestamp == 1718000000
        assert isinstance(msg.open, float)
        assert msg.volume == 1024.0

    def test_round_trip(self):
        original = PriceMessage(
            symbol="BTCUSDT", source="kraken", timestamp=1718000060,
            open=42850.0, high=42900.0, low=42800.0, close=42875.5,
            volume=12.5,
        )
        restored = PriceMessage.from_stream_dict(original.to_stream_dict())

        assert restored == original


# ── SignalMessage ────────────────────────────────────────────────────

class TestSignalMessageRoundTrip:
    def test_to_stream_dict_all_strings(self):
        msg = SignalMessage(
            symbol="EURUSD", strategy_id="ema_crossover", type=1,
            timestamp=1718000000, message="buy signal",
        )
        d = msg.to_stream_dict()

        assert d["type"] == "1"
        assert d["strategy_id"] == "ema_crossover"

    def test_from_stream_dict_typed(self):
        raw = {
            "symbol": "EURUSD", "strategy_id": "ema_crossover",
            "type": "2", "timestamp": "1718000000",
            "message": "sell signal",
        }
        msg = SignalMessage.from_stream_dict(raw)

        assert msg.type == 2
        assert isinstance(msg.timestamp, int)

    def test_round_trip(self):
        original = SignalMessage(
            symbol="BTCUSDT", strategy_id="rsi_bounce", type=2,
            timestamp=1718000120, message="RSI below 30",
        )
        restored = SignalMessage.from_stream_dict(original.to_stream_dict())

        assert restored == original


# ── validate_price_message ───────────────────────────────────────────

class TestValidatePriceMessage:
    def test_valid_message_passes(self):
        data = {
            "symbol": "EURUSD", "source": "binance", "timestamp": 1718000000,
            "open": 1.08, "high": 1.09, "low": 1.07, "close": 1.08,
            "volume": 100.0,
        }
        validate_price_message(data)  # should not raise

    def test_missing_field_raises(self):
        data = {"symbol": "EURUSD", "source": "binance"}
        with pytest.raises(ValueError, match="Missing price message fields"):
            validate_price_message(data)

    def test_bad_timestamp_raises(self):
        data = {
            "symbol": "X", "source": "s", "timestamp": "not-a-number",
            "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1,
        }
        with pytest.raises(ValueError, match="Invalid timestamp"):
            validate_price_message(data)

    def test_bad_float_field_raises(self):
        data = {
            "symbol": "X", "source": "s", "timestamp": 100,
            "open": "bad", "high": 1, "low": 1, "close": 1, "volume": 1,
        }
        with pytest.raises(ValueError, match="Invalid open"):
            validate_price_message(data)

    def test_string_numbers_accepted(self):
        data = {
            "symbol": "X", "source": "s", "timestamp": "100",
            "open": "1.5", "high": "2.0", "low": "0.5",
            "close": "1.8", "volume": "10",
        }
        validate_price_message(data)  # should not raise


# ── validate_signal_message ──────────────────────────────────────────

class TestValidateSignalMessage:
    def test_valid_message_passes(self):
        data = {
            "symbol": "EURUSD", "strategy_id": "ema_crossover",
            "type": 1, "timestamp": 100, "message": "buy",
        }
        validate_signal_message(data)  # should not raise

    def test_missing_field_raises(self):
        data = {"symbol": "EURUSD"}
        with pytest.raises(ValueError, match="Missing signal message fields"):
            validate_signal_message(data)

    def test_invalid_type_value_raises(self):
        data = {
            "symbol": "X", "strategy_id": "s", "type": 3,
            "timestamp": 100, "message": "m",
        }
        with pytest.raises(ValueError, match="must be 1.*or 2"):
            validate_signal_message(data)

    def test_non_numeric_type_raises(self):
        data = {
            "symbol": "X", "strategy_id": "s", "type": "abc",
            "timestamp": 100, "message": "m",
        }
        with pytest.raises(ValueError, match="Invalid signal type"):
            validate_signal_message(data)

    def test_bad_timestamp_raises(self):
        data = {
            "symbol": "X", "strategy_id": "s", "type": 1,
            "timestamp": "nope", "message": "m",
        }
        with pytest.raises(ValueError, match="Invalid timestamp"):
            validate_signal_message(data)
