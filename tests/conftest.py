import os
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set test environment variables before importing app
os.environ["LOKI_URL"] = "http://test-loki:3100"
os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"


@pytest.fixture
def sample_log_entry_data() -> dict:
    """Sample log entry data for testing."""
    return {
        "service": "test-service",
        "level": "INFO",
        "message": "Test log message",
        "context": {"request_id": "abc123"},
    }


@pytest.fixture
def sample_log_entry_minimal() -> dict:
    """Minimal log entry data."""
    return {
        "service": "test-service",
        "level": "DEBUG",
        "message": "Minimal log",
    }


@pytest.fixture
def sample_batch_data() -> dict:
    """Sample batch of log entries."""
    return {
        "logs": [
            {"service": "svc1", "level": "INFO", "message": "Log 1"},
            {"service": "svc1", "level": "ERROR", "message": "Log 2"},
            {"service": "svc2", "level": "WARNING", "message": "Log 3"},
        ]
    }


@pytest.fixture
def mock_loki_push_success():
    """Mock successful Loki push."""
    with patch("app.loki_client.loki_client.push", new_callable=AsyncMock) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_loki_push_failure():
    """Mock failed Loki push."""
    with patch("app.loki_client.loki_client.push", new_callable=AsyncMock) as mock:
        mock.return_value = False
        yield mock


@pytest.fixture
def mock_loki_push_batch_success():
    """Mock successful Loki batch push."""
    with patch("app.loki_client.loki_client.push_batch", new_callable=AsyncMock) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_loki_query():
    """Mock Loki query results."""
    with patch("app.loki_client.loki_client.query", new_callable=AsyncMock) as mock:
        mock.return_value = [
            {
                "timestamp": datetime.utcnow().isoformat(),
                "service": "test-service",
                "level": "INFO",
                "message": "Test message",
                "context": None,
            }
        ]
        yield mock


@pytest.fixture
def mock_auth_success():
    """Mock successful auth validation."""
    async def mock_require_auth(*args, **kwargs):
        return None

    with patch("app.auth.require_app_auth", side_effect=mock_require_auth) as mock:
        yield mock


@pytest.fixture
def valid_auth_headers() -> dict:
    """Valid authentication headers."""
    return {
        "X-Jarvis-App-Id": "test-app",
        "X-Jarvis-App-Key": "test-key-12345",
    }
