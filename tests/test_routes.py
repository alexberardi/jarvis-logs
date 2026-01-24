"""Tests for FastAPI routes."""

import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.models import LogEntry


# Set test environment
os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"


@pytest.fixture
def client() -> TestClient:
    """Create a test client with mocked auth."""
    # Import app fresh for each test
    from app.main import app

    # Override the auth dependency
    async def mock_auth():
        return None

    from app.auth import require_app_auth
    app.dependency_overrides[require_app_auth] = mock_auth

    yield TestClient(app)

    # Clean up
    app.dependency_overrides.clear()


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_ping(self):
        """Test ping endpoint."""
        from app.main import app
        client = TestClient(app)
        response = client.get("/ping")
        assert response.status_code == 200
        assert response.json() == {"message": "pong"}

    def test_health_loki_available(self):
        """Test health endpoint when Loki is available."""
        from app.main import app
        with patch("app.loki_client.loki_client.health_check", new_callable=AsyncMock) as mock:
            mock.return_value = True
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["services"]["loki"] == "available"

    def test_health_loki_unavailable(self):
        """Test health endpoint when Loki is unavailable."""
        from app.main import app
        with patch("app.loki_client.loki_client.health_check", new_callable=AsyncMock) as mock:
            mock.return_value = False
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert data["services"]["loki"] == "unavailable"


class TestIngestLog:
    """Tests for log ingestion endpoints."""

    def test_ingest_single_log_success(self, client: TestClient):
        """Test ingesting a single log entry."""
        with patch("app.loki_client.loki_client.push", new_callable=AsyncMock) as mock:
            mock.return_value = True
            response = client.post(
                "/api/v0/logs",
                json={
                    "service": "test-service",
                    "level": "INFO",
                    "message": "Test message",
                },
            )
            assert response.status_code == 204
            mock.assert_called_once()

    def test_ingest_single_log_with_context(self, client: TestClient):
        """Test ingesting a log with context."""
        with patch("app.loki_client.loki_client.push", new_callable=AsyncMock) as mock:
            mock.return_value = True
            response = client.post(
                "/api/v0/logs",
                json={
                    "service": "test-service",
                    "level": "ERROR",
                    "message": "Error occurred",
                    "context": {"error_code": "E001", "user_id": "user123"},
                },
            )
            assert response.status_code == 204

            # Verify the entry passed to push
            call_args = mock.call_args[0][0]
            assert call_args.context == {"error_code": "E001", "user_id": "user123"}

    def test_ingest_log_loki_failure(self, client: TestClient):
        """Test handling Loki push failure."""
        with patch("app.loki_client.loki_client.push", new_callable=AsyncMock) as mock:
            mock.return_value = False
            response = client.post(
                "/api/v0/logs",
                json={
                    "service": "test-service",
                    "level": "INFO",
                    "message": "Test",
                },
            )
            assert response.status_code == 502
            assert "Failed to push log to Loki" in response.json()["detail"]

    def test_ingest_log_invalid_level(self, client: TestClient):
        """Test rejecting invalid log level."""
        response = client.post(
            "/api/v0/logs",
            json={
                "service": "test-service",
                "level": "INVALID",
                "message": "Test",
            },
        )
        assert response.status_code == 422

    def test_ingest_log_missing_service(self, client: TestClient):
        """Test rejecting missing service."""
        response = client.post(
            "/api/v0/logs",
            json={
                "level": "INFO",
                "message": "Test",
            },
        )
        assert response.status_code == 422


