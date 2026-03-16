"""Ingestor entry point — connects to a data source and publishes candles.

Lifecycle
---------
1. Read configuration from environment variables.
2. Connect to Redis with exponential-backoff retry.
3. Open a websocket to the data source.
4. For each incoming tick, feed it to the CandleBuilder;
   when a candle is completed, XADD it to ``price:{symbol}``.
5. On websocket drop, log and reconnect.
6. Shut down cleanly on SIGINT / SIGTERM.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from typing import Any, Dict

import redis
import websocket

from candle_builder import CandleBuilder
import config

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingestor")


# ── Redis connection with retry ──────────────────────────────────────
def connect_redis(
    host: str = config.REDIS_HOST,
    port: int = config.REDIS_PORT,
    retries: int = config.MAX_RECONNECT_RETRIES,
    delay: float = config.RECONNECT_DELAY,
) -> redis.Redis:
    """Connect to Redis, retrying with exponential backoff."""
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


# ── Publish a candle to Redis Streams ────────────────────────────────
def publish_candle(r: redis.Redis, candle: Dict[str, Any]) -> None:
    """XADD the candle to ``price:{symbol}``."""
    stream = f"price:{candle['symbol']}"
    # Redis Streams store every value as a string.
    payload = {k: str(v) for k, v in candle.items()}
    try:
        msg_id = r.xadd(stream, payload)
        logger.debug("Published candle to %s  msg_id=%s", stream, msg_id)
    except redis.exceptions.RedisError:
        logger.exception("Failed to publish candle to %s — skipping", stream)


# ── Websocket tick parsing ───────────────────────────────────────────
def parse_binance_trade(raw: str) -> Dict[str, Any] | None:
    """Parse a Binance trade stream message into a tick dict.

    Expected JSON (Binance ``@trade`` stream)::

        {"e":"trade","E":1718000005123,"s":"BTCUSDT",
         "p":"42850.25","q":"0.0012","T":1718000005100, ...}

    Returns ``{"price": float, "volume": float, "timestamp": int}``
    or ``None`` if the message is not a trade event.
    """
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if msg.get("e") != "trade":
        return None

    return {
        "price": float(msg["p"]),
        "volume": float(msg["q"]),
        "timestamp": int(msg["T"]) // 1000,  # ms → seconds
    }


# ── Websocket lifecycle ─────────────────────────────────────────────
def build_ws_url(symbol: str, base_uri: str) -> str:
    """Build the full websocket URL for a Binance trade stream."""
    return f"{base_uri}/{symbol.lower()}@trade"


def run_ingestor(
    r: redis.Redis,
    symbol: str,
    source: str,
    interval: int,
    ws_uri: str,
) -> None:
    """Run the main ingest loop for a single symbol (blocking)."""
    builder = CandleBuilder(symbol, source, interval)
    url = build_ws_url(symbol, ws_uri)

    while True:
        try:
            logger.info("Connecting to websocket: %s", url)
            ws = websocket.create_connection(url, timeout=30)
            logger.info("Websocket connected for %s", symbol)

            while True:
                raw = ws.recv()
                tick = parse_binance_trade(raw)
                if tick is None:
                    continue

                candle = builder.process_tick(tick)
                if candle is not None:
                    publish_candle(r, candle)
                    logger.info(
                        "Candle emitted  %s  ts=%s  O=%.5f H=%.5f L=%.5f C=%.5f V=%.2f  ticks=%d",
                        symbol,
                        candle["timestamp"],
                        candle["open"],
                        candle["high"],
                        candle["low"],
                        candle["close"],
                        candle["volume"],
                        candle["tick_count"],
                    )

        except (
            websocket.WebSocketException,
            ConnectionError,
            OSError,
        ) as exc:
            logger.warning("Websocket error for %s: %s — reconnecting …", symbol, exc)
            time.sleep(config.RECONNECT_DELAY)
        except Exception:
            logger.exception("Unexpected error in ingest loop for %s", symbol)
            time.sleep(config.RECONNECT_DELAY)


# ── Graceful shutdown ────────────────────────────────────────────────
_shutdown = False


def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown
    logger.info("Received signal %d — shutting down", signum)
    _shutdown = True
    sys.exit(0)


# ── Main ─────────────────────────────────────────────────────────────
def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Ingestor starting — symbols=%s  interval=%ds  source=%s",
        config.SYMBOLS,
        config.INTERVAL,
        config.DATA_SOURCE,
    )

    r = connect_redis()

    # For v1 we run a single symbol in-process.
    # Multi-symbol support can be added via threading/asyncio later.
    if len(config.SYMBOLS) != 1:
        logger.warning(
            "v1 supports a single symbol per ingestor instance. "
            "Using the first symbol: %s",
            config.SYMBOLS[0],
        )

    run_ingestor(
        r,
        symbol=config.SYMBOLS[0],
        source=config.DATA_SOURCE,
        interval=config.INTERVAL,
        ws_uri=config.WS_URI,
    )


if __name__ == "__main__":
    main()
