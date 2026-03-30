"""EMA crossover strategy."""

from __future__ import annotations

from collections import deque
from typing import Any

from indicators import EMA

STRATEGY_ID = "ema_crossover"
FAST_PERIOD = 20
SLOW_PERIOD = 50
DEDUP_WINDOW = 3
LOOKBACK = SLOW_PERIOD


def indicators() -> dict[str, Any]:
    """Instantiate all indicators used by this strategy."""
    return {
        "ema_fast": EMA(period=FAST_PERIOD),
        "ema_slow": EMA(period=SLOW_PERIOD),
    }


def evaluate(candles: deque[dict[str, Any]], inds: dict[str, Any]) -> dict[str, Any] | None:
    """Evaluate the current candle window and indicator state."""
    fast = inds["ema_fast"]
    slow = inds["ema_slow"]

    if not (fast.ready() and slow.ready()):
        return None

    prev_fast = fast.prev_value()
    prev_slow = slow.prev_value()
    curr_fast = fast.value()
    curr_slow = slow.value()
    if None in (prev_fast, prev_slow, curr_fast, curr_slow):
        return None

    close = float(candles[-1]["close"])

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return {
            "type": 1,
            "message": f"EMA{FAST_PERIOD} crossed above EMA{SLOW_PERIOD}, close={close}",
        }
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return {
            "type": 2,
            "message": f"EMA{FAST_PERIOD} crossed below EMA{SLOW_PERIOD}, close={close}",
        }
    return None
