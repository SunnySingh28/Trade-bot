"""Strategy service entrypoint.

Consumes candles from ``price:{symbol}`` streams, updates indicators,
evaluates a strategy, and publishes signals to ``signal:{strategy_id}``.
"""

from __future__ import annotations

from collections import defaultdict, deque
import importlib
import logging
import signal
import sys
import time
from typing import Any

try:
    import redis
except ModuleNotFoundError:  # pragma: no cover - allows lightweight unit tests
    redis = None  # type: ignore[assignment]

import config


logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("strategy")


def connect_redis(
    host: str = config.REDIS_HOST,
    port: int = config.REDIS_PORT,
    retries: int = config.MAX_RECONNECT_RETRIES,
    delay: float = config.RECONNECT_DELAY,
) -> redis.Redis:
    """Connect to Redis with exponential-backoff retry."""
    if redis is None:
        raise RuntimeError("redis package is required to run strategy service")
    for attempt in range(1, retries + 1):
        try:
            client = redis.Redis(host=host, port=port, decode_responses=True)
            client.ping()
            logger.info("Connected to Redis at %s:%s", host, port)
            return client
        except redis.exceptions.ConnectionError:
            wait = delay * (2 ** (attempt - 1))
            logger.warning(
                "Redis not ready (attempt %d/%d), retrying in %.1fs …",
                attempt,
                retries,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"Could not connect to Redis at {host}:{port}")


def load_strategy_module(name: str):
    """Import and return ``strategies.<name>`` module."""
    return importlib.import_module(f"strategies.{name}")


def parse_candle(fields: dict[str, str]) -> dict[str, Any]:
    """Parse stream fields into typed candle values."""
    return {
        "symbol": fields["symbol"],
        "source": fields.get("source", "unknown"),
        "timestamp": int(fields["timestamp"]),
        "open": float(fields["open"]),
        "high": float(fields["high"]),
        "low": float(fields["low"]),
        "close": float(fields["close"]),
        "volume": float(fields["volume"]),
    }


def dedup_should_suppress(history: deque[int], signal_type: int, window: int) -> bool:
    """Return ``True`` when the previous ``window`` signals match this type."""
    if window <= 0:
        return False
    if len(history) < window:
        return False
    return all(prev == signal_type for prev in history)


def indicator_stream(strategy_id: str) -> str:
    return f"indicator:{strategy_id}"


def publish_indicator_snapshot(
    r: "redis.Redis",
    strategy_id: str,
    symbol: str,
    timestamp: int,
    inds: dict[str, Any],
) -> None:
    """Publish EMA snapshot for chart overlays.

    Emits one message per closed candle once indicators are ready.
    """
    ema_fast = inds.get("ema_fast")
    ema_slow = inds.get("ema_slow")
    if ema_fast is None or ema_slow is None:
        return

    fast_val = ema_fast.value()
    slow_val = ema_slow.value()
    if fast_val is None or slow_val is None:
        return

    payload = {
        "symbol": symbol,
        "strategy_id": strategy_id,
        "timestamp": timestamp,
        "ema_fast": round(float(fast_val), 8),
        "ema_slow": round(float(slow_val), 8),
    }
    r.xadd(indicator_stream(strategy_id), {k: str(v) for k, v in payload.items()})


def _cursor_key(stream_name: str) -> str:
    return f"{config.CURSOR_KEY_PREFIX}:{stream_name}"


