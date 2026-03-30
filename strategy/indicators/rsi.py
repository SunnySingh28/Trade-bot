"""Relative Strength Index (RSI) indicator."""

from __future__ import annotations

from typing import Any


class RSI:
    """Compute RSI with Wilder's smoothing."""

    def __init__(self, period: int = 14) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period
        self._prev_close: float | None = None
        self._avg_gain: float | None = None
        self._avg_loss: float | None = None
        self._seed_gains = 0.0
        self._seed_losses = 0.0
        self._seed_count = 0
        self._value: float | None = None

    def update(self, candle: dict[str, Any]) -> None:
        close = float(candle["close"])
        if self._prev_close is None:
            self._prev_close = close
            return

        change = close - self._prev_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if self._avg_gain is None or self._avg_loss is None:
            self._seed_gains += gain
            self._seed_losses += loss
            self._seed_count += 1
            if self._seed_count == self.period:
                self._avg_gain = self._seed_gains / self.period
                self._avg_loss = self._seed_losses / self.period
                self._value = self._compute_rsi(self._avg_gain, self._avg_loss)
        else:
            self._avg_gain = ((self._avg_gain * (self.period - 1)) + gain) / self.period
            self._avg_loss = ((self._avg_loss * (self.period - 1)) + loss) / self.period
            self._value = self._compute_rsi(self._avg_gain, self._avg_loss)

        self._prev_close = close

    def value(self) -> float | None:
        return self._value

    def ready(self) -> bool:
        return self._value is not None

    @staticmethod
    def _compute_rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
