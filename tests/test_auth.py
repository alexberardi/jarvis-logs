"""Tests for authentication middleware."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pytest_httpx import HTTPXMock

from app.auth import (
    NodeValidationResult,
    require_app_auth,
    require_node_auth,
    validate_node_credentials,
    _node_validation_cache,
)


@pytest.fixture
def mock_request():
    """Create a mock request object."""
    request = MagicMock()
    request.url.path = "/api/v0/logs"
    request.state = MagicMock()
    return request


@pytest.fixture
def mock_health_request():
    """Create a mock request for health endpoint."""
    request = MagicMock()
    request.url.path = "/health"
    request.state = MagicMock()
    return request


class TestRequireAppAuth:
    """Tests for require_app_auth dependency."""

    @pytest.mark.asyncio
    async def test_health_endpoint_skips_auth(self, mock_health_request):
        """Test that /health endpoint skips authentication."""
        # Should not raise even without credentials
        result = await require_app_auth(
            mock_health_request,
            x_jarvis_app_id=None,
            x_jarvis_app_key=None,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_ping_endpoint_skips_auth(self):
        """Test that /ping endpoint skips authentication."""
        request = MagicMock()
        request.url.path = "/ping"
        request.state = MagicMock()

        result = await require_app_auth(
            request,
            x_jarvis_app_id=None,
            x_jarvis_app_key=None,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_app_id(self, mock_request):
        """Test that missing app ID returns 401."""
        with pytest.raises(HTTPException) as exc_info:
            await require_app_auth(
                mock_request,
                x_jarvis_app_id=None,
                x_jarvis_app_key="some-key",
            )
        assert exc_info.value.status_code == 401
        assert "Missing app credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_app_key(self, mock_request):
        """Test that missing app key returns 401."""
        with pytest.raises(HTTPException) as exc_info:
            await require_app_auth(
                mock_request,
                x_jarvis_app_id="some-app",
                x_jarvis_app_key=None,
            )
        assert exc_info.value.status_code == 401
        assert "Missing app credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_both_credentials(self, mock_request):
        """Test that missing both credentials returns 401."""
        with pytest.raises(HTTPException) as exc_info:
            await require_app_auth(
                mock_request,
                x_jarvis_app_id=None,
                x_jarvis_app_key=None,
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_auth_base_url(self, mock_request):
        """Test that missing JARVIS_AUTH_BASE_URL returns 500."""
        with patch.dict(os.environ, {"JARVIS_AUTH_BASE_URL": ""}, clear=False):
            # Clear the env var for this test
            old_val = os.environ.pop("JARVIS_AUTH_BASE_URL", None)
            try:
                with pytest.raises(HTTPException) as exc_info:
                    await require_app_auth(
                        mock_request,
                        x_jarvis_app_id="test-app",
                        x_jarvis_app_key="test-key",
                    )
                assert exc_info.value.status_code == 500
                assert "JARVIS_AUTH_BASE_URL not configured" in exc_info.value.detail
            finally:
                if old_val:
                    os.environ["JARVIS_AUTH_BASE_URL"] = old_val

    @pytest.mark.asyncio
    async def test_auth_service_success(self, mock_request, httpx_mock: HTTPXMock):
        """Test successful authentication."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/app-ping",
            method="GET",
            status_code=200,
            json={"app_id": "test-app", "name": "Test App"},
        )

        result = await require_app_auth(
            mock_request,
            x_jarvis_app_id="test-app",
            x_jarvis_app_key="valid-key",
        )

        assert result is None
        assert mock_request.state.calling_app_id == "test-app"

    @pytest.mark.asyncio
    async def test_auth_service_invalid_credentials(self, mock_request, httpx_mock: HTTPXMock):
        """Test authentication with invalid credentials."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/app-ping",
            method="GET",
            status_code=401,
            json={"detail": "Invalid credentials"},
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_app_auth(
                mock_request,
                x_jarvis_app_id="test-app",
                x_jarvis_app_key="invalid-key",
            )
        assert exc_info.value.status_code == 401
        assert "Invalid app credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_auth_service_other_error(self, mock_request, httpx_mock: HTTPXMock):
        """Test handling non-401 errors from auth service."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/app-ping",
            method="GET",
            status_code=500,
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_app_auth(
                mock_request,
                x_jarvis_app_id="test-app",
                x_jarvis_app_key="test-key",
            )
        assert exc_info.value.status_code == 500
        assert "App auth failed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_auth_service_unavailable(self, mock_request, httpx_mock: HTTPXMock):
        """Test handling auth service being unavailable."""
        import httpx

        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"

        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        with pytest.raises(HTTPException) as exc_info:
            await require_app_auth(
                mock_request,
                x_jarvis_app_id="test-app",
                x_jarvis_app_key="test-key",
            )
        assert exc_info.value.status_code == 502
        assert "Auth service unavailable" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_auth_service_timeout(self, mock_request, httpx_mock: HTTPXMock):
        """Test handling auth service timeout."""
        import httpx

        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"

        httpx_mock.add_exception(httpx.ReadTimeout("Timeout"))

        with pytest.raises(HTTPException) as exc_info:
            await require_app_auth(
                mock_request,
                x_jarvis_app_id="test-app",
                x_jarvis_app_key="test-key",
            )
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_auth_headers_forwarded(self, mock_request, httpx_mock: HTTPXMock):
        """Test that credentials are forwarded to auth service."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/app-ping",
            method="GET",
            status_code=200,
            json={"app_id": "my-app"},
        )

        await require_app_auth(
            mock_request,
            x_jarvis_app_id="my-app",
            x_jarvis_app_key="my-secret-key",
        )

        request = httpx_mock.get_request()
        assert request.headers["X-Jarvis-App-Id"] == "my-app"
        assert request.headers["X-Jarvis-App-Key"] == "my-secret-key"

    @pytest.mark.asyncio
    async def test_auth_response_without_app_id(self, mock_request, httpx_mock: HTTPXMock):
        """Test handling auth response without app_id in body."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/app-ping",
            method="GET",
            status_code=200,
            json={},  # No app_id in response
        )

        await require_app_auth(
            mock_request,
            x_jarvis_app_id="fallback-app",
            x_jarvis_app_key="key",
        )

        # Should fall back to header value
        assert mock_request.state.calling_app_id == "fallback-app"

    @pytest.mark.asyncio
    async def test_auth_response_invalid_json(self, mock_request, httpx_mock: HTTPXMock):
        """Test handling auth response with invalid JSON."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/app-ping",
            method="GET",
            status_code=200,
            text="not json",
        )

        await require_app_auth(
            mock_request,
            x_jarvis_app_id="fallback-app",
            x_jarvis_app_key="key",
        )

        # Should fall back to header value
        assert mock_request.state.calling_app_id == "fallback-app"


# ============================================================
# Node Authentication Tests
# ============================================================


@pytest.fixture
def mock_node_request():
    """Create a mock request object for node auth."""
    request = MagicMock()
    request.url.path = "/api/v0/node/logs"
    request.state = MagicMock()
    return request


@pytest.fixture(autouse=True)
def clear_validation_cache():
    """Clear the node validation cache before each test."""
    _node_validation_cache.clear()
    yield
    _node_validation_cache.clear()


class TestValidateNodeCredentials:
    """Tests for validate_node_credentials function."""

    @pytest.mark.asyncio
    async def test_missing_auth_base_url(self):
        """Test that missing JARVIS_AUTH_BASE_URL returns invalid result."""
        old_val = os.environ.pop("JARVIS_AUTH_BASE_URL", None)
        try:
            result = await validate_node_credentials("node-1", "key-1", "jarvis-logs")
            assert result.valid is False
            assert "JARVIS_AUTH_BASE_URL not configured" in result.reason
        finally:
            if old_val:
                os.environ["JARVIS_AUTH_BASE_URL"] = old_val

    @pytest.mark.asyncio
    async def test_missing_app_key(self):
        """Test that missing JARVIS_APP_KEY returns invalid result."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        old_key = os.environ.pop("JARVIS_APP_KEY", None)
        try:
            result = await validate_node_credentials("node-1", "key-1", "jarvis-logs")
            assert result.valid is False
            assert "JARVIS_APP_KEY not configured" in result.reason
        finally:
            if old_key:
                os.environ["JARVIS_APP_KEY"] = old_key

    @pytest.mark.asyncio
    async def test_successful_validation(self, httpx_mock: HTTPXMock):
        """Test successful node credential validation."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_KEY"] = "test-app-key"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/validate-node",
            method="POST",
            status_code=200,
            json={"valid": True, "node_id": "test-node", "user_id": 1},
        )

        result = await validate_node_credentials("test-node", "node-key", "jarvis-logs")
        assert result.valid is True
        assert result.node_id == "test-node"
        assert result.user_id == 1

    @pytest.mark.asyncio
    async def test_invalid_credentials(self, httpx_mock: HTTPXMock):
        """Test invalid node credentials."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_KEY"] = "test-app-key"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/validate-node",
            method="POST",
            status_code=200,
            json={"valid": False, "reason": "Invalid node credentials"},
        )

        result = await validate_node_credentials("test-node", "wrong-key", "jarvis-logs")
        assert result.valid is False
        assert "Invalid node credentials" in result.reason

    @pytest.mark.asyncio
    async def test_no_service_access(self, httpx_mock: HTTPXMock):
        """Test node without service access."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_KEY"] = "test-app-key"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/validate-node",
            method="POST",
            status_code=200,
            json={"valid": False, "reason": "Node is not authorized to access service 'jarvis-logs'"},
        )

        result = await validate_node_credentials("test-node", "valid-key", "jarvis-logs")
        assert result.valid is False
        assert "not authorized" in result.reason

    @pytest.mark.asyncio
    async def test_auth_service_unavailable(self, httpx_mock: HTTPXMock):
        """Test handling auth service being unavailable."""
        import httpx

        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_KEY"] = "test-app-key"

        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        result = await validate_node_credentials("test-node", "node-key", "jarvis-logs")
        assert result.valid is False
        assert "Auth service unavailable" in result.reason

    @pytest.mark.asyncio
    async def test_auth_service_error(self, httpx_mock: HTTPXMock):
        """Test handling auth service error response."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_KEY"] = "test-app-key"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/validate-node",
            method="POST",
            status_code=500,
        )

        result = await validate_node_credentials("test-node", "node-key", "jarvis-logs")
        assert result.valid is False
        assert "Auth service error" in result.reason

    @pytest.mark.asyncio
    async def test_caching(self, httpx_mock: HTTPXMock):
        """Test that validation results are cached."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_KEY"] = "test-app-key"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/validate-node",
            method="POST",
            status_code=200,
            json={"valid": True, "node_id": "cached-node", "user_id": 2},
        )

        # First call
        result1 = await validate_node_credentials("cached-node", "node-key", "jarvis-logs")
        assert result1.valid is True

        # Second call should use cache (no new HTTP request)
        result2 = await validate_node_credentials("cached-node", "node-key", "jarvis-logs")
        assert result2.valid is True
        assert result2.node_id == "cached-node"

        # Verify only one request was made
        requests = httpx_mock.get_requests()
        assert len(requests) == 1


class TestRequireNodeAuth:
    """Tests for require_node_auth dependency."""

    @pytest.mark.asyncio
    async def test_missing_node_id(self, mock_node_request):
        """Test that missing node ID returns 401."""
        with pytest.raises(HTTPException) as exc_info:
            await require_node_auth(
                mock_node_request,
                x_node_id=None,
                x_node_key="some-key",
            )
        assert exc_info.value.status_code == 401
        assert "Missing node credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_node_key(self, mock_node_request):
        """Test that missing node key returns 401."""
        with pytest.raises(HTTPException) as exc_info:
            await require_node_auth(
                mock_node_request,
                x_node_id="some-node",
                x_node_key=None,
            )
        assert exc_info.value.status_code == 401
        assert "Missing node credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_successful_auth(self, mock_node_request, httpx_mock: HTTPXMock):
        """Test successful node authentication."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_KEY"] = "test-app-key"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/validate-node",
            method="POST",
            status_code=200,
            json={"valid": True, "node_id": "auth-node", "user_id": 3},
        )

        result = await require_node_auth(
            mock_node_request,
            x_node_id="auth-node",
            x_node_key="valid-key",
        )

        assert result.valid is True
        assert result.node_id == "auth-node"
        assert result.user_id == 3
        assert mock_node_request.state.node_id == "auth-node"
        assert mock_node_request.state.user_id == 3

    @pytest.mark.asyncio
    async def test_invalid_credentials_raises_403(self, mock_node_request, httpx_mock: HTTPXMock):
        """Test that invalid credentials raise 403."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_KEY"] = "test-app-key"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/validate-node",
            method="POST",
            status_code=200,
            json={"valid": False, "reason": "Invalid node credentials"},
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_node_auth(
                mock_node_request,
                x_node_id="bad-node",
                x_node_key="bad-key",
            )
        assert exc_info.value.status_code == 403
        assert "Invalid node credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_headers_forwarded(self, mock_node_request, httpx_mock: HTTPXMock):
        """Test that app credentials are forwarded to auth service."""
        os.environ["JARVIS_AUTH_BASE_URL"] = "http://test-auth:8007"
        os.environ["JARVIS_APP_ID"] = "jarvis-logs"
        os.environ["JARVIS_APP_KEY"] = "logs-secret-key"

        httpx_mock.add_response(
            url="http://test-auth:8007/internal/validate-node",
            method="POST",
            status_code=200,
            json={"valid": True, "node_id": "my-node", "user_id": 1},
        )

        await require_node_auth(
            mock_node_request,
            x_node_id="my-node",
            x_node_key="my-node-key",
        )

        request = httpx_mock.get_request()
        assert request.headers["X-Jarvis-App-Id"] == "jarvis-logs"
        assert request.headers["X-Jarvis-App-Key"] == "logs-secret-key"

        # Verify request body
        import json
        body = json.loads(request.content)
        assert body["node_id"] == "my-node"
        assert body["node_key"] == "my-node-key"
        assert body["service_id"] == "jarvis-logs"