_shutdown = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown
    logger.info("Received signal %d — shutting down", signum)
    _shutdown = True
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    strategy = load_strategy_module(config.STRATEGY_MODULE)
    strategy_id = getattr(strategy, "STRATEGY_ID", config.STRATEGY_MODULE)
    dedup_window = int(getattr(strategy, "DEDUP_WINDOW", 0))

    # Determine candle-window size: explicit LOOKBACK or max indicator period.
    base_inds = strategy.indicators()
    lookback = int(
        getattr(
            strategy,
            "LOOKBACK",
            max(getattr(ind, "period", 1) for ind in base_inds.values()),
        )
    )

    logger.info(
        "Strategy starting — strategy=%s symbols=%s lookback=%d dedup_window=%d",
        strategy_id,
        config.SYMBOLS,
        lookback,
        dedup_window,
    )

    r = connect_redis()

    streams = {f"price:{symbol}": config.STREAM_START_ID for symbol in config.SYMBOLS}
    for stream in list(streams.keys()):
        saved = r.get(_cursor_key(stream))
        if saved:
            streams[stream] = saved

    candles_by_symbol: dict[str, deque[dict[str, Any]]] = {
        symbol: deque(maxlen=lookback) for symbol in config.SYMBOLS
    }
    indicators_by_symbol: dict[str, dict[str, Any]] = {
        symbol: strategy.indicators() for symbol in config.SYMBOLS
    }
    signal_history: dict[str, deque[int]] = defaultdict(
        lambda: deque(maxlen=max(dedup_window, 1))
    )

    while True:
        try:
            results = r.xread(streams, block=config.XREAD_BLOCK_MS, count=config.XREAD_COUNT)
            for stream_name, entries in results or []:
                for msg_id, fields in entries:
                    streams[stream_name] = msg_id
                    r.set(_cursor_key(stream_name), msg_id)

                    try:
                        candle = parse_candle(fields)
                    except (KeyError, TypeError, ValueError):
                        logger.exception("Skipping invalid candle payload: %s", fields)
                        continue

                    symbol = candle["symbol"]
                    if symbol not in candles_by_symbol:
                        logger.debug("Ignoring unconfigured symbol in payload: %s", symbol)
                        continue

                    candles = candles_by_symbol[symbol]
                    inds = indicators_by_symbol[symbol]

                    candles.append(candle)
                    for ind in inds.values():
                        ind.update(candle)

                    # Warm-up gate
                    if len(candles) < candles.maxlen:
                        continue

                    try:
                        publish_indicator_snapshot(
                            r,
                            strategy_id=strategy_id,
                            symbol=symbol,
                            timestamp=int(candle["timestamp"]),
                            inds=inds,
                        )
                    except redis.exceptions.RedisError:
                        logger.error(
                            "Failed to publish indicator snapshot strategy=%s symbol=%s ts=%s",
                            strategy_id,
                            symbol,
                            candle["timestamp"],
                            exc_info=True,
                        )

                    signal_payload = strategy.evaluate(candles, inds)
                    if signal_payload is None:
                        continue

                    signal_type = int(signal_payload["type"])
                    history = signal_history[symbol]
                    if dedup_should_suppress(history, signal_type, dedup_window):
                        logger.info(
                            "Suppressed duplicate signal — strategy=%s symbol=%s type=%d",
                            strategy_id,
                            symbol,
                            signal_type,
                        )
                        continue

                    full_signal = {
                        "symbol": symbol,
                        "strategy_id": strategy_id,
                        "type": signal_type,
                        "timestamp": candle["timestamp"],
                        "message": str(signal_payload["message"]),
                    }

                    try:
                        r.xadd(f"signal:{strategy_id}", {k: str(v) for k, v in full_signal.items()})
                        history.append(signal_type)
                        logger.info(
                            "Published signal — strategy=%s symbol=%s type=%d ts=%d",
                            strategy_id,
                            symbol,
                            signal_type,
                            candle["timestamp"],
                        )
                    except redis.exceptions.RedisError:
                        logger.error(
                            "Failed to publish signal payload=%s",
                            full_signal,
                            exc_info=True,
                        )

            if _shutdown:
                break

        except redis.exceptions.ConnectionError as exc:
            logger.warning("Redis connection dropped: %s — reconnecting …", exc)
            time.sleep(config.RECONNECT_DELAY)
            r = connect_redis()
        except Exception:
            logger.exception("Unexpected error in strategy loop")
            time.sleep(config.RECONNECT_DELAY)


if __name__ == "__main__":
    main()
