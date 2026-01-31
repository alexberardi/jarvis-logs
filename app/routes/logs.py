import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.loki_client import loki_client
from app.models import LogBatch, LogEntry

router = APIRouter()


@router.post("/logs", status_code=204)
async def ingest_log(entry: LogEntry) -> None:
    """Ingest a single log entry."""
    success = await loki_client.push(entry)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to push log to Loki")


@router.post("/logs/batch", status_code=204)
async def ingest_batch(batch: LogBatch) -> None:
    """Ingest a batch of log entries."""
    if not batch.logs:
        return

    success = await loki_client.push_batch(batch.logs)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to push logs to Loki")


@router.get("/logs")
async def query_logs(
    service: str | None = Query(default=None, description="Filter by service name"),
    level: str | None = Query(default=None, description="Filter by log level"),
    search: str | None = Query(default=None, description="Search in message content"),
    since: datetime | None = Query(default=None, description="Start time (ISO format)"),
    until: datetime | None = Query(default=None, description="End time (ISO format)"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
) -> list[dict[str, Any]]:
    """Query logs with optional filters."""
    return await loki_client.query(
        service=service,
        level=level,
        search=search,
        since=since,
        until=until,
        limit=limit,
    )


@router.get("/logs/stream")
async def stream_logs(
    service: str | None = Query(default=None, description="Filter by service name"),
    level: str | None = Query(default=None, description="Filter by log level"),
) -> StreamingResponse:
    """Stream logs in real-time using Server-Sent Events."""

    async def event_generator():
        last_seen = datetime.utcnow()
        while True:
            logs = await loki_client.query(
                service=service,
                level=level,
                since=last_seen,
                limit=50,
            )
            for log in reversed(logs):  # Oldest first for streaming
                import json
                yield f"data: {json.dumps(log)}\n\n"
                # Update last_seen to the log's timestamp
                log_ts = datetime.fromisoformat(log["timestamp"])
                if log_ts > last_seen:
                    last_seen = log_ts

            await asyncio.sleep(1)  # Poll every second

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/services")
async def list_services() -> list[str]:
    """List all services that have sent logs."""
    # Query Loki for unique service labels
    # This is a workaround since Loki doesn't have a direct label values endpoint
    # that's easily accessible without auth
    logs = await loki_client.query(limit=1000)
    services = set()
    for log in logs:
        if log.get("service"):
            services.add(log["service"])
    return sorted(services)
