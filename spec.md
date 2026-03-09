<!-- # Event driven Algo Trading Engine
Building a real-time, event-driven algorithmic trading platform.

## High-Level Architecture
- Market data is received via WebSocket
- Data is processed by an ingestion service
- All communication happens via Redis Pub-Sub
- Time-series data is stored in Redis timeseries
- Trading strategies consume market data and emit signals in an event driven manner
- Grafana visualizes prices and signals, with redis as the source

## Core Design Principles
- Event-driven architecture
- Loose coupling via Pub-Sub
- Low latency and high throughput
- Horizontal scalability
- Fault tolerance

## Technologies
- Language: Python
- Messaging: Redis pubsub
- Storage: redis timeseries
- Visualization: Grafana
- Deployment: Docker compose -->

# trade-bot

trade-bot is an event-driven real-time system that ingests prices, executes algorithmic trading strategies on them, and sends generated signals to subscribed consumers.

On a high level, the project consists of an ingestion service that subscribes to data sources, Redis Streams as the inter-service message bus, a strategy service that computes indicator values and evaluates trading strategies to generate signals, Redis TimeSeries as the time series store for prices and signals, and a Grafana dashboard for visualisation.

---

## Components

### Ingestion service

Connects to a data source (websocket or polling), processes incoming data into candles, and publishes completed candles to a Redis Stream.

Language: Python

Candle schema (published to Redis Streams):
```json
{
    "symbol": "EURUSD",
    "source": "binance",
    "timestamp": 1718000000,
    "open": 1.0821,
    "high": 1.0834,
    "low": 1.0819,
    "close": 1.0829,
    "volume": 1024.0
}
```

`timestamp` is the Unix epoch (seconds) of the first tick in the candle window. It is taken as the source of truth for the entire system.

All incoming data (whether raw ticks or pre-formed candles) carries a timestamp field from the data source, which the ingestor uses directly rather than deriving timestamps from wall-clock time.

#### CandleBuilder

Receives ticks from the source and accumulates them into candles. A candle is sealed and emitted when the first tick of a new time interval arrives. The interval boundary is computed as:

```
floor(tick.timestamp / interval_seconds) * interval_seconds
```

When a tick's computed interval is greater than the current candle's open interval, the current candle is complete and emitted before a new one is started. Candles are never emitted at a wall-clock boundary — only an incoming tick with a newer interval triggers emission. This means there is always exactly one candle of lag, which is correct and expected.

Within a candle: `open` is the price of the first tick, `close` is the price of the last tick before sealing, `high` and `low` are the running max and min of price across all ticks in the window, `volume` is the sum of tick volumes.

Edge cases:
- First tick ever: initialise a new candle, do not emit.
- Gap in data (market close, weekend, reconnect): the builder does not synthesise missing candles. On reconnect the next tick starts a fresh candle. Gaps are visible in the TSDB and dashboard as missing data points, which is correct.
- Reconnection: the ingestor is responsible for handling websocket drops and polling failures. On reconnect it resumes publishing. Gap detection is the responsibility of the operator reading the dashboard.

---

### Redis Streams (message bus)

Redis Streams (via the `redis/redis-stack` Docker image) replace a dedicated message broker. All inter-service communication flows through streams.

#### Stream naming

One stream per symbol for prices, one stream per strategy for signals:

```
price:EURUSD
price:BTCUSDT
signal:ema_crossover
```

There are no wildcard subscriptions. Each service is configured with the list of symbols and strategies it cares about (via environment variables), and subscribes to those named streams explicitly.

#### Multiple consumers

Each service reads streams independently using `XREAD` with its own tracked cursor (last-seen message ID). The stream is a persistent log — consumers are not registered with the stream and do not affect each other. The strategy service and the TSDB writer each maintain their own cursor and advance it independently. A service that restarts resumes from its last saved cursor, or from the stream's current tail if no cursor is saved.

