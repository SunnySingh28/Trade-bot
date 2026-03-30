"""Alerts service.

Consumes strategy signal streams and emits operator-facing alerts
through logs and optional webhook delivery.
"""

from __future__ import annotations

from collections import defaultdict, deque
import logging
import signal
import sys
import time
from typing import Any

try:
    import redis
except ModuleNotFoundError:  # pragma: no cover - test environments without redis
    redis = None  # type: ignore[assignment]

if redis is None:  # pragma: no cover
    REDIS_CONNECTION_ERROR = ConnectionError
    REDIS_ERROR = RuntimeError
else:  # pragma: no cover
    REDIS_CONNECTION_ERROR = redis.exceptions.ConnectionError
    REDIS_ERROR = redis.exceptions.RedisError

import config
from notifier import format_alert_message, send_webhook


logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("alerts")


def connect_redis(
    host: str = config.REDIS_HOST,
    port: int = config.REDIS_PORT,
    retries: int = config.MAX_RECONNECT_RETRIES,
    delay: float = config.RECONNECT_DELAY,
) -> "redis.Redis":
    """Connect to Redis with exponential-backoff retry."""
    if redis is None:
        raise RuntimeError("redis package is required to run alerts service")

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


def signal_stream(strategy_id: str) -> str:
    return f"signal:{strategy_id}"


def cursor_key(stream_name: str) -> str:
    return f"{config.CURSOR_KEY_PREFIX}:{stream_name}"


def parse_signal(fields: dict[str, str]) -> dict[str, Any]:
    """Parse and type-cast signal stream message fields."""
    return {
        "symbol": fields["symbol"],
        "strategy_id": fields["strategy_id"],
        "type": int(fields["type"]),
        "timestamp": int(fields["timestamp"]),
        "message": fields["message"],
    }


def should_suppress(history: deque[int], signal_type: int, window: int) -> bool:
    """Return True if previous ``window`` signals are all the same type."""
    if window <= 0:
        return False
    if len(history) < window:
        return False
    return all(prev == signal_type for prev in history)


def deliver_alert(signal_payload: dict[str, Any]) -> None:
    """Deliver one alert (always logs; optionally sends webhook)."""
    text = format_alert_message(signal_payload)
    logger.warning("ALERT[%s] %s", config.ALERT_CHANNEL, text)

    if not config.ALERT_WEBHOOK_URL:
        return

    webhook_payload = {
        "channel": config.ALERT_CHANNEL,
        "text": text,
        "signal": signal_payload,
    }
    send_webhook(
        config.ALERT_WEBHOOK_URL,
        webhook_payload,
        timeout_seconds=config.ALERT_TIMEOUT_SECONDS,
    )


def load_stream_cursors(r: "redis.Redis") -> dict[str, str]:
    """Load signal stream cursors from Redis or default start ID."""
    streams: dict[str, str] = {}
    for strategy_id in config.STRATEGIES:
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
        "Alerts service starting — strategies=%s symbols=%s",
        config.STRATEGIES,
        config.SYMBOLS if config.SYMBOLS else "*",
    )

    r = connect_redis()
    streams = load_stream_cursors(r)

    # Strategy+symbol dedup cache.
    dedup_history: dict[tuple[str, str], deque[int]] = defaultdict(
        lambda: deque(maxlen=max(config.DEDUP_WINDOW, 1))
    )

    while True:
        try:
            results = r.xread(streams, block=config.XREAD_BLOCK_MS, count=config.XREAD_COUNT)

            for stream_name, entries in results or []:
                for msg_id, fields in entries:
                    try:
                        sig = parse_signal(fields)
                    except (KeyError, TypeError, ValueError):
                        logger.exception(
                            "Invalid signal payload stream=%s payload=%s",
                            stream_name,
                            fields,
                        )
                        streams[stream_name] = msg_id
                        r.set(cursor_key(stream_name), msg_id)
                        continue

                    if config.SYMBOLS and sig["symbol"] not in config.SYMBOLS:
                        streams[stream_name] = msg_id
                        r.set(cursor_key(stream_name), msg_id)
                        continue

                    cache_key = (sig["strategy_id"], sig["symbol"])
                    history = dedup_history[cache_key]

                    if should_suppress(history, int(sig["type"]), config.DEDUP_WINDOW):
                        logger.info(
                            "Suppressed duplicate alert strategy=%s symbol=%s type=%s",
                            sig["strategy_id"],
                            sig["symbol"],
                            sig["type"],
                        )
                    else:
                        try:
                            deliver_alert(sig)
                            history.append(int(sig["type"]))
                        except Exception:
                            # Delivery failure should not stop stream consumption.
                            logger.exception("Failed to deliver alert payload=%s", sig)

                    streams[stream_name] = msg_id
                    r.set(cursor_key(stream_name), msg_id)

            if _shutdown:
                break

        except REDIS_CONNECTION_ERROR as exc:
            logger.warning("Redis connection dropped: %s — reconnecting …", exc)
            time.sleep(config.RECONNECT_DELAY)
            r = connect_redis()
            streams = load_stream_cursors(r)
        except Exception:
            logger.exception("Unexpected error in alerts loop")
            time.sleep(config.RECONNECT_DELAY)


if __name__ == "__main__":
    main()
