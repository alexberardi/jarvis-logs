FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app

ENV LOG_SERVER_PORT=8006
EXPOSE ${LOG_SERVER_PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${LOG_SERVER_PORT}