```python
last_id = "0"  # "0" reads from beginning; "$" reads only new messages from now

while True:
    results = redis.xread({"price:EURUSD": last_id}, block=500, count=100)
    for stream_name, entries in (results or []):
        for msg_id, fields in entries:
            process(fields)
            last_id = msg_id
```

Multiple services (strategy, tsdb-writer) read the same stream independently. There are no consumer groups — each service needs every message, so independent cursors are the correct model.

#### Message schemas

Price message fields (all values stored as strings in the stream, parsed by consumers):

| Field     | Type   |
|-----------|--------|
| symbol    | string |
| source    | string |
| timestamp | int    |
| open      | float  |
| high      | float  |
| low       | float  |
| close     | float  |
| volume    | float  |

Signal message fields:

| Field       | Type   |
|-------------|--------|
| symbol      | string |
| strategy_id | string |
| type        | int    | 
| timestamp   | int    |
| message     | string |

`type`: 1 = buy, 2 = sell.

`message` is a human-readable string set by the strategy describing why the signal fired, for example `"EMA20 crossed above EMA50, close=1.0829"`. It is stored as-is in the TSDB and surfaced in Grafana annotations.

---

### Strategy service

Language: Python

A single process that reads from one or more price streams, maintains a rolling window of recent candles in memory, computes indicator values, and evaluates a hardcoded strategy to produce signals. Signals are published to the appropriate signal stream.

#### Candle window

The service maintains a `deque` of the last N candles per symbol, where N is the largest lookback period required by the active strategy. Candles are appended on arrival and the deque is capped at maxlen=N.

```python
from collections import deque
candles = deque(maxlen=50)  # sized to strategy's largest indicator period
```

#### Warm-up gate

The strategy is not evaluated until the deque is full. Until `len(candles) == candles.maxlen`, indicator updates proceed but `evaluate()` returns `None`. This prevents signals from being generated against partial history.

#### Indicators

Indicators are plain Python classes that accept candles one at a time and expose their current value. Example interface:

```python
class EMA:
    def __init__(self, period: int, smoothing: float = 2.0):
        self.period = period
        self.smoothing = smoothing
        self._value = None
        self._count = 0

    def update(self, candle: dict) -> None:
        price = candle["close"]
        if self._value is None:
            self._value = price
        else:
            k = self.smoothing / (self.period + 1)
            self._value = price * k + self._value * (1 - k)
        self._count += 1

    def value(self) -> float | None:
        return self._value if self._count >= self.period else None

    def ready(self) -> bool:
        return self._count >= self.period
```

`value()` returns `None` if the indicator does not yet have enough data. Strategies must check for `None` before using indicator values.

Built-in indicators for v1: `EMA`, `SMA`, `RSI`.

#### Strategy structure

Each strategy is a Python module with two functions:

```python
def indicators() -> list:
    # returns instantiated indicator objects the strategy needs
    ...

def evaluate(candles: deque, inds: dict) -> dict | None:
    # returns a signal dict or None
    ...
```

Example — EMA crossover:

```python
# strategies/ema_crossover.py

def indicators():
    return {
        "ema_fast": EMA(period=20),
        "ema_slow": EMA(period=50),
    }

def evaluate(candles, inds):
    fast = inds["ema_fast"]
    slow = inds["ema_slow"]

    if not (fast.ready() and slow.ready()):
        return None

    # need previous values — maintained as module-level state
    prev_fast = fast.prev_value()
    prev_slow = slow.prev_value()
    curr_fast = fast.value()
    curr_slow = slow.value()

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return {
            "type": 1,
            "message": f"EMA20 crossed above EMA50, close={candles[-1]['close']}"
        }
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return {
            "type": 2,
            "message": f"EMA20 crossed below EMA50, close={candles[-1]['close']}"
        }
    return None
```

The main loop imports the active strategy module, calls `indicators()` once at startup to instantiate indicator objects, then on each candle calls each indicator's `update()` and then `evaluate()`.

