"""Unit tests for pubsub.streams — stream name helpers."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pubsub.streams import price_stream, signal_stream


class TestPriceStream:
    def test_eurusd(self):
        assert price_stream("EURUSD") == "price:EURUSD"

    def test_btcusdt(self):
        assert price_stream("BTCUSDT") == "price:BTCUSDT"

    def test_preserves_case(self):
        assert price_stream("ethUsdt") == "price:ethUsdt"


class TestSignalStream:
    def test_ema_crossover(self):
        assert signal_stream("ema_crossover") == "signal:ema_crossover"

    def test_rsi_bounce(self):
        assert signal_stream("rsi_bounce") == "signal:rsi_bounce"
