"""Configuration for alerts service."""

from __future__ import annotations

import os


# Redis
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

# Explicit subscriptions (no wildcard)
STRATEGIES: list[str] = [
    s.strip() for s in os.getenv("STRATEGIES", "ema_crossover").split(",") if s.strip()
]

# Optional symbol filtering; empty means all symbols from subscribed strategy streams.
SYMBOLS: list[str] = [
    s.strip() for s in os.getenv("SYMBOLS", "").split(",") if s.strip()
]

# Stream cursor
STREAM_START_ID: str = os.getenv("STREAM_START_ID", "$")
XREAD_BLOCK_MS: int = int(os.getenv("XREAD_BLOCK_MS", "500"))
XREAD_COUNT: int = int(os.getenv("XREAD_COUNT", "100"))
CURSOR_KEY_PREFIX: str = os.getenv("CURSOR_KEY_PREFIX", "alerts:cursor")

# Delivery
ALERT_WEBHOOK_URL: str | None = os.getenv("ALERT_WEBHOOK_URL")
ALERT_TIMEOUT_SECONDS: float = float(os.getenv("ALERT_TIMEOUT_SECONDS", "5"))
ALERT_CHANNEL: str = os.getenv("ALERT_CHANNEL", "default")

# Suppress repeated identical signal types per strategy+symbol for N events.
DEDUP_WINDOW: int = int(os.getenv("DEDUP_WINDOW", "1"))

# Connection retry
RECONNECT_DELAY: float = float(os.getenv("RECONNECT_DELAY", "2"))
MAX_RECONNECT_RETRIES: int = int(os.getenv("MAX_RECONNECT_RETRIES", "10"))

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
