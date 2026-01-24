"""Tests for LokiClient."""

import json
import re
from datetime import datetime, timedelta

import pytest
from pytest_httpx import HTTPXMock

from app.loki_client import LokiClient
from app.models import LogEntry


@pytest.fixture
def sample_entry() -> LogEntry:
    """Create a sample log entry."""
    return LogEntry(
        service="test-service",
        level="INFO",
        message="Test message",
        timestamp=datetime(2024, 1, 15, 12, 0, 0),
    )


class TestLokiClientPush:
    """Tests for LokiClient.push and push_batch."""

    @pytest.mark.asyncio
    async def test_push_single_entry_success(
        self, sample_entry: LogEntry, httpx_mock: HTTPXMock
    ):
        """Test pushing a single log entry successfully."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url="http://test-loki:3100/loki/api/v1/push",
            method="POST",
            status_code=204,
        )

        result = await client.push(sample_entry)
        assert result is True
        await client.close()

    @pytest.mark.asyncio
    async def test_push_single_entry_failure(
        self, sample_entry: LogEntry, httpx_mock: HTTPXMock
    ):
        """Test pushing when Loki returns an error."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url="http://test-loki:3100/loki/api/v1/push",
            method="POST",
            status_code=500,
        )

        result = await client.push(sample_entry)
        assert result is False
        await client.close()

    @pytest.mark.asyncio
    async def test_push_batch_success(self, httpx_mock: HTTPXMock):
        """Test pushing a batch of entries."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url="http://test-loki:3100/loki/api/v1/push",
            method="POST",
            status_code=204,
        )

        entries = [
            LogEntry(service="svc1", level="INFO", message="Msg 1"),
            LogEntry(service="svc1", level="ERROR", message="Msg 2"),
            LogEntry(service="svc2", level="WARNING", message="Msg 3"),
        ]

        result = await client.push_batch(entries)
        assert result is True

        # Verify the request payload structure
        request = httpx_mock.get_request()
        payload = json.loads(request.content)
        assert "streams" in payload
        assert len(payload["streams"]) >= 1
        await client.close()

    @pytest.mark.asyncio
    async def test_push_batch_groups_by_service_level(self, httpx_mock: HTTPXMock):
        """Test that batch push groups entries by service and level."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url="http://test-loki:3100/loki/api/v1/push",
            method="POST",
            status_code=204,
        )

        entries = [
            LogEntry(service="svc1", level="INFO", message="Msg 1"),
            LogEntry(service="svc1", level="INFO", message="Msg 2"),
            LogEntry(service="svc1", level="ERROR", message="Msg 3"),
        ]

        await client.push_batch(entries)

        request = httpx_mock.get_request()
        payload = json.loads(request.content)

        # Should have 2 streams: (svc1, INFO) and (svc1, ERROR)
        assert len(payload["streams"]) == 2

        # Find the INFO stream and verify it has 2 values
        info_stream = next(
            s for s in payload["streams"]
            if s["stream"]["service"] == "svc1" and s["stream"]["level"] == "INFO"
        )
        assert len(info_stream["values"]) == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_push_batch_empty(self, httpx_mock: HTTPXMock):
        """Test pushing an empty batch returns True without making request."""
        client = LokiClient(base_url="http://test-loki:3100")
        result = await client.push_batch([])
        assert result is True
        assert len(httpx_mock.get_requests()) == 0
        await client.close()

    @pytest.mark.asyncio
    async def test_push_network_error(
        self, sample_entry: LogEntry, httpx_mock: HTTPXMock
    ):
        """Test handling network errors during push."""
        import httpx
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        result = await client.push(sample_entry)
        assert result is False
        await client.close()


