"""Configuration — reads all settings from environment variables.

Every knob the ingestor needs is read once at import time and exposed
as module-level constants.  Defaults match the docker-compose setup.
"""

from __future__ import annotations

import os


# ── Redis ────────────────────────────────────────────────────────────
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

# ── Symbols ──────────────────────────────────────────────────────────
# Comma-separated list, e.g. "EURUSD,BTCUSDT"
SYMBOLS: list[str] = [
    s.strip()
    for s in os.getenv("SYMBOLS", "BTCUSDT").split(",")
    if s.strip()
]

# ── Candle ───────────────────────────────────────────────────────────
INTERVAL: int = int(os.getenv("INTERVAL", "60"))  # seconds

# ── Data source ──────────────────────────────────────────────────────
DATA_SOURCE: str = os.getenv("DATA_SOURCE", "binance")
WS_URI: str = os.getenv(
    "WS_URI",
    "wss://stream.binance.com/ws",
)
BINANCE_KLINE_INTERVAL: str = os.getenv("BINANCE_KLINE_INTERVAL", "1s")
WS_CONNECT_TIMEOUT: float = float(os.getenv("WS_CONNECT_TIMEOUT", "10"))

# ── Operational ──────────────────────────────────────────────────────
RECONNECT_DELAY: float = float(os.getenv("RECONNECT_DELAY", "2"))
MAX_RECONNECT_RETRIES: int = int(os.getenv("MAX_RECONNECT_RETRIES", "10"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
