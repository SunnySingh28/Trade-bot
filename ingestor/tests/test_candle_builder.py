"""Unit tests for CandleBuilder.

Tests cover:
    - First tick initialisation (no emit)
    - Same-interval tick accumulation
    - Interval boundary crossing and candle emission
    - OHLCV correctness
    - Enhanced fields: interval, tick_count, vwap, closed
    - Gap handling (ticks far apart)
    - Single-tick candles
    - Zero-volume edge case for VWAP
"""

from __future__ import annotations

import math
import sys
import os

import pytest

# Ensure the ingestor package is importable from the test directory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from candle_builder import CandleBuilder


# ── Helpers ──────────────────────────────────────────────────────────

def _tick(price: float, volume: float, timestamp: int) -> dict:
    return {"price": price, "volume": volume, "timestamp": timestamp}


SYMBOL = "EURUSD"
SOURCE = "binance"
INTERVAL = 60  # seconds


@pytest.fixture
def builder() -> CandleBuilder:
    return CandleBuilder(SYMBOL, SOURCE, INTERVAL)


# ── Basic lifecycle ──────────────────────────────────────────────────

class TestFirstTick:
    """The very first tick initialises a candle but never emits one."""

    def test_returns_none(self, builder: CandleBuilder) -> None:
        result = builder.process_tick(_tick(1.0821, 10, 1718000005))
        assert result is None

    def test_marks_candle_in_progress(self, builder: CandleBuilder) -> None:
        builder.process_tick(_tick(1.0821, 10, 1718000005))
        assert builder.has_candle_in_progress


class TestSameInterval:
    """Ticks within the same interval accumulate without emitting."""

    def test_no_emission(self, builder: CandleBuilder) -> None:
        builder.process_tick(_tick(1.0821, 10, 1718000005))
        result = builder.process_tick(_tick(1.0830, 15, 1718000030))
        assert result is None

    def test_still_one_candle_in_progress(self, builder: CandleBuilder) -> None:
        builder.process_tick(_tick(1.0821, 10, 1718000005))
        builder.process_tick(_tick(1.0830, 15, 1718000030))
        assert builder.has_candle_in_progress


# ── Candle emission ─────────────────────────────────────────────────

class TestCandelEmission:
    """A tick crossing an interval boundary seals the current candle."""

    def test_emits_candle_on_new_interval(self, builder: CandleBuilder) -> None:
        # Two ticks in interval 1718000000-1718000059
        builder.process_tick(_tick(1.0821, 10, 1718000005))
        builder.process_tick(_tick(1.0834, 20, 1718000030))
        # Third tick in next interval (1718000060+)
        candle = builder.process_tick(_tick(1.0829, 5, 1718000065))
        assert candle is not None

    def test_candle_fields_correct(self, builder: CandleBuilder) -> None:
        # Interval: floor(1717999980/60)*60 = 1717999980 → [1717999980, 1718000040)
        builder.process_tick(_tick(1.0821, 10, 1717999980))  # open — exact boundary
        builder.process_tick(_tick(1.0834, 20, 1717999995))  # high
        builder.process_tick(_tick(1.0819, 15, 1718000010))  # low
        builder.process_tick(_tick(1.0829, 5, 1718000030))   # close
        # Crosses into next interval (1718000040):
        candle = builder.process_tick(_tick(1.0800, 10, 1718000045))

        assert candle["symbol"] == SYMBOL
        assert candle["source"] == SOURCE
        assert candle["timestamp"] == 1717999980
        assert candle["open"] == 1.0821
        assert candle["high"] == 1.0834
        assert candle["low"] == 1.0819
        assert candle["close"] == 1.0829
        assert candle["volume"] == pytest.approx(50.0)  # 10+20+15+5

    def test_enhanced_fields(self, builder: CandleBuilder) -> None:
        builder.process_tick(_tick(100.0, 2.0, 1718000005))
        builder.process_tick(_tick(200.0, 3.0, 1718000030))
        candle = builder.process_tick(_tick(150.0, 1.0, 1718000065))

        assert candle["interval"] == INTERVAL
        assert candle["tick_count"] == 2
        assert candle["closed"] is True
        # VWAP = (100*2 + 200*3) / (2+3) = 800/5 = 160.0
        assert candle["vwap"] == pytest.approx(160.0)


# ── Edge cases ───────────────────────────────────────────────────────

class TestGapHandling:
    """A tick far in the future emits the current candle without synthesising gaps."""

    def test_gap_emits_single_candle(self, builder: CandleBuilder) -> None:
        # floor(1717999980/60)*60 = 1717999980
        builder.process_tick(_tick(1.0821, 10, 1717999980))
        # Jump 10 minutes forward
        candle = builder.process_tick(_tick(1.0900, 5, 1718000605))

        assert candle is not None
        assert candle["timestamp"] == 1717999980
        assert candle["tick_count"] == 1

    def test_gap_does_not_synthesise_missing(self, builder: CandleBuilder) -> None:
        builder.process_tick(_tick(1.0821, 10, 1718000005))
        candle = builder.process_tick(_tick(1.0900, 5, 1718000605))
        # Only one candle emitted — not 10.
        assert candle is not None
        # The next process_tick should return None (new candle in progress)
        result = builder.process_tick(_tick(1.0910, 5, 1718000620))
        assert result is None


class TestSingleTickCandle:
    """A candle built from exactly one tick is valid."""

    def test_single_tick_candle(self, builder: CandleBuilder) -> None:
        builder.process_tick(_tick(42850.25, 0.5, 1718000005))
        candle = builder.process_tick(_tick(42900.00, 0.3, 1718000065))

        assert candle["open"] == 42850.25
        assert candle["high"] == 42850.25
        assert candle["low"] == 42850.25
        assert candle["close"] == 42850.25
        assert candle["volume"] == pytest.approx(0.5)
        assert candle["tick_count"] == 1
        # VWAP for single tick = price itself
        assert candle["vwap"] == pytest.approx(42850.25)


class TestZeroVolumeTick:
    """VWAP computation handles zero-volume gracefully."""

    def test_zero_volume_vwap_fallback(self, builder: CandleBuilder) -> None:
        builder.process_tick(_tick(100.0, 0.0, 1718000005))
        candle = builder.process_tick(_tick(200.0, 1.0, 1718000065))

        # volume == 0 → vwap falls back to close price
        assert candle["vwap"] == pytest.approx(candle["close"])


class TestMultipleEmissions:
    """Builder correctly emits candles across several intervals."""

    def test_three_consecutive_candles(self, builder: CandleBuilder) -> None:
        # Candle 1: interval 1718000000
        builder.process_tick(_tick(10.0, 1.0, 1718000005))
        # Candle 2: interval 1718000060
        c1 = builder.process_tick(_tick(20.0, 2.0, 1718000065))
        assert c1 is not None
        assert c1["close"] == 10.0

        # Candle 3: interval 1718000120
        c2 = builder.process_tick(_tick(30.0, 3.0, 1718000125))
        assert c2 is not None
        assert c2["close"] == 20.0

        # One more to flush
        c3 = builder.process_tick(_tick(40.0, 4.0, 1718000185))
        assert c3 is not None
        assert c3["close"] == 30.0


# ── Constructor validation ───────────────────────────────────────────

class TestConstructor:
    def test_zero_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            CandleBuilder("X", "src", 0)

    def test_negative_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            CandleBuilder("X", "src", -5)