class TestIngestBatch:
    """Tests for batch log ingestion."""

    def test_ingest_batch_success(self, client: TestClient):
        """Test batch ingestion."""
        with patch("app.loki_client.loki_client.push_batch", new_callable=AsyncMock) as mock:
            mock.return_value = True
            response = client.post(
                "/api/v0/logs/batch",
                json={
                    "logs": [
                        {"service": "svc1", "level": "INFO", "message": "Msg 1"},
                        {"service": "svc2", "level": "ERROR", "message": "Msg 2"},
                    ]
                },
            )
            assert response.status_code == 204
            mock.assert_called_once()
            assert len(mock.call_args[0][0]) == 2

    def test_ingest_batch_empty(self, client: TestClient):
        """Test empty batch returns success without calling Loki."""
        with patch("app.loki_client.loki_client.push_batch", new_callable=AsyncMock) as mock:
            response = client.post(
                "/api/v0/logs/batch",
                json={"logs": []},
            )
            assert response.status_code == 204
            mock.assert_not_called()

    def test_ingest_batch_loki_failure(self, client: TestClient):
        """Test handling Loki batch push failure."""
        with patch("app.loki_client.loki_client.push_batch", new_callable=AsyncMock) as mock:
            mock.return_value = False
            response = client.post(
                "/api/v0/logs/batch",
                json={
                    "logs": [
                        {"service": "test", "level": "INFO", "message": "Test"},
                    ]
                },
            )
            assert response.status_code == 502

    def test_ingest_batch_invalid_entry(self, client: TestClient):
        """Test batch with invalid entry."""
        response = client.post(
            "/api/v0/logs/batch",
            json={
                "logs": [
                    {"service": "test", "level": "INVALID", "message": "Test"},
                ]
            },
        )
        assert response.status_code == 422


class TestQueryLogs:
    """Tests for log query endpoint."""

    def test_query_logs_default(self, client: TestClient):
        """Test querying logs with defaults."""
        with patch("app.loki_client.loki_client.query", new_callable=AsyncMock) as mock:
            mock.return_value = [
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "test",
                    "level": "INFO",
                    "message": "Test",
                    "context": None,
                }
            ]
            response = client.get("/api/v0/logs")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["service"] == "test"

    def test_query_logs_with_filters(self, client: TestClient):
        """Test querying logs with filters."""
        with patch("app.loki_client.loki_client.query", new_callable=AsyncMock) as mock:
            mock.return_value = []
            response = client.get(
                "/api/v0/logs",
                params={
                    "service": "my-service",
                    "level": "ERROR",
                    "search": "exception",
                    "limit": 50,
                },
            )
            assert response.status_code == 200
            mock.assert_called_once()
            call_kwargs = mock.call_args[1]
            assert call_kwargs["service"] == "my-service"
            assert call_kwargs["level"] == "ERROR"
            assert call_kwargs["search"] == "exception"
            assert call_kwargs["limit"] == 50

    def test_query_logs_with_time_range(self, client: TestClient):
        """Test querying logs with time range."""
        with patch("app.loki_client.loki_client.query", new_callable=AsyncMock) as mock:
            mock.return_value = []
            response = client.get(
                "/api/v0/logs",
                params={
                    "since": "2024-01-01T00:00:00",
                    "until": "2024-01-02T00:00:00",
                },
            )
            assert response.status_code == 200
            call_kwargs = mock.call_args[1]
            assert call_kwargs["since"] is not None
            assert call_kwargs["until"] is not None

    def test_query_logs_limit_max(self, client: TestClient):
        """Test query respects maximum limit."""
        with patch("app.loki_client.loki_client.query", new_callable=AsyncMock) as mock:
            mock.return_value = []
            response = client.get("/api/v0/logs", params={"limit": 1001})
            assert response.status_code == 422

    def test_query_logs_limit_min(self, client: TestClient):
        """Test query respects minimum limit."""
        with patch("app.loki_client.loki_client.query", new_callable=AsyncMock) as mock:
            mock.return_value = []
            response = client.get("/api/v0/logs", params={"limit": 0})
            assert response.status_code == 422


class TestListServices:
    """Tests for list services endpoint."""

    def test_list_services_success(self, client: TestClient):
        """Test listing services."""
        with patch("app.loki_client.loki_client.query", new_callable=AsyncMock) as mock:
            mock.return_value = [
                {"service": "svc1", "level": "INFO", "message": "a", "timestamp": "", "context": None},
                {"service": "svc2", "level": "INFO", "message": "b", "timestamp": "", "context": None},
                {"service": "svc1", "level": "ERROR", "message": "c", "timestamp": "", "context": None},
            ]
            response = client.get("/api/v0/services")
            assert response.status_code == 200
            services = response.json()
            assert sorted(services) == ["svc1", "svc2"]

    def test_list_services_empty(self, client: TestClient):
        """Test listing services when none exist."""
        with patch("app.loki_client.loki_client.query", new_callable=AsyncMock) as mock:
            mock.return_value = []
            response = client.get("/api/v0/services")
            assert response.status_code == 200
            assert response.json() == []
