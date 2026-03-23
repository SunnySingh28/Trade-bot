"""Stream publisher — wraps ``XADD`` with logging and error handling.

Fire-and-forget semantics: Redis errors are logged but never raised,
matching the spec's requirement that publish failures do not crash the
calling service.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import redis

from .streams import price_stream, signal_stream

logger = logging.getLogger("pubsub.publisher")


class StreamPublisher:
    """Publish messages to Redis Streams.

    Parameters
    ----------
    redis_client : redis.Redis
        A connected Redis client (``decode_responses=True`` expected).
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    # -- generic -----------------------------------------------------------

    def publish(self, stream: str, data: Dict[str, Any]) -> Optional[str]:
        """XADD *data* to *stream*.

        All values are stringified before sending (Redis Streams store
        everything as bytes/strings).

        Returns
        -------
        str or None
            The message ID assigned by Redis, or ``None`` if the
            publish failed.
        """
        payload = {k: str(v) for k, v in data.items()}
        try:
            msg_id = self._redis.xadd(stream, payload)
            logger.debug("Published to %s  msg_id=%s", stream, msg_id)
            return msg_id
        except redis.exceptions.RedisError:
            logger.exception("Failed to publish to %s — skipping", stream)
            return None

    # -- convenience -------------------------------------------------------

    def publish_price(self, candle: Dict[str, Any]) -> Optional[str]:
        """Publish a candle dict to the appropriate price stream.

        The stream name is derived from ``candle["symbol"]``.
        """
        stream = price_stream(candle["symbol"])
        return self.publish(stream, candle)

    def publish_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        """Publish a signal dict to the appropriate signal stream.

        The stream name is derived from ``signal["strategy_id"]``.
        """
        stream = signal_stream(signal["strategy_id"])
        return self.publish(stream, signal)
