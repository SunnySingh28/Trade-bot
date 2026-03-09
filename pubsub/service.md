# Pub-Sub Module – Copilot Context

## Purpose
This module provides asynchronous, event-driven communication between services.

## Responsibilities
- Define topics and message formats
- Handle producers and consumers
- Ensure message durability

## Topics
| Topic Name | Description |
|----------|-------------|
| market.prices | Live tick data |
| market.candles | Aggregated OHLCV data |
| trade.signals | Buy/Sell signals |

## Message Guarantees
- At-least-once delivery
- Partition by symbol
- Ordered delivery per symbol

## Producers
- Ingestion Service
- Strategy Service

## Consumers
- Strategy Service
- timeseries service

## Coding Guidelines
- Keep topic names centralized
- Use schema validation
- Handle retries and backoff
- Support dead-letter queues
- Avoid business logic in this layer