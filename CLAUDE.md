# jarvis-logs

Centralized log ingestion and query service. Thin FastAPI shim over **Loki** (storage/indexing) with **Grafana** for visualization. Logs flow in from services (app-creds) and nodes (node-creds) and out to Grafana dashboards or the query API.

> **What this service is:** a write/read API for Loki, with auth and node enrichment. It does not store logs itself — Loki does. It does not run dashboards — Grafana does.

---

## Topology

```
services / nodes  ──app-creds or node-creds──▶  jarvis-logs (7702)  ──/loki/api/v1/push──▶  Loki (7032)
                                                                                              │
                                                                                              ▼
                                                                                          Grafana (7033)
                                                                                          [admin / jarvis]
```

The three processes (Loki, Grafana, jarvis-logs API) are usually run as one docker-compose stack but are otherwise independent.

---

## Quick Reference

```bash
# Full stack (Loki + Grafana + API)
./run.sh

# Tests
./run-tests.sh
# or: pytest

# Grafana
open http://localhost:7033   # admin / jarvis
```

---

## Dependency graph

**Upstream (jarvis-logs depends on):**
- **Loki** (port 7032) — required. Push and query backend. If Loki is down, ingest returns 502 and query returns `[]`.
- **jarvis-auth** (port 7701) — required at request time:
  - `/api/v0/logs*` calls `/internal/app-ping` to validate app credentials
  - `/api/v0/node/logs*` calls `/internal/validate-node` with `service_id="jarvis-logs"` (and caches the result for 60s)
- **jarvis-config-service** (port 7700) — used for service discovery (finding the auth URL); falls back to `JARVIS_AUTH_BASE_URL` env var
- **Grafana** (port 7033) — required only for the *human* dashboard experience; not in the API request path

**Downstream (depends on jarvis-logs):**
- **All services that emit logs** via `jarvis-log-client` library — but the library degrades to console-only on failure, so callers stay up
- **jarvis-mcp** — debug log query tools (`query_logs`, `logs_tail`, `get_log_stats`) hit this service
- **Pi Zero nodes** — POST to `/api/v0/node/logs*` from `jarvis-node-setup`

**Impact if down:**
- Logs go to console only at every caller; nobody crashes
- Grafana dashboards have no fresh data
- MCP log-query tools return errors

---

## Lifecycle / common operations

### 1. Service log ingestion (the hot path)

```
Service               jarvis-logs                    jarvis-auth                 Loki
   │ POST /api/v0/logs ──▶ require_app_auth ──/internal/app-ping──▶  200 OK
   │   X-Jarvis-App-Id          │                       │
   │   X-Jarvis-App-Key         │                       │
   │                            │
   │                       LokiClient.push ──/loki/api/v1/push──▶  204
   │ ◀── 204 No Content ───
```

`require_app_auth` (`app/auth.py`) is mounted as a router-level dependency on the `logs.router` in `main.py`. **Every request to `/api/v0/logs*` round-trips to auth.** No caching for service auth (only for node auth).

### 2. Node log ingestion

```
Node                  jarvis-logs                    jarvis-auth                 Loki
   │ POST /api/v0/node/logs ─▶ require_node_auth
   │   X-Node-Id                 │
   │   X-Node-Key                │
   │                  ┌──── 60s cache hit? ────────────────────────┐
   │                  │ NO ▼                                       │ YES (skip auth)
   │                  validate ──/internal/validate-node──▶  valid │
   │                  with service_id="jarvis-logs"                │
   │                  ◀────────────────────────────────────────────┘
   │
   │                  enrich context with node_id + user_id
   │                  LokiClient.push ──▶  Loki
   │ ◀── 204 ──
```

Node validation is cached in-process for 60s (`CACHE_TTL_SECONDS` in `app/auth.py`), keyed by `(node_id, node_key, service_id)`. **This means a revoked node still works for up to 60s.** Configurable via the `auth.cache_ttl_seconds` setting.

