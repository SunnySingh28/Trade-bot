"""Configuration for strategy service."""

from __future__ import annotations

import os


# Redis
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

# Service behavior
SYMBOLS: list[str] = [
    s.strip() for s in os.getenv("SYMBOLS", "BTCUSDT").split(",") if s.strip()
]
STRATEGY_MODULE: str = os.getenv("STRATEGY_MODULE", "ema_crossover")

# Stream consumption
XREAD_BLOCK_MS: int = int(os.getenv("XREAD_BLOCK_MS", "500"))
XREAD_COUNT: int = int(os.getenv("XREAD_COUNT", "100"))
STREAM_START_ID: str = os.getenv("STREAM_START_ID", "$")
CURSOR_KEY_PREFIX: str = os.getenv("CURSOR_KEY_PREFIX", "strategy:cursor")

# Connection retry
RECONNECT_DELAY: float = float(os.getenv("RECONNECT_DELAY", "2"))
MAX_RECONNECT_RETRIES: int = int(os.getenv("MAX_RECONNECT_RETRIES", "10"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
