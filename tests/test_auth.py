"""Tests for authentication middleware."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pytest_httpx import HTTPXMock

from app.auth import require_app_auth


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
