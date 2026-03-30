from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import (
    PRICE_FIELDS,
    parse_price,
    parse_signal,
    price_ts_key,
    process_message,
    signal_meta_key,
    signal_ts_key,
    write_price,
    write_signal,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.commands: list[tuple] = []
        self.hsets: list[tuple] = []

    def execute_command(self, *args):
        self.commands.append(args)
        return "OK"

    def hset(self, key, mapping):
        self.hsets.append((key, mapping))
        return 1


def test_parse_price() -> None:
    parsed = parse_price(
        {
            "symbol": "EURUSD",
            "timestamp": "1718000000",
            "open": "1.1",
            "high": "1.2",
            "low": "1.0",
            "close": "1.15",
            "volume": "100",
        }
    )
    assert parsed["symbol"] == "EURUSD"
    assert parsed["timestamp"] == 1718000000
    assert parsed["close"] == 1.15


def test_parse_signal() -> None:
    parsed = parse_signal(
        {
            "symbol": "EURUSD",
            "strategy_id": "ema_crossover",
            "type": "1",
            "timestamp": "1718000000",
            "message": "crossed",
        }
    )
    assert parsed["strategy_id"] == "ema_crossover"
    assert parsed["type"] == 1


def test_write_price_generates_five_ts_adds() -> None:
    r = _FakeRedis()
    write_price(
        r,
        {
            "symbol": "EURUSD",
            "timestamp": 1718000000,
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 100.0,
        },
    )
    assert len(r.commands) == len(PRICE_FIELDS)
    assert r.commands[0][0] == "TS.ADD"
    assert r.commands[0][1] == price_ts_key("EURUSD", "open")
    assert r.commands[0][2] == 1718000000 * 1000


def test_write_signal_generates_ts_add_and_meta_hash() -> None:
    r = _FakeRedis()
    write_signal(
        r,
        {
            "symbol": "EURUSD",
            "strategy_id": "ema_crossover",
            "type": 2,
            "timestamp": 1718000000,
            "message": "sell",
        },
    )
    assert r.commands[0][0] == "TS.ADD"
    assert r.commands[0][1] == signal_ts_key("ema_crossover", "EURUSD")
    assert r.hsets[0][0] == signal_meta_key("ema_crossover", "EURUSD", 1718000000 * 1000)
    assert r.hsets[0][1]["message"] == "sell"


def test_process_message_advances_on_invalid_payload() -> None:
    r = _FakeRedis()
    should_advance = process_message(r, "price:EURUSD", {"symbol": "EURUSD"})
    assert should_advance is True
