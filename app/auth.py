import json
import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import httpx
from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)


async def require_app_auth(
    request: Request,
    x_jarvis_app_id: Optional[str] = Header(None),
    x_jarvis_app_key: Optional[str] = Header(None),
) -> None:
    """
    Enforce app-to-app authentication by forwarding headers to jarvis-auth /internal/app-ping.
    Health endpoints remain unauthenticated.
    """
    # Skip auth for health endpoints
    if request.url.path in ("/health", "/ping"):
        return

    if not x_jarvis_app_id or not x_jarvis_app_key:
        raise HTTPException(status_code=401, detail="Missing app credentials")

    jarvis_auth_base = os.getenv("JARVIS_AUTH_BASE_URL")
    if not jarvis_auth_base:
        raise HTTPException(status_code=500, detail="JARVIS_AUTH_BASE_URL not configured")

    app_ping = jarvis_auth_base.rstrip("/") + "/internal/app-ping"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(
                app_ping,
                headers={
                    "X-Jarvis-App-Id": x_jarvis_app_id,
                    "X-Jarvis-App-Key": x_jarvis_app_key,
                },
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Auth service unavailable: {exc}",
            ) from exc

    if resp.status_code != 200:
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid app credentials")
        raise HTTPException(status_code=resp.status_code, detail="App auth failed")

    # Stash calling app in request state
    try:
        body = resp.json()
        request.state.calling_app_id = body.get("app_id") or x_jarvis_app_id
    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        logger.debug("Failed to parse app_id from auth response: %s", exc)
        request.state.calling_app_id = x_jarvis_app_id


@dataclass
class NodeValidationResult:
    """Result of node credential validation."""
    valid: bool
    node_id: str | None = None
    user_id: int | None = None
    reason: str | None = None


# Cache for node validation results (expires every 60 seconds)
_node_validation_cache: dict[str, tuple[NodeValidationResult, float]] = {}
CACHE_TTL_SECONDS = 60


def _get_cached_validation(cache_key: str) -> NodeValidationResult | None:
    """Get cached validation result if not expired."""
    if cache_key in _node_validation_cache:
        result, timestamp = _node_validation_cache[cache_key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return result
        del _node_validation_cache[cache_key]
    return None


def _cache_validation(cache_key: str, result: NodeValidationResult) -> None:
    """Cache a validation result."""
    _node_validation_cache[cache_key] = (result, time.time())


def _get_service_credentials() -> tuple[str, str]:
    """Get jarvis-logs app credentials for authenticating to jarvis-auth."""
    app_id = os.getenv("JARVIS_LOGS_APP_ID", "jarvis-logs")
    app_key = os.getenv("JARVIS_LOGS_APP_KEY")
    return app_id, app_key


async def validate_node_credentials(
    node_id: str,
    node_key: str,
    service_id: str = "jarvis-logs",
) -> NodeValidationResult:
    """
    Validate node credentials against jarvis-auth service.
    Results are cached for 60 seconds to reduce auth service load.
    """
    cache_key = f"{node_id}:{node_key}:{service_id}"
    cached = _get_cached_validation(cache_key)
    if cached is not None:
        return cached

    jarvis_auth_base = os.getenv("JARVIS_AUTH_BASE_URL")
    if not jarvis_auth_base:
        return NodeValidationResult(valid=False, reason="JARVIS_AUTH_BASE_URL not configured")

    app_id, app_key = _get_service_credentials()
    if not app_key:
        return NodeValidationResult(valid=False, reason="JARVIS_LOGS_APP_KEY not configured")

    validate_url = jarvis_auth_base.rstrip("/") + "/internal/validate-node"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(
                validate_url,
                headers={
                    "X-Jarvis-App-Id": app_id,
                    "X-Jarvis-App-Key": app_key,
                },
                json={
                    "node_id": node_id,
                    "node_key": node_key,
                    "service_id": service_id,
                },
            )
        except httpx.RequestError as exc:
            return NodeValidationResult(valid=False, reason=f"Auth service unavailable: {exc}")

    if resp.status_code != 200:
        return NodeValidationResult(valid=False, reason=f"Auth service error: {resp.status_code}")

    try:
        body = resp.json()
        result = NodeValidationResult(
            valid=body.get("valid", False),
            node_id=body.get("node_id"),
            user_id=body.get("user_id"),
            reason=body.get("reason"),
        )
        _cache_validation(cache_key, result)
        return result
    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        logger.debug("Failed to parse node validation response: %s", exc)
        return NodeValidationResult(valid=False, reason=f"Invalid response from auth service: {exc}")


async def require_node_auth(
    request: Request,
    x_node_id: Optional[str] = Header(None),
    x_node_key: Optional[str] = Header(None),
) -> NodeValidationResult:
    """
    Enforce node authentication by validating credentials against jarvis-auth.
    The node must have access to the 'jarvis-logs' service.

    Returns the validation result containing node_id and user_id on success.
    """
    if not x_node_id or not x_node_key:
        raise HTTPException(status_code=401, detail="Missing node credentials")

    result = await validate_node_credentials(x_node_id, x_node_key, "jarvis-logs")

    if not result.valid:
        raise HTTPException(
            status_code=403,
            detail=result.reason or "Invalid node credentials",
        )

    # Store validated node info in request state
    request.state.node_id = result.node_id
    request.state.user_id = result.user_id

    return result
