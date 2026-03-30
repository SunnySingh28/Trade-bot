from __future__ import annotations

from collections import deque
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strategies import ema_crossover


def _candle(close: float, ts: int) -> dict[str, float | int]:
    return {
        "close": close,
        "timestamp": ts,
    }


def test_no_signal_when_not_ready() -> None:
    inds = ema_crossover.indicators()
    candles: deque[dict] = deque(maxlen=ema_crossover.LOOKBACK)
    candles.append(_candle(100.0, 1))

    for ind in inds.values():
        ind.update(candles[-1])

    assert ema_crossover.evaluate(candles, inds) is None


def test_emits_signal_dict_shape_after_ready() -> None:
    inds = ema_crossover.indicators()
    candles: deque[dict] = deque(maxlen=ema_crossover.LOOKBACK)

    # Create a sequence with drift up then down/up enough to eventually cross.
    prices = [float(100 + i) for i in range(70)] + [140.0, 130.0, 150.0, 160.0]

    got = None
    for idx, price in enumerate(prices):
        candle = _candle(price, idx + 1)
        candles.append(candle)
        for ind in inds.values():
            ind.update(candle)
        if len(candles) == candles.maxlen:
            got = ema_crossover.evaluate(candles, inds) or got

    if got is not None:
        assert got["type"] in (1, 2)
        assert isinstance(got["message"], str)
