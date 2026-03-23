"""PubSub configuration — shared Redis settings from environment variables.

Every Redis-related knob is read once at import time and exposed as
module-level constants.  Defaults match the docker-compose setup.
"""

from __future__ import annotations

import os


# ── Redis ────────────────────────────────────────────────────────────
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

# ── Connection retry ─────────────────────────────────────────────────
RECONNECT_DELAY: float = float(os.getenv("RECONNECT_DELAY", "2"))
MAX_RECONNECT_RETRIES: int = int(os.getenv("MAX_RECONNECT_RETRIES", "10"))

# ── Consumer defaults ────────────────────────────────────────────────
XREAD_BLOCK_MS: int = int(os.getenv("XREAD_BLOCK_MS", "500"))
XREAD_COUNT: int = int(os.getenv("XREAD_COUNT", "100"))

# ── Logging ──────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
