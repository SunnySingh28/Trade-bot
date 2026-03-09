# InfluxDB Writer – Copilot Context

## Purpose
Consumes events from Pub-Sub and writes time-series data into InfluxDB.

## Responsibilities
- Subscribe to price and signal topics
- Transform messages into InfluxDB format
- Write data efficiently using batch writes

## Measurements
| Measurement | Fields |
|------------|--------|
| prices | price, volume |
| signals | signal, confidence |

prices will contain ohlcv data along with timestamp. need separate columns for each.
signals will be timestamped, will have buy/sell along with symbol (string - like eurusd)

## Tags
- symbol
- exchange
- strategy

## Retention Policy
- Ticks: short-term
- Candles: long-term
- Signals: long-term

## Coding Guidelines
- Batch writes for performance
- Handle write failures gracefully
- No business logic here
- Validate data before writing