"""Simple Moving Average indicator."""

from __future__ import annotations

from collections import deque
from typing import Any


class SMA:
    """Compute SMA over a fixed rolling window."""

    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period
        self._values: deque[float] = deque(maxlen=period)
        self._sum = 0.0
        self._value: float | None = None
        self._prev_value: float | None = None
        self._updates = 0

    def update(self, candle: dict[str, Any]) -> None:
        price = float(candle["close"])
        self._prev_value = self._value

        if len(self._values) == self.period:
            self._sum -= self._values[0]

        self._values.append(price)
        self._sum += price

        if self.ready():
            self._value = self._sum / self.period
        else:
            self._value = None
        self._updates += 1

    def value(self) -> float | None:
        return self._value

    def prev_value(self) -> float | None:
        if self._updates <= self.period:
            return None
        return self._prev_value

    def ready(self) -> bool:
        return len(self._values) >= self.period
