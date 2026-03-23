"""Redis connection with exponential-backoff retry.

Provides a single ``connect_redis`` function that all services can
import instead of duplicating retry logic.
"""

from __future__ import annotations

import logging
import time

import redis

from . import config

logger = logging.getLogger("pubsub.connection")


def connect_redis(
    host: str = config.REDIS_HOST,
    port: int = config.REDIS_PORT,
    retries: int = config.MAX_RECONNECT_RETRIES,
    delay: float = config.RECONNECT_DELAY,
    decode_responses: bool = True,
) -> redis.Redis:
    """Connect to Redis, retrying with exponential back-off.

    Parameters
    ----------
    host : str
        Redis hostname.
    port : int
        Redis port.
    retries : int
        Maximum number of connection attempts.
    delay : float
        Base delay in seconds (doubled after each failure).
    decode_responses : bool
        If ``True``, Redis values are returned as Python strings.

    Returns
    -------
    redis.Redis
        A connected Redis client.

    Raises
    ------
    RuntimeError
        If the connection could not be established after *retries* attempts.
    """
    for attempt in range(1, retries + 1):
        try:
            client = redis.Redis(
                host=host, port=port, decode_responses=decode_responses,
            )
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
