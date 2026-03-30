"""Notification utilities for alerts service."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import request


logger = logging.getLogger("alerts.notifier")


def signal_type_label(sig_type: int) -> str:
    """Return human-readable signal type label."""
    if sig_type == 1:
        return "BUY"
    if sig_type == 2:
        return "SELL"
    return f"UNKNOWN({sig_type})"


def format_alert_message(signal: dict[str, Any]) -> str:
    """Format alert text from signal payload."""
    sig_type = int(signal["type"])
    label = signal_type_label(sig_type)
    return (
        f"[{signal['strategy_id']}] {signal['symbol']} {label} "
        f"at {signal['timestamp']}: {signal['message']}"
    )


def send_webhook(url: str, payload: dict[str, Any], timeout_seconds: float) -> None:
    """Send alert payload as JSON via HTTP POST."""
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds):
        return
