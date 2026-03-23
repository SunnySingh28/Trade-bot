"""Centralised stream-name helpers.

Keeps the ``price:{symbol}`` / ``signal:{strategy_id}`` naming
conventions in one place so every service stays consistent.
"""

from __future__ import annotations


def price_stream(symbol: str) -> str:
    """Return the Redis Stream key for a symbol's price candles.

    >>> price_stream("EURUSD")
    'price:EURUSD'
    """
    return f"price:{symbol}"


def signal_stream(strategy_id: str) -> str:
    """Return the Redis Stream key for a strategy's signals.

    >>> signal_stream("ema_crossover")
    'signal:ema_crossover'
    """
    return f"signal:{strategy_id}"