### 3. Query

`GET /api/v0/logs` builds a LogQL query of the form `{service="X",level="Y"} |~ "search"` and calls Loki's `query_range`. Default time range: last 1 hour. Max limit: 1000 per request. Context (the `dict[str, Any]` payload) is extracted from the message by splitting on ` | ` and JSON-parsing the suffix.

### 4. Streaming

`GET /api/v0/logs/stream` uses SSE. It polls Loki every 1 second with a 50-row limit — not a true tail. Adequate for low-volume dashboards; for high-throughput tailing, query Loki directly or use Grafana's Live tail.

---

## "How to..." recipes

### Add a new endpoint that accepts service logs

Add to `app/routes/logs.py`. The `require_app_auth` dependency is already applied at the router level — no extra work. The calling app's id is available as `request.state.calling_app_id`.

### Add a new endpoint that accepts node logs

Add to `app/routes/node_logs.py`. Use `node_auth: NodeValidationResult = Depends(require_node_auth)` for the validated identity. `node_auth.node_id` and `node_auth.user_id` are the keys to enrich logs with.

### Add a new setting

Append to `SETTINGS_DEFINITIONS` in `app/services/settings_definitions.py`. The standard `jarvis-settings-client` flow handles persistence and the `/settings/*` router. Don't write directly to the settings table.

### Add a new log label / dimension

Today, Loki streams are labeled `{service, level}`. Adding a new label means:
1. Update `LokiClient.push_batch` in `app/loki_client.py` (label dict in the stream payload)
2. Update `LokiClient.query` to allow filtering on it
3. Ensure callers (via `jarvis-log-client`) set the new field

**Caution:** Loki performance degrades with high-cardinality labels. Service and level are low-cardinality and safe. Don't add `request_id`, `user_id`, etc. as labels — those go in the message context.

---

## Invariants & gotchas

1. **`jarvis-log-client` falls back to console silently when push fails.** This is by design (a logging library should never crash the host service) but it means a misconfigured service appears to log fine locally while nothing reaches Loki. If you can't find a service's logs in Grafana, **first check whether `jarvis-log-client` initialized successfully** in that service — auth errors or unreachable jarvis-logs URL cause silent fallback. The current jarvis-log-client users in the stack: auth, command-center, llm-proxy, notifications, settings-server, tts, whisper.
2. **Node access must include `service_id="jarvis-logs"`.** Nodes that only have command-center access **cannot** push to `/api/v0/node/logs*` — they'll get a 403. To grant: `POST /admin/nodes/{node_id}/services` on jarvis-auth with `{"service_id": "jarvis-logs"}` (admin-token-protected). The "Node auth 403 on logs" issue tracked in dev memory likely traces here. Verify with `GET /admin/nodes/{node_id}` on auth. (Prod has this granted for all nodes; some dev/laptop installs may not.)
3. **Service auth has no cache; node auth caches 60s.** Every service log call hits jarvis-auth `/internal/app-ping`. Under heavy log volume, this can put pressure on auth. If a hardening pass is warranted, add a TTL cache for service auth too (and bump the node TTL up — 60s is conservative).
4. **The settings router uses combined auth for reads.** Reads accept superuser JWT OR app-to-app credentials (so apps can display settings). Writes require superuser JWT only. Same pattern as jarvis-auth.
5. **Loki retention is enforced by Loki, not the app.** The `logs.retention_days=30` setting in `settings_definitions.py` is **informational** — nothing in this service reads it for retention. Actual retention lives in `loki-config.yaml`. If you change the setting, also update Loki's config; otherwise they'll drift.
6. **API version is `/api/v0` permanently as of today.** Treat `v0` as the stable surface for now; no v1 is planned. Don't introduce versioning churn.
7. **`/health` and `/ping` are open.** They bypass auth because they're mounted on the root app (`app.get(...)`) rather than under `/api/v0` which has the auth dependency. The `if path in ("/health", "/ping"): return` check in `require_app_auth` is defensive belt-and-suspenders — unreachable in normal routing.
8. **Streaming endpoint polls Loki at 1Hz.** Not a true tail. For high-volume real-time monitoring, use Grafana or query Loki directly. Don't lean on `/api/v0/logs/stream` for production observability.
9. **Context is encoded in the log line, not as a label.** The message stored in Loki is `"<message> | <json-context>"` when context is present. Queries parse this back into a dict in `LokiClient.query`. If you change this delimiter, also change the parser.

