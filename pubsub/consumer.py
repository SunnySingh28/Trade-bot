"""Stream consumer — wraps ``XREAD`` with cursor tracking.

Each consumer maintains its own independent cursor per stream, matching
the spec's "no consumer groups" architecture.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

import redis

from . import config

logger = logging.getLogger("pubsub.consumer")

# Type alias for a single parsed stream entry.
StreamEntry = Tuple[str, str, Dict[str, str]]  # (stream, msg_id, fields)


class StreamConsumer:
    """Read messages from one or more Redis Streams using ``XREAD``.

    Parameters
    ----------
    redis_client : redis.Redis
        A connected Redis client (``decode_responses=True`` expected).
    streams : dict[str, str]
        Mapping of stream name → initial cursor.
        Use ``"0"`` to read from the beginning or ``"$"`` for only new
        messages.
    block_ms : int
        Milliseconds to block on each ``XREAD`` call.
    count : int
        Maximum messages to fetch per ``XREAD`` call.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        streams: Dict[str, str],
        block_ms: int = config.XREAD_BLOCK_MS,
        count: int = config.XREAD_COUNT,
    ) -> None:
        self._redis = redis_client
        self._cursors: Dict[str, str] = dict(streams)
        self._block_ms = block_ms
        self._count = count

    # -- public API --------------------------------------------------------

    @property
    def cursors(self) -> Dict[str, str]:
        """Return a copy of the current stream → cursor mapping."""
        return dict(self._cursors)

    def poll(self) -> List[StreamEntry]:
        """Execute one ``XREAD`` call and return parsed entries.

        Advances internal cursors automatically so the next ``poll``
        resumes where this one left off.

        Returns
        -------
        list of (stream_name, msg_id, fields) tuples
            An empty list when ``XREAD`` returns nothing (timeout).
        """
        results = self._redis.xread(
            self._cursors, block=self._block_ms, count=self._count,
        )

        entries: List[StreamEntry] = []
        for stream_name, messages in results or []:
            for msg_id, fields in messages:
                entries.append((stream_name, msg_id, fields))
                self._cursors[stream_name] = msg_id

        return entries

    def consume(
        self,
        callback: Callable[[str, str, Dict[str, str]], None],
        *,
        stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Blocking loop that invokes *callback* for each message.

        Parameters
        ----------
        callback : callable
            Called as ``callback(stream_name, msg_id, fields)`` for
            every message received.
        stop : callable, optional
            A zero-argument callable that returns ``True`` when the
            loop should exit.  Checked after each ``poll`` cycle.
            If ``None``, the loop runs indefinitely.
        """
        logger.info(
            "Starting consumer loop — streams=%s", list(self._cursors.keys()),
        )
        while True:
            entries = self.poll()
            for stream_name, msg_id, fields in entries:
                callback(stream_name, msg_id, fields)

            if stop is not None and stop():
                logger.info("Stop signal received — exiting consumer loop")
                break
