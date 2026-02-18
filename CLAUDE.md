# jarvis-logs

Centralized logging service. Receives logs from microservices, stores in Loki, visualizes in Grafana.

## Quick Reference

```bash
# Setup
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Run full stack (Loki + Grafana + API)
./run.sh

# Run API only (assumes Loki/Grafana running)
./run-local.sh

# Test
./run-tests.sh

# Grafana dashboard
open http://localhost:7033  # admin/jarvis
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

docker-compose.yaml   # Loki (7032), Grafana (3000), API (7702)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOKI_URL` | http://loki:7032 | Loki server URL |
| `LOG_SERVER_PORT` | 7702 | API port |
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
curl "http://localhost:7702/api/v0/logs?service=auth&level=ERROR&since_minutes=60"
```

## Linked Services

| Service | Port | Purpose |
|---------|------|---------|
| Loki | 7032 | Log storage/indexing |
| Grafana | 7033 | Dashboards |
| API | 7702 | REST interface |

## Authentication

Clients authenticate via `X-Jarvis-App-Id` + `X-Jarvis-App-Key` headers.
Credentials validated against jarvis-auth service.

## Dependencies

**Python Libraries:**
- FastAPI, httpx

**Service Dependencies:**
- ✅ **Required**: Loki (7032) - Log storage and indexing
- ✅ **Required**: Grafana (7033) - Visualization and dashboards
- ✅ **Required**: `jarvis-auth` (7701) - App-to-app authentication validation
- ⚠️ **Optional**: `jarvis-config-service` (7700) - Service discovery

**Used By:**
- ALL services via `jarvis-log-client` library
- `jarvis-mcp` - Log querying tools for Claude Code

**Impact if Down:**
- ⚠️ Logs go to console only (services continue running)
- ⚠️ No centralized log aggregation
- ⚠️ No Grafana dashboards
- ✅ Services degrade gracefully (console logging fallback)
