from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notifier import format_alert_message, signal_type_label


def test_signal_type_label() -> None:
    assert signal_type_label(1) == "BUY"
    assert signal_type_label(2) == "SELL"
    assert signal_type_label(9) == "UNKNOWN(9)"


def test_format_alert_message() -> None:
    msg = format_alert_message(
        {
            "symbol": "EURUSD",
            "strategy_id": "ema_crossover",
            "type": 1,
            "timestamp": 1718000000,
            "message": "cross up",
        }
    )
    assert "ema_crossover" in msg
    assert "EURUSD" in msg
    assert "BUY" in msg
    assert "cross up" in msg
