# Strategy Service

The strategy service contains all trading logic and algorithms.

The trades are executed based on basic technical indicators like RSI, moving averages (SMA, EMA DMA) and ATR.
For now simple trading strategies will need to be created, starting with golden crossover.

## Responsibilities
- Subscribe to live market data
- Execute event driven strategies to generate signals
- Send signals over to the signals service of pubsub



## Input
Topic: `market.prices`

```json
{
  "symbol": "BTCUSDT",
  "price": 42850.25,
  "timestamp": 1700000000
}
```