from __future__ import annotations

from collections import deque
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import cursor_key, parse_signal, should_suppress, signal_stream


def test_signal_stream_name() -> None:
    assert signal_stream("ema_crossover") == "signal:ema_crossover"


def test_cursor_key_prefix() -> None:
    key = cursor_key("signal:ema_crossover")
    assert key.startswith("alerts:cursor:")


def test_parse_signal() -> None:
    sig = parse_signal(
        {
            "symbol": "EURUSD",
            "strategy_id": "ema_crossover",
            "type": "2",
            "timestamp": "1718000000",
            "message": "cross down",
        }
    )
    assert sig["type"] == 2
    assert sig["timestamp"] == 1718000000


def test_should_suppress_true_when_all_previous_match() -> None:
    history = deque([1, 1, 1], maxlen=3)
    assert should_suppress(history, 1, 3) is True


def test_should_suppress_false_when_short_history() -> None:
    history = deque([1], maxlen=3)
    assert should_suppress(history, 1, 3) is False
