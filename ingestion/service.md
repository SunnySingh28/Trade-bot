# Ingestion Service – Copilot Context

## Purpose
The ingestion service is responsible for consuming real-time market data from WebSocket sources and publishing normalized events to the Pub-Sub system.

## Responsibilities
- Maintain WebSocket connections to market data providers
- Handle reconnects and heartbeat failures
- Validate incoming data schema
- Normalize data fields
- Attach consistent timestamps
- Publish events to Pub-Sub topics

## Implementation
The sample code that is provided is correct, yet uses google pubsub. We need to port it over to Redis Pubsub instead and create a function that actually sends the data to the topic. This service, like others in this project is event driven, and for each relevant event a push must be done to the prices topic after processing.

No other changes need to be made for this component.