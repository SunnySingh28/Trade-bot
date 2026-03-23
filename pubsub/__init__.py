"""PubSub module — shared Redis Streams abstraction for inter-service messaging.

Re-exports the public API so consumers can write::

    from pubsub import connect_redis, StreamPublisher, StreamConsumer
"""

from .connection import connect_redis
from .consumer import StreamConsumer
from .publisher import StreamPublisher
from .schemas import PriceMessage, SignalMessage, validate_price_message, validate_signal_message
from .streams import price_stream, signal_stream

__all__ = [
    "connect_redis",
    "StreamPublisher",
    "StreamConsumer",
    "PriceMessage",
    "SignalMessage",
    "validate_price_message",
    "validate_signal_message",
    "price_stream",
    "signal_stream",
]
