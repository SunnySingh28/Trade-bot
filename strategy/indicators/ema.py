"""Exponential Moving Average indicator."""

from __future__ import annotations

from typing import Any


class EMA:
    """Compute EMA incrementally from incoming candles."""

    def __init__(self, period: int, smoothing: float = 2.0) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period
        self.smoothing = smoothing
        self._value: float | None = None
        self._prev_value: float | None = None
        self._count = 0

    def update(self, candle: dict[str, Any]) -> None:
        price = float(candle["close"])
        self._prev_value = self._value
        if self._value is None:
            self._value = price
        else:
            k = self.smoothing / (self.period + 1)
            self._value = price * k + self._value * (1 - k)
        self._count += 1

    def value(self) -> float | None:
        if not self.ready():
            return None
        return self._value

    def prev_value(self) -> float | None:
        if self._count <= self.period:
            return None
        return self._prev_value

    def ready(self) -> bool:
        return self._count >= self.period
