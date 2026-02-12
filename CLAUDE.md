# jarvis-logs

Centralized logging service. Receives logs from microservices, stores in Loki, visualizes in Grafana.

## Quick Reference

```bash
# Run full stack (Loki + Grafana + API)
./run.sh

# Run API only (assumes Loki/Grafana running)
./run-local.sh

# Test
./run-tests.sh

# Grafana dashboard
open http://localhost:8015  # admin/jarvis
```

## Architecture

```
app/
├── main.py           # FastAPI app
├── routes/
│   ├── logs.py       # Log ingestion and querying
│   └── node_logs.py  # Node-specific logs
├── loki_client.py    # Loki push/query
└── auth.py           # App-to-app auth

docker-compose.yaml   # Loki (3100), Grafana (3000), API (8006)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOKI_URL` | http://loki:3100 | Loki server URL |
| `LOG_SERVER_PORT` | 8006 | API port |
| `LOG_API_KEY` | - | API key for log ingestion |
| `ADMIN_API_KEY` | - | Admin endpoint protection |

## API Endpoints

**Ingestion:**
- `POST /api/v0/logs` → Single log
- `POST /api/v0/logs/batch` → Batch logs

**Querying:**
- `GET /api/v0/logs` → Query with filters
- `GET /api/v0/logs/stream` → Real-time stream (SSE)
- `GET /api/v0/services` → List services with logs

**Health:**
- `GET /health` → Health check

## Query Parameters

```bash
# Filter by service, level, time range
curl "http://localhost:8006/api/v0/logs?service=auth&level=ERROR&since_minutes=60"
```

## Linked Services

| Service | Port | Purpose |
|---------|------|---------|
| Loki | 3100 | Log storage/indexing |
| Grafana | 8015 | Dashboards |
| API | 8006 | REST interface |

## Authentication

Clients authenticate via `X-Jarvis-App-Id` + `X-Jarvis-App-Key` headers.
Credentials validated against jarvis-auth service.

## Dependencies

- FastAPI, httpx
- Loki (log storage)
- Grafana (visualization)
