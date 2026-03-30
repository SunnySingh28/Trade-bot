# Alerts Service

## Purpose
Consume strategy signal streams and emit operational alerts for buy/sell events.

## Responsibilities
- Subscribe to explicit signal streams (`signal:{strategy_id}`)
- Parse and validate signal payloads
- Optionally filter by symbol
- Suppress repeated identical alerts with a small dedup window
- Deliver alerts to logs and optional webhook endpoint
- Persist stream cursors for restart-safe consumption

## Input
Redis Streams message from `signal:{strategy_id}`:

```json
{
	"symbol": "EURUSD",
	"strategy_id": "ema_crossover",
	"type": 1,
	"timestamp": 1718000000,
	"message": "EMA20 crossed above EMA50, close=1.0829"
}
```

`type`: `1=buy`, `2=sell`.

## Delivery
- Always logs a warning-level alert message
- Optionally sends webhook JSON if `ALERT_WEBHOOK_URL` is configured

Webhook payload shape:

```json
{
	"channel": "default",
	"text": "[ema_crossover] EURUSD BUY at 1718000000: EMA20 crossed above EMA50, close=1.0829",
	"signal": { "...": "original signal payload" }
}
```

## Runtime config
- `STRATEGIES` (comma-separated, required for subscription)
- `SYMBOLS` (optional comma-separated filter)
- `ALERT_WEBHOOK_URL` (optional)
- `ALERT_CHANNEL`
- `DEDUP_WINDOW`
- `STREAM_START_ID`, `XREAD_BLOCK_MS`, `XREAD_COUNT`
- `REDIS_HOST`, `REDIS_PORT`

## Error handling
- Invalid signal payload: log and skip
- Webhook failure: log and continue
- Redis disconnect: reconnect with exponential backoff

