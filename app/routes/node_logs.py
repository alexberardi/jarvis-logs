"""Node-authenticated log endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.auth import NodeValidationResult, require_node_auth
from app.loki_client import loki_client
from app.models import LogBatch, LogEntry

router = APIRouter()


@router.post("/node/logs", status_code=204)
async def ingest_node_log(
    entry: LogEntry,
    node_auth: NodeValidationResult = Depends(require_node_auth),
) -> None:
    """Ingest a single log entry from an authenticated node.

    Nodes authenticate using X-Node-Id and X-Node-Key headers.
    The node must have access to the 'jarvis-logs' service.
    """
    # Enrich log entry with node context
    context = entry.context or {}
    context["node_id"] = node_auth.node_id
    context["user_id"] = node_auth.user_id
    entry.context = context

    success = await loki_client.push(entry)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to push log to Loki")


@router.post("/node/logs/batch", status_code=204)
async def ingest_node_batch(
    batch: LogBatch,
    node_auth: NodeValidationResult = Depends(require_node_auth),
) -> None:
    """Ingest a batch of log entries from an authenticated node.

    Nodes authenticate using X-Node-Id and X-Node-Key headers.
    The node must have access to the 'jarvis-logs' service.
    """
    if not batch.logs:
        return

    # Enrich all log entries with node context
    for entry in batch.logs:
        context = entry.context or {}
        context["node_id"] = node_auth.node_id
        context["user_id"] = node_auth.user_id
        entry.context = context

    success = await loki_client.push_batch(batch.logs)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to push logs to Loki")