class TestLokiClientQuery:
    """Tests for LokiClient.query."""

    @pytest.mark.asyncio
    async def test_query_basic(self, httpx_mock: HTTPXMock):
        """Test basic log query."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url=re.compile(r"http://test-loki:3100/loki/api/v1/query_range.*"),
            method="GET",
            json={
                "data": {
                    "result": [
                        {
                            "stream": {"service": "test", "level": "INFO"},
                            "values": [
                                ["1705320000000000000", "Test message"],
                            ],
                        }
                    ]
                }
            },
        )

        results = await client.query()
        assert len(results) == 1
        assert results[0]["service"] == "test"
        assert results[0]["level"] == "INFO"
        assert results[0]["message"] == "Test message"
        await client.close()

    @pytest.mark.asyncio
    async def test_query_with_service_filter(self, httpx_mock: HTTPXMock):
        """Test query with service filter."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url=re.compile(r"http://test-loki:3100/loki/api/v1/query_range.*"),
            method="GET",
            json={"data": {"result": []}},
        )

        await client.query(service="my-service")

        request = httpx_mock.get_request()
        assert 'service="my-service"' in request.url.params["query"]
        await client.close()

    @pytest.mark.asyncio
    async def test_query_with_level_filter(self, httpx_mock: HTTPXMock):
        """Test query with level filter."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url=re.compile(r"http://test-loki:3100/loki/api/v1/query_range.*"),
            method="GET",
            json={"data": {"result": []}},
        )

        await client.query(level="ERROR")

        request = httpx_mock.get_request()
        assert 'level="ERROR"' in request.url.params["query"]
        await client.close()

    @pytest.mark.asyncio
    async def test_query_with_search(self, httpx_mock: HTTPXMock):
        """Test query with search term."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url=re.compile(r"http://test-loki:3100/loki/api/v1/query_range.*"),
            method="GET",
            json={"data": {"result": []}},
        )

        await client.query(search="exception")

        request = httpx_mock.get_request()
        assert 'exception' in request.url.params["query"]
        await client.close()

    @pytest.mark.asyncio
    async def test_query_with_time_range(self, httpx_mock: HTTPXMock):
        """Test query with time range."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url=re.compile(r"http://test-loki:3100/loki/api/v1/query_range.*"),
            method="GET",
            json={"data": {"result": []}},
        )

        since = datetime(2024, 1, 1, 0, 0, 0)
        until = datetime(2024, 1, 2, 0, 0, 0)
        await client.query(since=since, until=until)

        request = httpx_mock.get_request()
        assert "start" in request.url.params
        assert "end" in request.url.params
        await client.close()

    @pytest.mark.asyncio
    async def test_query_parses_context(self, httpx_mock: HTTPXMock):
        """Test that query parses context from log message."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url=re.compile(r"http://test-loki:3100/loki/api/v1/query_range.*"),
            method="GET",
            json={
                "data": {
                    "result": [
                        {
                            "stream": {"service": "test", "level": "INFO"},
                            "values": [
                                ["1705320000000000000", 'Test message | {"key": "value"}'],
                            ],
                        }
                    ]
                }
            },
        )

        results = await client.query()
        assert results[0]["message"] == "Test message"
        assert results[0]["context"] == {"key": "value"}
        await client.close()

    @pytest.mark.asyncio
    async def test_query_handles_invalid_context_json(self, httpx_mock: HTTPXMock):
        """Test that invalid context JSON is handled gracefully."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url=re.compile(r"http://test-loki:3100/loki/api/v1/query_range.*"),
            method="GET",
            json={
                "data": {
                    "result": [
                        {
                            "stream": {"service": "test", "level": "INFO"},
                            "values": [
                                ["1705320000000000000", "Test | not-json"],
                            ],
                        }
                    ]
                }
            },
        )

        results = await client.query()
        assert results[0]["message"] == "Test"
        assert results[0]["context"] is None
        await client.close()

    @pytest.mark.asyncio
    async def test_query_error_returns_empty(self, httpx_mock: HTTPXMock):
        """Test that query errors return empty list."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url=re.compile(r"http://test-loki:3100/loki/api/v1/query_range.*"),
            method="GET",
            status_code=500,
        )

        results = await client.query()
        assert results == []
        await client.close()

    @pytest.mark.asyncio
    async def test_query_network_error(self, httpx_mock: HTTPXMock):
        """Test handling network errors during query."""
        import httpx
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        results = await client.query()
        assert results == []
        await client.close()


class TestLokiClientHealth:
    """Tests for LokiClient.health_check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, httpx_mock: HTTPXMock):
        """Test successful health check."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url="http://test-loki:3100/ready",
            status_code=200,
            text="ready",
        )

        result = await client.health_check()
        assert result is True
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, httpx_mock: HTTPXMock):
        """Test failed health check."""
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_response(
            url="http://test-loki:3100/ready",
            status_code=503,
        )

        result = await client.health_check()
        assert result is False
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_network_error(self, httpx_mock: HTTPXMock):
        """Test health check with network error."""
        import httpx
        client = LokiClient(base_url="http://test-loki:3100")
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        result = await client.health_check()
        assert result is False
        await client.close()


class TestLokiClientLifecycle:
    """Tests for LokiClient lifecycle management."""

    @pytest.mark.asyncio
    async def test_client_reuse(self, httpx_mock: HTTPXMock):
        """Test that the same client is reused."""
        client = LokiClient(base_url="http://test-loki:3100")

        # Need two responses since we make two requests
        httpx_mock.add_response(url="http://test-loki:3100/ready", status_code=200)
        httpx_mock.add_response(url="http://test-loki:3100/ready", status_code=200)

        await client.health_check()
        client1 = client._client

        await client.health_check()
        client2 = client._client

        assert client1 is client2
        await client.close()

    @pytest.mark.asyncio
    async def test_close_clears_client(self, httpx_mock: HTTPXMock):
        """Test that close() clears the client."""
        client = LokiClient(base_url="http://test-loki:3100")

        httpx_mock.add_response(url="http://test-loki:3100/ready", status_code=200)

        await client.health_check()
        assert client._client is not None

        await client.close()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        """Test that close() works even if client was never created."""
        client = LokiClient(base_url="http://test-loki:3100")
        await client.close()  # Should not raise
