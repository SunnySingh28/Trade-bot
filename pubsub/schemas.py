"""Message schemas for Redis Streams messages.

Provides typed dataclasses whose ``to_stream_dict`` / ``from_stream_dict``
methods handle the string ↔ native-type conversion that Redis Streams require.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


# ── Price message ────────────────────────────────────────────────────

_PRICE_REQUIRED_FIELDS = frozenset(
    {"symbol", "source", "timestamp", "open", "high", "low", "close", "volume"}
)


@dataclass(slots=True)
class PriceMessage:
    """A completed OHLCV candle published to a price stream."""

    symbol: str
    source: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    # -- serialisation -----------------------------------------------------

    def to_stream_dict(self) -> Dict[str, str]:
        """Convert to a ``{field: string}`` dict suitable for ``XADD``."""
        return {
            "symbol": self.symbol,
            "source": self.source,
            "timestamp": str(self.timestamp),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
        }

    @classmethod
    def from_stream_dict(cls, data: Dict[str, str]) -> "PriceMessage":
        """Parse a stream entry back into a typed ``PriceMessage``."""
        return cls(
            symbol=data["symbol"],
            source=data["source"],
            timestamp=int(data["timestamp"]),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data["volume"]),
        )


# ── Signal message ───────────────────────────────────────────────────

_SIGNAL_REQUIRED_FIELDS = frozenset(
    {"symbol", "strategy_id", "type", "timestamp", "message"}
)


@dataclass(slots=True)
class SignalMessage:
    """A trading signal published to a signal stream."""

    symbol: str
    strategy_id: str
    type: int          # 1 = buy, 2 = sell
    timestamp: int
    message: str

    # -- serialisation -----------------------------------------------------

    def to_stream_dict(self) -> Dict[str, str]:
        """Convert to a ``{field: string}`` dict suitable for ``XADD``."""
        return {
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "type": str(self.type),
            "timestamp": str(self.timestamp),
            "message": self.message,
        }

    @classmethod
    def from_stream_dict(cls, data: Dict[str, str]) -> "SignalMessage":
        """Parse a stream entry back into a typed ``SignalMessage``."""
        return cls(
            symbol=data["symbol"],
            strategy_id=data["strategy_id"],
            type=int(data["type"]),
            timestamp=int(data["timestamp"]),
            message=data["message"],
        )


# ── Validation helpers ───────────────────────────────────────────────

def validate_price_message(data: Dict[str, Any]) -> None:
    """Raise ``ValueError`` if *data* is not a valid price message.

    Checks that all required fields are present and have values
    convertible to the expected types.
    """
    missing = _PRICE_REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ValueError(f"Missing price message fields: {sorted(missing)}")

    try:
        int(data["timestamp"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid timestamp: {data['timestamp']!r}") from exc

    for field in ("open", "high", "low", "close", "volume"):
        try:
            float(data[field])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {field}: {data[field]!r}") from exc


def validate_signal_message(data: Dict[str, Any]) -> None:
    """Raise ``ValueError`` if *data* is not a valid signal message.

    Checks required fields, valid signal type (1 or 2), and
    convertible timestamp.
    """
    missing = _SIGNAL_REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ValueError(f"Missing signal message fields: {sorted(missing)}")

    try:
        sig_type = int(data["type"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid signal type: {data['type']!r}") from exc

    if sig_type not in (1, 2):
        raise ValueError(
            f"Signal type must be 1 (buy) or 2 (sell), got {sig_type}"
        )

    try:
        int(data["timestamp"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid timestamp: {data['timestamp']!r}") from exc
