# Redis TimeSeries Writer

## Purpose
Consume Redis Stream price/signal messages and persist them to Redis TimeSeries keys for dashboarding.

## Responsibilities
- Subscribe to explicit streams (no wildcards):
	- `price:{symbol}`
	- `signal:{strategy_id}`
- Parse and validate payloads
- Write OHLCV candles to per-field TimeSeries keys
- Write strategy signals to TimeSeries + companion hash metadata
- Maintain per-stream cursors for restart safety

## TimeSeries layout

### Price keys
For each symbol and field:
- `price:{symbol}:open`
- `price:{symbol}:high`
- `price:{symbol}:low`
- `price:{symbol}:close`
- `price:{symbol}:volume`

Each key is created on startup with labels:
- `symbol`
- `field`
- `type=price`

### Signal keys
For each strategy+symbol pair:
- `signal:{strategy_id}:{symbol}`

Signal value is `type` (`1=buy`, `2=sell`) at timestamp in milliseconds.

Signal message metadata is stored in:
- `signal_meta:{strategy_id}:{symbol}:{timestamp_ms}`

## Error handling
- Invalid payloads: log and skip
- Non-connection write errors: log and skip
- Connection loss: reconnect with exponential backoff
- Cursor advances only after a message is processed/explicitly skipped

## Runtime config
- `SYMBOLS` (comma-separated)
- `STRATEGIES` (comma-separated)
- `REDIS_HOST`, `REDIS_PORT`
- `STREAM_START_ID`, `XREAD_BLOCK_MS`, `XREAD_COUNT`
- `CURSOR_KEY_PREFIX`
