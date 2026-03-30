from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from indicators import EMA, RSI, SMA


def _candle(close: float) -> dict[str, float]:
    return {"close": close}


def test_ema_ready_after_period() -> None:
    ema = EMA(period=3)
    ema.update(_candle(10.0))
    ema.update(_candle(11.0))
    assert ema.ready() is False
    ema.update(_candle(12.0))
    assert ema.ready() is True
    assert ema.value() is not None


def test_sma_value() -> None:
    sma = SMA(period=3)
    sma.update(_candle(1.0))
    sma.update(_candle(2.0))
    sma.update(_candle(3.0))
    assert sma.ready() is True
    assert sma.value() == pytest.approx(2.0)


def test_rsi_ready_after_period_changes() -> None:
    rsi = RSI(period=3)
    rsi.update(_candle(100.0))
    rsi.update(_candle(101.0))
    rsi.update(_candle(102.0))
    assert rsi.ready() is False
    rsi.update(_candle(101.0))
    assert rsi.ready() is True
    assert 0.0 <= float(rsi.value()) <= 100.0