---

## Debug: "service X has no logs in Loki" / "node gets 403"

1. Verify Loki has the service: `curl http://localhost:7032/loki/api/v1/label/service/values` — if your service isn't listed, it's not pushing successfully.
2. **`jarvis-log-client` swallows push failures and falls back to console** — so the calling service won't appear broken. Check the calling service's container stdout for "Failed to push log" or similar from `JarvisLogger`. Common causes: missing/wrong `JARVIS_APP_KEY`, jarvis-logs URL not discoverable (no `JARVIS_CONFIG_URL`), or auth-service down.
3. For nodes getting 403: check service access — call `GET /admin/nodes/{node_id}` on jarvis-auth (with admin token) and verify `jarvis-logs` is in the granted services. Grant it with `POST /admin/nodes/{node_id}/services` body `{"service_id": "jarvis-logs"}`.
4. For services getting 401: verify the calling service has `JARVIS_APP_ID` and `JARVIS_APP_KEY` set, and that the app-client exists in jarvis-auth (`GET /admin/app-clients`).
5. Test ingest manually:
   ```bash
   curl -X POST http://localhost:7702/api/v0/logs \
     -H "X-Jarvis-App-Id: jarvis-logs" \
     -H "X-Jarvis-App-Key: $JARVIS_APP_KEY" \
     -H "Content-Type: application/json" \
     -d '{"service":"smoke-test","level":"INFO","message":"hello"}'
   ```
   Expect 204. Then query Loki: `curl 'http://localhost:7032/loki/api/v1/query_range?query=%7Bservice%3D%22smoke-test%22%7D&limit=10'`.
6. As a quick health check on the whole pipeline: `curl http://localhost:7032/loki/api/v1/label/service/values` should list multiple services in a healthy install (prod typically shows all 7 emitters). A list with only one or two services suggests a system-wide auth or config issue, not a single-service bug.

---

## API surface

### Service-authenticated (`/api/v0/*`, `X-Jarvis-App-Id` + `X-Jarvis-App-Key`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/v0/logs` | Single log → Loki (204 / 502 on Loki failure) |
| POST | `/api/v0/logs/batch` | Batch logs |
| GET | `/api/v0/logs` | Query (service, level, search, since, until, limit≤1000) |
| GET | `/api/v0/logs/stream` | SSE; 1Hz poll of Loki |
| GET | `/api/v0/services` | Unique service labels seen in last 1h of logs (scans up to 1000) |

### Node-authenticated (`/api/v0/node/*`, `X-Node-Id` + `X-Node-Key`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/v0/node/logs` | Single log, enriched with `node_id` + `user_id` |
| POST | `/api/v0/node/logs/batch` | Batch, same enrichment |

### Settings (`/settings/*`, library mount)
- Reads: superuser JWT OR app credentials
- Writes: superuser JWT only

### Open
| Method | Path |
|---|---|
| GET | `/health` (also reports Loki health) |
| GET | `/ping` |

---

## Data model

The app is largely stateless. Two persisted surfaces:

| Where | What |
|---|---|
| **Loki** | All log data — streams keyed by `{service, level}`, values are `[ts_ns, message_with_optional_context]`. Retention configured in `loki-config.yaml`. |
| **Postgres** | The `settings` table (multi-tenant scoped, same pattern as other services) — managed by Alembic |

