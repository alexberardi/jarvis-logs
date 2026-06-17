from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import service_config
from app.auth import require_app_auth
from app.loki_client import loki_client
from app.routes import logs, node_logs
from app.services.settings_service import get_settings_service
from jarvis_settings_client import create_combined_auth, create_settings_router, create_superuser_auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    service_config.init()
    yield
    # Shutdown
    service_config.shutdown()
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
    allow_credentials=False,
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

_settings_router = create_settings_router(
    service=get_settings_service(),
    auth_dependency=create_combined_auth(service_config.get_auth_url()),
    write_auth_dependency=create_superuser_auth(service_config.get_auth_url()),
)
app.include_router(_settings_router, prefix="/settings", tags=["settings"])


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
