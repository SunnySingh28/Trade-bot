from __future__ import annotations

from collections import deque
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import dedup_should_suppress


def test_dedup_suppresses_when_last_k_match() -> None:
    history = deque([1, 1, 1], maxlen=3)
    assert dedup_should_suppress(history, 1, 3) is True


def test_dedup_does_not_suppress_when_history_short() -> None:
    history = deque([1, 1], maxlen=3)
    assert dedup_should_suppress(history, 1, 3) is False


def test_dedup_does_not_suppress_when_mixed() -> None:
    history = deque([1, 2, 1], maxlen=3)
    assert dedup_should_suppress(history, 1, 3) is False
