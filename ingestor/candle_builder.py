"""CandleBuilder — accumulates ticks into OHLCV candles.

Stateful builder that receives individual ticks and emits a completed
candle dict whenever a new time-interval boundary is crossed.  Pure
logic — no I/O, no Redis dependency.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


class CandleBuilder:
    """Accumulate ticks into fixed-interval OHLCV candles.

    Parameters
    ----------
    symbol : str
        Instrument identifier, e.g. ``"EURUSD"``.
    source : str
        Data-source tag, e.g. ``"binance"``.
    interval_seconds : int
        Candle width in seconds (e.g. 60 for 1-minute candles).

    Usage
    -----
    >>> builder = CandleBuilder("EURUSD", "binance", 60)
    >>> candle = builder.process_tick({"price": 1.08, "volume": 10, "timestamp": 1718000005})
    >>> candle is None  # first tick — no candle emitted yet
    True
    """

    __slots__ = (
        "symbol",
        "source",
        "interval_seconds",
        # current candle state
        "_open_ts",
        "_open",
        "_high",
        "_low",
        "_close",
        "_volume",
        "_tick_count",
        "_vwap_numerator",
    )

    def __init__(self, symbol: str, source: str, interval_seconds: int) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.symbol = symbol
        self.source = source
        self.interval_seconds = interval_seconds

        # No candle in progress yet
        self._open_ts: Optional[int] = None
        self._open: float = 0.0
        self._high: float = 0.0
        self._low: float = 0.0
        self._close: float = 0.0
        self._volume: float = 0.0
        self._tick_count: int = 0
        self._vwap_numerator: float = 0.0  # running Σ(price × volume)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ingest a single tick and optionally return a completed candle.

        Parameters
        ----------
        tick : dict
            Must contain ``price`` (float), ``volume`` (float), and
            ``timestamp`` (int, Unix epoch seconds).

        Returns
        -------
        dict or None
            A candle dict if the tick crossed an interval boundary,
            otherwise ``None``.
        """
        price: float = float(tick["price"])
        volume: float = float(tick["volume"])
        ts: int = int(tick["timestamp"])

        tick_interval = self._interval_start(ts)
        emitted: Optional[Dict[str, Any]] = None

        if self._open_ts is None:
            # Very first tick — just initialise, never emit.
            self._start_candle(price, volume, tick_interval)
            return None

        if tick_interval > self._open_ts:
            # New interval boundary crossed — seal the current candle.
            emitted = self._seal_candle()
            # Start a fresh candle with this tick.
            self._start_candle(price, volume, tick_interval)
        else:
            # Same interval — update running aggregates.
            self._update_candle(price, volume)

        return emitted

    @property
    def has_candle_in_progress(self) -> bool:
        """Return ``True`` if there is an un-emitted candle being built."""
        return self._open_ts is not None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _interval_start(self, timestamp: int) -> int:
        """Compute the interval boundary for a given timestamp."""
        return math.floor(timestamp / self.interval_seconds) * self.interval_seconds

    def _start_candle(self, price: float, volume: float, interval_ts: int) -> None:
        """Initialise a new candle with the first tick."""
        self._open_ts = interval_ts
        self._open = price
        self._high = price
        self._low = price
        self._close = price
        self._volume = volume
        self._tick_count = 1
        self._vwap_numerator = price * volume

    def _update_candle(self, price: float, volume: float) -> None:
        """Fold a tick into the candle currently being built."""
        if price > self._high:
            self._high = price
        if price < self._low:
            self._low = price
        self._close = price
        self._volume += volume
        self._tick_count += 1
        self._vwap_numerator += price * volume

    def _seal_candle(self) -> Dict[str, Any]:
        """Produce the completed candle dict."""
        vwap = (
            self._vwap_numerator / self._volume
            if self._volume > 0
            else self._close
        )
        return {
            "symbol": self.symbol,
            "source": self.source,
            "interval": self.interval_seconds,
            "timestamp": self._open_ts,
            "open": self._open,
            "high": self._high,
            "low": self._low,
            "close": self._close,
            "volume": self._volume,
            "tick_count": self._tick_count,
            "vwap": round(vwap, 8),
            "closed": True,
        }
