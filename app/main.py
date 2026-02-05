from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_app_auth
from app.loki_client import loki_client
from app.routes import logs, node_logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    yield
    # Shutdown
    await loki_client.close()


app = FastAPI(
    title="Jarvis Logs",
    description="Centralized logging service for jarvis microservices",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include app-authenticated routes (services)
app.include_router(
    logs.router,
    prefix="/api/v0",
    tags=["logs"],
    dependencies=[Depends(require_app_auth)],
)

# Include node-authenticated routes (nodes use their own auth)
app.include_router(
    node_logs.router,
    prefix="/api/v0",
    tags=["node-logs"],
)

# Add settings router from shared library
from jarvis_settings_client import create_settings_router
from app.services.settings_service import get_settings_service

_settings_router = create_settings_router(
    service=get_settings_service(),
    auth_dependency=require_app_auth,
)
app.include_router(_settings_router, prefix="/v1/settings", tags=["settings"])


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    loki_healthy = await loki_client.health_check()
    return {
        "status": "healthy" if loki_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "loki": "available" if loki_healthy else "unavailable",
        },
    }


@app.get("/ping")
async def ping() -> dict:
    """Simple ping endpoint."""
    return {"message": "pong"}
