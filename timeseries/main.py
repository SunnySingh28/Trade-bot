"""Redis TimeSeries writer service.

Consumes price and signal stream messages and stores them in Redis
TimeSeries keys for Grafana dashboards.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Any

try:
    import redis
except ModuleNotFoundError:  # pragma: no cover - allows helper tests without deps
    redis = None  # type: ignore[assignment]

if redis is None:  # pragma: no cover
    REDIS_CONNECTION_ERROR = ConnectionError
    REDIS_RESPONSE_ERROR = RuntimeError
    REDIS_ERROR = RuntimeError
else:  # pragma: no cover
    REDIS_CONNECTION_ERROR = redis.exceptions.ConnectionError
    REDIS_RESPONSE_ERROR = redis.exceptions.ResponseError
    REDIS_ERROR = redis.exceptions.RedisError

import config


logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("timeseries")


PRICE_FIELDS = ("open", "high", "low", "close", "volume")


def connect_redis(
    host: str = config.REDIS_HOST,
    port: int = config.REDIS_PORT,
    retries: int = config.MAX_RECONNECT_RETRIES,
    delay: float = config.RECONNECT_DELAY,
) -> "redis.Redis":
    """Connect to Redis with exponential-backoff retry."""
    if redis is None:
        raise RuntimeError("redis package is required to run timeseries service")

    for attempt in range(1, retries + 1):
        try:
            client = redis.Redis(host=host, port=port, decode_responses=True)
            client.ping()
            logger.info("Connected to Redis at %s:%s", host, port)
            return client
        except REDIS_CONNECTION_ERROR:
            wait = delay * (2 ** (attempt - 1))
            logger.warning(
                "Redis not ready (attempt %d/%d), retrying in %.1fs …",
                attempt,
                retries,
                wait,
            )
            time.sleep(wait)

    raise RuntimeError(f"Could not connect to Redis at {host}:{port}")


def price_stream(symbol: str) -> str:
    return f"price:{symbol}"


def signal_stream(strategy_id: str) -> str:
    return f"signal:{strategy_id}"


def price_ts_key(symbol: str, field: str) -> str:
    return f"price:{symbol}:{field}"


def signal_ts_key(strategy_id: str, symbol: str) -> str:
    return f"signal:{strategy_id}:{symbol}"


def signal_meta_key(strategy_id: str, symbol: str, timestamp_ms: int) -> str:
    return f"signal_meta:{strategy_id}:{symbol}:{timestamp_ms}"


def cursor_key(stream_name: str) -> str:
    return f"{config.CURSOR_KEY_PREFIX}:{stream_name}"


def _labels_to_args(labels: dict[str, str]) -> list[str]:
    args: list[str] = []
    for k, v in labels.items():
        args.extend([k, v])
    return args


def ts_create_if_missing(
    r: "redis.Redis",
    key: str,
    labels: dict[str, str],
) -> None:
    """Create a TimeSeries key if it doesn't exist."""
    try:
        r.execute_command(
            "TS.CREATE",
            key,
            "DUPLICATE_POLICY",
            "last",
            "LABELS",
            *_labels_to_args(labels),
        )
    except REDIS_RESPONSE_ERROR as exc:
        if "already exists" not in str(exc).lower():
            raise


def ensure_series_keys(
    r: "redis.Redis",
    symbols: list[str],
    strategies: list[str],
) -> None:
    """Create all required TimeSeries keys upfront."""
    for symbol in symbols:
        for field in PRICE_FIELDS:
            ts_create_if_missing(
                r,
                price_ts_key(symbol, field),
                labels={"symbol": symbol, "field": field, "type": "price"},
            )

    for strategy_id in strategies:
        for symbol in symbols:
            ts_create_if_missing(
                r,
                signal_ts_key(strategy_id, symbol),
                labels={
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "type": "signal",
                },
            )


def parse_price(fields: dict[str, str]) -> dict[str, Any]:
    """Parse a price stream message."""
    return {
        "symbol": fields["symbol"],
        "timestamp": int(fields["timestamp"]),
        "open": float(fields["open"]),
        "high": float(fields["high"]),
        "low": float(fields["low"]),
        "close": float(fields["close"]),
        "volume": float(fields["volume"]),
    }


