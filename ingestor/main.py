"""Ingestor entry point — connects to a data source and publishes candles.

Lifecycle
---------
1. Read configuration from environment variables.
2. Connect to Redis with exponential-backoff retry.
3. Open a stable WebSocketApp to the Binance 1s Kline stream.
4. For each incoming tick, parse the completed kline;
   when a candle is completed, XADD it to ``price:{symbol}``.
5. Handle heartbeats (ping/pong) to prevent silent connection drops.
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

import config

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingestor")

# Global reference for the Redis client to be used in callbacks
redis_client: redis.Redis | None = None

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
def parse_binance_kline(raw: str) -> Dict[str, Any] | None:
    """Parse a Binance kline stream message into a completed candle dict.
    
    Returns OHLCV only if the kline is fully closed ("x": true).
    """
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if msg.get("e") != "kline":
        return None

    kline = msg.get("k", {})

    if not kline.get("x"):
        return None

    return {
        "symbol": msg.get("s"),
        "timestamp": int(kline.get("t", 0)) // 1000,  # ms → seconds
        "open": float(kline.get("o", 0.0)),
        "high": float(kline.get("h", 0.0)),
        "low": float(kline.get("l", 0.0)),
        "close": float(kline.get("c", 0.0)),
        "volume": float(kline.get("v", 0.0)),
        "tick_count": int(kline.get("n", 0)),
    }


# ── Websocket Callbacks ──────────────────────────────────────────────
def on_message(ws, message):
    """Triggered whenever data is received from the socket."""
    candle = parse_binance_kline(message)
    if candle and redis_client:
        publish_candle(redis_client, candle)
        logger.info(
            "Candle Published  %s  ts=%s  C=%.2f  V=%.2f",
            candle["symbol"],
            candle["timestamp"],
            candle["close"],
            candle["volume"]
        )

def on_error(ws, error):
    logger.error("Websocket Error: %s", error)

def on_close(ws, close_status_code, close_msg):
    logger.warning("Websocket Closed: %s - %s", close_status_code, close_msg)

def on_open(ws):
    """Triggered when the handshake is successful."""
    logger.info(
        "Websocket Connection Established! Streaming %s Klines...",
        config.BINANCE_KLINE_INTERVAL,
    )


# ── Websocket lifecycle ─────────────────────────────────────────────
def build_ws_url(symbol: str, base_uri: str, interval: str = "1s") -> str:
    """Build the full websocket URL for a Binance kline stream."""
    return f"{base_uri}/{symbol.lower()}@kline_{interval}"


def run_ingestor_v2(symbol: str, ws_uri: str, interval: str) -> None:
    """Run the main ingest loop using WebSocketApp for heartbeats."""
    url = build_ws_url(symbol, ws_uri, interval=interval)
    logger.info("Connecting websocket url=%s", url)
    
    # Enable internal trace for deep debugging if needed
    # websocket.enableTrace(False) 

    # Prevent hanging forever when a host/port is unreachable.
    websocket.setdefaulttimeout(config.WS_CONNECT_TIMEOUT)

    ws = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    # run_forever handles the connection and reconnection logic.
    # ping_interval ensures we send a keep-alive every 30s.
    ws.run_forever(ping_interval=30, ping_timeout=10)


# ── Graceful shutdown ────────────────────────────────────────────────
_shutdown = False

def _handle_signal(signum: int, _frame: Any) -> None:
    global _shutdown
    logger.info("Received signal %d — shutting down", signum)
    _shutdown = True
    sys.exit(0)


# ── Main ─────────────────────────────────────────────────────────────
def main() -> None:
    global redis_client
    
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Ingestor starting — symbols=%s  source=%s ws_uri=%s interval=%s",
        config.SYMBOLS,
        config.DATA_SOURCE,
        config.WS_URI,
        config.BINANCE_KLINE_INTERVAL,
    )

    # 1. Initialize Redis
    redis_client = connect_redis()

    symbol = config.SYMBOLS[0]
    if len(config.SYMBOLS) != 1:
        logger.warning("v1 supports single symbol. Using: %s", symbol)

    # 2. Start WebSocket Loop
    while not _shutdown:
        try:
            run_ingestor_v2(symbol, config.WS_URI, config.BINANCE_KLINE_INTERVAL)
        except Exception:
            logger.exception("Unexpected error in ingest loop. Reconnecting in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    main()