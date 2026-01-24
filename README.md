# jarvis-logs

Centralized logging service for jarvis microservices. Receives logs via REST API and forwards to Loki for storage, with Grafana for visualization.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────┐     ┌────────────────┐
│  Microservices  │────▶│  jarvis-logs     │────▶│  Loki          │────▶│  Grafana       │
│  (jarvis-log    │     │  FastAPI (8006)  │     │  (3100)        │     │  (3000)        │
│   client pkg)   │     └──────────────────┘     └────────────────┘     └────────────────┘
└─────────────────┘
```

## Quick Start

```bash
# Start the stack (jarvis-logs + Loki + Grafana)
docker-compose up -d

# View logs in Grafana
open http://localhost:3000
# Login: admin / jarvis
```

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v0/logs` | Ingest single log entry |
| POST | `/api/v0/logs/batch` | Ingest batch of logs |
| GET | `/api/v0/logs` | Query logs with filters |
| GET | `/api/v0/logs/stream` | Real-time log stream (SSE) |
| GET | `/api/v0/services` | List services with logs |
| GET | `/health` | Health check |

## API Examples

```bash
# Send a log
curl -X POST http://localhost:8006/api/v0/logs \
  -H "Content-Type: application/json" \
  -d '{
    "service": "test-service",
    "level": "INFO",
    "message": "Hello from curl",
    "context": {"request_id": "abc123"}
  }'

# Query logs
curl "http://localhost:8006/api/v0/logs?service=test-service&limit=10"

# Filter by level
curl "http://localhost:8006/api/v0/logs?level=ERROR&limit=50"

# Search message content
curl "http://localhost:8006/api/v0/logs?search=error&limit=20"

# Stream logs (SSE)
curl -N "http://localhost:8006/api/v0/logs/stream?service=llm-proxy"
```

## Client Integration

Install the client package in your service:

```bash
pip install -e ../jarvis-log-client
```

```python
from jarvis_log_client import JarvisLogger

logger = JarvisLogger(
    service="my-service",
    console_level="WARNING",  # Quiet console
    remote_level="DEBUG",     # Send everything to server
)

logger.info("Service started")
logger.error("Something failed", error=str(e), request_id=req_id)
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| jarvis-logs | 8006 | REST API for log ingestion/query |
| Loki | 3100 | Log storage and indexing |
| Grafana | 3000 | Dashboard and visualization |

## Grafana Dashboard

A pre-configured dashboard is available at `http://localhost:3000/d/jarvis-logs`:

- Error logs panel (all services)
- Log volume by level (time series)
- Log volume by service (time series)
- All logs panel with filters

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOKI_URL` | `http://loki:3100` | Loki server URL |
| `LOG_SERVER_PORT` | `8006` | jarvis-logs port |
| `LOG_API_KEY` | (none) | Optional API key for ingestion |
| `ADMIN_API_KEY` | (none) | Admin operations key |

### Loki Configuration

Edit `loki-config.yaml` to customize:

- `limits_config.retention_period`: Log retention (default: 7 days)
- `limits_config.ingestion_rate_mb`: Max ingestion rate
- `limits_config.max_line_size`: Max log line size

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start Loki/Grafana (required for jarvis-logs to work)
docker-compose up -d loki grafana

# Run jarvis-logs locally
./run.sh
```

## Log Format

```json
{
  "timestamp": "2026-01-22T10:30:00.000000",
  "service": "llm-proxy",
  "level": "INFO",
  "message": "Request processed",
  "context": {
    "request_id": "abc123",
    "duration_ms": 150,
    "model": "llama-3.2"
  }
}
```

## Querying with LogQL (Grafana)

```logql
# All errors from llm-proxy
{service="llm-proxy", level="ERROR"}

# Search for specific text
{service=~".+"} |~ "timeout"

# Filter by context field (JSON)
{service="command-center"} | json | request_id="abc123"
```
