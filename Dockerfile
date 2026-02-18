FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY app/ ./app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

ENV LOG_SERVER_PORT=7702
EXPOSE ${LOG_SERVER_PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${LOG_SERVER_PORT}
