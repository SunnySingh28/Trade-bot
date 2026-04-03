FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir websocket-client google-cloud-pubsub

COPY . .

CMD ["python", "ingest.py"]