def parse_signal(fields: dict[str, str]) -> dict[str, Any]:
    """Parse a signal stream message."""
    return {
        "symbol": fields["symbol"],
        "strategy_id": fields["strategy_id"],
        "type": int(fields["type"]),
        "timestamp": int(fields["timestamp"]),
        "message": fields["message"],
    }


def write_price(r: "redis.Redis", candle: dict[str, Any]) -> None:
    """Write OHLCV values to per-field TimeSeries keys."""
    symbol = candle["symbol"]
    ts_ms = int(candle["timestamp"]) * 1000
    for field in PRICE_FIELDS:
        r.execute_command("TS.ADD", price_ts_key(symbol, field), ts_ms, candle[field])


def write_signal(r: "redis.Redis", sig: dict[str, Any]) -> None:
    """Write signal value and companion signal metadata hash."""
    symbol = sig["symbol"]
    strategy_id = sig["strategy_id"]
    ts_ms = int(sig["timestamp"]) * 1000

    r.execute_command(
        "TS.ADD",
        signal_ts_key(strategy_id, symbol),
        ts_ms,
        int(sig["type"]),
    )
    r.hset(
        signal_meta_key(strategy_id, symbol, ts_ms),
        mapping={
            "message": str(sig["message"]),
            "type": str(sig["type"]),
        },
    )


def process_message(r: "redis.Redis", stream_name: str, fields: dict[str, str]) -> bool:
    """Process one stream message.

    Returns
    -------
    bool
        Whether the stream cursor should advance for this message.
    """
    try:
        if stream_name.startswith("price:"):
            candle = parse_price(fields)
            write_price(r, candle)
            return True

        if stream_name.startswith("signal:"):
            sig = parse_signal(fields)
            write_signal(r, sig)
            return True

        logger.warning("Unknown stream name=%s payload=%s", stream_name, fields)
        return True

    except REDIS_CONNECTION_ERROR:
        # Do not advance cursor; caller reconnects and re-reads.
        raise
    except (KeyError, TypeError, ValueError):
        logger.exception("Invalid payload stream=%s payload=%s", stream_name, fields)
        return True
    except REDIS_ERROR:
        # Non-connection Redis errors are logged and skipped.
        logger.exception("TS write failed stream=%s payload=%s", stream_name, fields)
        return True


def load_stream_cursors(
    r: "redis.Redis",
    symbols: list[str],
    strategies: list[str],
) -> dict[str, str]:
    """Load stream cursors from Redis or default start IDs."""
    streams: dict[str, str] = {}

    for symbol in symbols:
        stream = price_stream(symbol)
        streams[stream] = r.get(cursor_key(stream)) or config.STREAM_START_ID

    for strategy_id in strategies:
        stream = signal_stream(strategy_id)
        streams[stream] = r.get(cursor_key(stream)) or config.STREAM_START_ID

    return streams


_shutdown = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown
    logger.info("Received signal %d — shutting down", signum)
    _shutdown = True
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Timeseries writer starting — symbols=%s strategies=%s",
        config.SYMBOLS,
        config.STRATEGIES,
    )

    r = connect_redis()
    ensure_series_keys(r, config.SYMBOLS, config.STRATEGIES)
    stream_cursors = load_stream_cursors(r, config.SYMBOLS, config.STRATEGIES)

    while True:
        try:
            results = r.xread(
                stream_cursors,
                block=config.XREAD_BLOCK_MS,
                count=config.XREAD_COUNT,
            )

            for stream_name, entries in results or []:
                for msg_id, fields in entries:
                    should_advance = process_message(r, stream_name, fields)
                    if should_advance:
                        stream_cursors[stream_name] = msg_id
                        r.set(cursor_key(stream_name), msg_id)

            if _shutdown:
                break

        except REDIS_CONNECTION_ERROR as exc:
            logger.warning("Redis connection dropped: %s — reconnecting …", exc)
            time.sleep(config.RECONNECT_DELAY)
            r = connect_redis()
            ensure_series_keys(r, config.SYMBOLS, config.STRATEGIES)
        except Exception:
            logger.exception("Unexpected error in timeseries loop")
            time.sleep(config.RECONNECT_DELAY)


if __name__ == "__main__":
    main()