Pydantic models in `app/models.py`:
```python
LogEntry(timestamp, service, level, message, context)
LogBatch(logs: list[LogEntry])
LogQuery(...)  # not currently used by any endpoint; legacy
```

`level` regex: `^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$`. Anything outside this set rejected with 422.

---

## Config surface

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LOKI_URL` | no | `http://loki:7032` | Loki base URL (push + query) |
| `LOG_SERVER_PORT` | no | `7702` | API port |
| `JARVIS_APP_ID` | yes (for node-auth path) | `jarvis-logs` | This service's app credential for calling jarvis-auth `/internal/validate-node` |
| `JARVIS_APP_KEY` | yes | — | Paired key |
| `JARVIS_CONFIG_URL` | yes | — | Config-service URL for discovering jarvis-auth |
| `JARVIS_AUTH_BASE_URL` | optional legacy | — | Direct override; only used if config-client unavailable |
| `DATABASE_URL` | yes | — | Postgres for settings table |
| `CACHE_TTL_SECONDS` | no | `60` | Node-auth result cache TTL. Also settable via setting `auth.cache_ttl_seconds`. |
| `LOG_RETENTION_DAYS` | no (informational) | `30` | Not enforced by this service; mirror in `loki-config.yaml` |
| `LOG_MAX_BATCH_SIZE` | no | `1000` | Not currently enforced |
| `LOG_QUERY_LIMIT` | no | `1000` | Cap on query limit |

---

## Architecture

```
app/
├── main.py                              # FastAPI factory, lifespan, router wiring
├── auth.py                              # require_app_auth, require_node_auth (with 60s cache)
├── service_config.py                    # jarvis-config-client wrapper + env fallback
├── loki_client.py                       # Push + LogQL query + health
├── models.py                            # LogEntry, LogBatch, LogQuery
├── db/
│   ├── models.py                        # Settings table model
│   └── session.py
├── routes/
│   ├── logs.py                          # /api/v0/logs* — app-auth
│   └── node_logs.py                     # /api/v0/node/logs* — node-auth
└── services/
    ├── settings_definitions.py          # SettingDefinition entries
    └── settings_service.py              # Backing store for settings router

alembic/                                 # Settings migrations
loki-config.yaml                         # Loki config (retention lives here)
grafana/                                 # Provisioning (datasources, dashboards)
```

---

## Testing

- **Unit tests only.** Loki is **not** spun up — tests mock the LokiClient or the httpx client. Same constraint as the rest of the stack.
- Auth dependencies overridden in `tests/conftest.py`.
- When adding a new route: write a TestClient test covering 401/403/200 paths, and mock the LokiClient response.

Run: `./run-tests.sh` (or `pytest`).

---

## Failure modes

| Failure | Behavior |
|---|---|
| Loki down | Ingest returns 502; query returns `[]`; `/health` returns `degraded` |
| jarvis-auth down | All `/api/v0/*` returns 502 (auth check fails) |
| Wrong app credentials | 401 |
| Node lacks `jarvis-logs` service access | 403 (most common cause of "logs missing for node X") |
| `JARVIS_APP_KEY` unset | Node ingestion fails with "JARVIS_APP_KEY not configured" — service can't call auth on the node's behalf |
| Config-client uninitialized AND no `JARVIS_AUTH_BASE_URL` | 503 on every authed request |
| Loki retention drops old logs | Loki silently — the app is unaware |

---

## Out of scope / explicitly not here

- **Log retention enforcement.** Loki owns this.
- **Alerting.** No rules engine; that's Grafana's domain.
- **Multi-tenant log isolation.** Logs are not scoped by household today. If you add household-scoped views, do it via filtering at query time (low-cardinality label OR client-side), not Loki streams.
- **Log forwarding to external sinks** (Datadog, Sentry, etc.). Loki is the terminus.
- **High-throughput tailing.** Use Grafana Live or Loki directly.