#### Deduplication

A signal is suppressed if the last K signals from this strategy had the same type. K is a constant defined in the strategy module (e.g. `DEDUP_WINDOW = 3`). The main loop maintains a small list of the last K signal types per strategy and checks before publishing.

#### Signal publishing

When `evaluate()` returns a non-None signal dict and dedup passes, the main loop assembles the full signal message and publishes it:

```python
redis.xadd(f"signal:{strategy_id}", {
    "symbol": symbol,
    "strategy_id": strategy_id,
    "type": signal["type"],
    "timestamp": candle["timestamp"],
    "message": signal["message"],
})
```

If the `xadd` call fails, the error is logged at error level with the full signal payload and execution continues. Signals are not retried.

#### Directory structure

```
strategy/
    main.py
    indicators/
        __init__.py
        ema.py
        sma.py
        rsi.py
    strategies/
        __init__.py
        ema_crossover.py
    Dockerfile
```

---

### TSDB writer

Language: Python

Subscribes to `price:*` and `signal:*` streams and writes received messages into Redis TimeSeries. This is the only component that writes to Redis TimeSeries.

#### Redis TimeSeries layout

TimeSeries keys use one key per field per symbol. Timestamps are stored in milliseconds.

**Price keys:**

```
price:EURUSD:open
price:EURUSD:high
price:EURUSD:low
price:EURUSD:close
price:EURUSD:volume
```

Each key is created on startup with labels for Grafana filtering:

```python
ts.create(f"price:{symbol}:close",
    labels={"symbol": symbol, "field": "close", "type": "price"},
    duplicate_policy="last")
```

On each price message, all five fields are written at the same timestamp:

```python
ts_ms = candle["timestamp"] * 1000  # convert seconds to milliseconds

for field in ("open", "high", "low", "close", "volume"):
    ts.add(f"price:{symbol}:{field}", ts_ms, candle[field])
```

**Signal keys:**

```
signal:ema_crossover:EURUSD
```

Signal value is the signal type integer (1 = buy, 2 = sell). The `message` string is stored as a label on the data point using `TS.ADD` with `LABELS` — or, since RedisTimeSeries does not support per-sample string metadata, the message is stored in a companion Redis Hash keyed by `signal_meta:{strategy_id}:{symbol}:{timestamp_ms}`, which Grafana annotation queries can optionally retrieve.

```python
ts_ms = signal["timestamp"] * 1000
ts.add(f"signal:{strategy_id}:{symbol}", ts_ms, signal["type"])

# store message for annotation tooltip
redis.hset(
    f"signal_meta:{strategy_id}:{symbol}:{ts_ms}",
    mapping={"message": signal["message"], "type": signal["type"]}
)
```

#### Error handling

If a TimeSeries write fails, the error is logged at error level with the full raw message payload. The message is not requeued. If the Redis connection is lost, the writer enters a reconnect loop with exponential backoff. The stream cursor is not advanced during a failed write, so on reconnect the writer re-reads and retries the message.

---

### Dashboard

Grafana instance using the **Redis Data Source** plugin (`redis-datasource`) pointed at the Redis Stack instance.

#### Plugin provisioning

The plugin is installed automatically via the `GF_INSTALL_PLUGINS` environment variable in docker-compose. The datasource is provisioned at startup via a YAML file in `grafana/provisioning/datasources/`.

```yaml
# grafana/provisioning/datasources/redis.yaml
apiVersion: 1
datasources:
  - name: Redis
    type: redis-datasource
    url: redis://redis:6379
    isDefault: true
```

#### Candlestick panel

Grafana's built-in candlestick panel requires a wide table with columns named `time`, `open`, `high`, `low`, `close`. Since OHLC values are stored in separate TimeSeries keys, the panel is built as follows:

1. Add five queries (A through E), one per field, using `TS.RANGE` over the dashboard time range:
   - Query A: `TS.RANGE price:EURUSD:open $__from $__to`
   - Query B: `TS.RANGE price:EURUSD:high $__from $__to`
   - Query C: `TS.RANGE price:EURUSD:low $__from $__to`
   - Query D: `TS.RANGE price:EURUSD:close $__from $__to`
   - Query E: `TS.RANGE price:EURUSD:volume $__from $__to`

2. In the **Transform** tab, apply **"Join by field"** on `time`. This merges the five series into one wide table with columns `open`, `high`, `low`, `close`, `volume` aligned on timestamp.

3. The candlestick panel maps these columns automatically.

One panel is created per symbol. A separate row per strategy can be added later.

#### Signal annotations

In the candlestick panel's **Alert & Annotation** section, add an annotation query:

```
TS.RANGE signal:ema_crossover:EURUSD $__from $__to
```

The annotation is configured with:
- **Time field**: the timestamp column returned by TS.RANGE
- **Text field**: the value column (1 or 2), optionally mapped to `"Buy"` / `"Sell"` via a value mapping in the panel
- **Color**: a field override rule — value 1 renders green, value 2 renders red

Annotations render as vertical lines overlaid on the candlestick chart. One annotation query per strategy per symbol. No authentication on Grafana. Public read-only access.

---

### Docker Compose

All services run via a single `docker-compose.yml` at the repository root.

#### Services

- `redis` — `redis/redis-stack` image (includes RedisTimeSeries). Exposes port 6379 internally. Mounts a named volume for persistence.
- `grafana` — official Grafana image. Mounts `grafana/provisioning/` for datasource and dashboard config. Installs `redis-datasource` plugin on startup.
- `ingestor` — Python service. Built from `./ingestor/Dockerfile`. Depends on `redis`.
- `strategy` — Python service. Built from `./strategy/Dockerfile`. Depends on `redis`.
- `tsdb-writer` — Python service. Built from `./tsdb-writer/Dockerfile`. Depends on `redis`.

Services that depend on Redis implement a startup retry loop rather than relying solely on compose `depends_on`, since `depends_on` only waits for the container to start, not for Redis to be ready to accept connections.

```python
import time, redis as r

def connect_with_retry(host, port, retries=10, delay=2):
    for i in range(retries):
        try:
            client = r.Redis(host=host, port=port)
            client.ping()
            return client
        except r.exceptions.ConnectionError:
            time.sleep(delay)
    raise RuntimeError("Could not connect to Redis")
```

#### Repository structure

```
/
    docker-compose.yml
    ingestor/
        Dockerfile
        main.py
        candle_builder.py
    strategy/
        Dockerfile
        main.py
        indicators/
        strategies/
    tsdb-writer/
        Dockerfile
        main.py
    grafana/
        provisioning/
            datasources/
                redis.yaml
            dashboards/
                dashboard.json
```

No `init.sql` is required. Redis TimeSeries keys are created explicitly by the tsdb-writer on startup before it begins consuming messages.

---

## Configuration

All services are configured via environment variables.

| Variable         | Service         | Description                                      |
|------------------|-----------------|--------------------------------------------------|
| `REDIS_HOST`     | all             | Redis hostname (default: `redis`)                |
| `REDIS_PORT`     | all             | Redis port (default: `6379`)                     |
| `SYMBOLS`        | ingestor, strategy, tsdb-writer | Comma-separated list of symbols (e.g. `EURUSD,BTCUSDT`) |
| `INTERVAL`       | ingestor        | Candle interval in seconds (e.g. `60`)           |
| `DATA_SOURCE`    | ingestor        | Source identifier (e.g. `binance`)               |
| `STRATEGY`       | strategy        | Name of the strategy module to load (e.g. `ema_crossover`) |
| `CANDLE_WINDOW`  | strategy        | Max candles to hold in memory per symbol         |