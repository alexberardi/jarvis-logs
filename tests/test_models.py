"""Tests for Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models import LogEntry, LogBatch, LogQuery


class TestLogEntry:
    """Tests for LogEntry model."""

    def test_valid_entry_full(self, sample_log_entry_data: dict):
        """Test creating a log entry with all fields."""
        entry = LogEntry(**sample_log_entry_data)
        assert entry.service == "test-service"
        assert entry.level == "INFO"
        assert entry.message == "Test log message"
        assert entry.context == {"request_id": "abc123"}
        assert entry.timestamp is not None

    def test_valid_entry_minimal(self, sample_log_entry_minimal: dict):
        """Test creating a log entry with minimal fields."""
        entry = LogEntry(**sample_log_entry_minimal)
        assert entry.service == "test-service"
        assert entry.level == "DEBUG"
        assert entry.message == "Minimal log"
        assert entry.context is None

    def test_valid_levels(self):
        """Test all valid log levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in valid_levels:
            entry = LogEntry(service="test", level=level, message="test")
            assert entry.level == level

    def test_invalid_level(self):
        """Test that invalid log levels are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LogEntry(service="test", level="INVALID", message="test")
        assert "level" in str(exc_info.value)

    def test_invalid_level_lowercase(self):
        """Test that lowercase levels are rejected."""
        with pytest.raises(ValidationError):
            LogEntry(service="test", level="info", message="test")

    def test_empty_service_rejected(self):
        """Test that empty service name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LogEntry(service="", level="INFO", message="test")
        assert "service" in str(exc_info.value)

    def test_service_max_length(self):
        """Test that overly long service names are rejected."""
        with pytest.raises(ValidationError):
            LogEntry(service="x" * 65, level="INFO", message="test")

    def test_service_max_length_valid(self):
        """Test that service names at max length are accepted."""
        entry = LogEntry(service="x" * 64, level="INFO", message="test")
        assert len(entry.service) == 64

    def test_empty_message_allowed(self):
        """Test that empty messages are allowed."""
        entry = LogEntry(service="test", level="INFO", message="")
        assert entry.message == ""

    def test_custom_timestamp(self):
        """Test providing a custom timestamp."""
        custom_time = datetime(2024, 1, 15, 12, 30, 0)
        entry = LogEntry(
            service="test",
            level="INFO",
            message="test",
            timestamp=custom_time,
        )
        assert entry.timestamp == custom_time

    def test_context_complex(self):
        """Test complex context structures."""
        entry = LogEntry(
            service="test",
            level="INFO",
            message="test",
            context={
                "user_id": "user123",
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "number": 42.5,
            },
        )
        assert entry.context["user_id"] == "user123"
        assert entry.context["nested"]["key"] == "value"

    def test_to_loki_format_simple(self):
        """Test converting to Loki format without context."""
        entry = LogEntry(
            service="test",
            level="INFO",
            message="Test message",
            timestamp=datetime(2024, 1, 15, 12, 0, 0),
        )
        ts_ns, log_line = entry.to_loki_format()
        assert log_line == "Test message"
        assert ts_ns == str(int(datetime(2024, 1, 15, 12, 0, 0).timestamp() * 1e9))

    def test_to_loki_format_with_context(self):
        """Test converting to Loki format with context."""
        entry = LogEntry(
            service="test",
            level="INFO",
            message="Test message",
            context={"key": "value"},
        )
        ts_ns, log_line = entry.to_loki_format()
        assert "Test message" in log_line
        assert '{"key": "value"}' in log_line
        assert " | " in log_line


class TestLogBatch:
    """Tests for LogBatch model."""

    def test_valid_batch(self, sample_batch_data: dict):
        """Test creating a valid batch."""
        batch = LogBatch(**sample_batch_data)
        assert len(batch.logs) == 3
        assert batch.logs[0].service == "svc1"
        assert batch.logs[1].level == "ERROR"

    def test_empty_batch(self):
        """Test that empty batches are allowed."""
        batch = LogBatch(logs=[])
        assert len(batch.logs) == 0

    def test_batch_validates_entries(self):
        """Test that batch validates individual entries."""
        with pytest.raises(ValidationError):
            LogBatch(
                logs=[
                    {"service": "test", "level": "INVALID", "message": "test"},
                ]
            )


class TestLogQuery:
    """Tests for LogQuery model."""

    def test_default_values(self):
        """Test default query values."""
        query = LogQuery()
        assert query.service is None
        assert query.level is None
        assert query.search is None
        assert query.since is None
        assert query.until is None
        assert query.limit == 100

    def test_custom_values(self):
        """Test query with custom values."""
        since = datetime(2024, 1, 1)
        until = datetime(2024, 1, 31)
        query = LogQuery(
            service="test",
            level="ERROR",
            search="exception",
            since=since,
            until=until,
            limit=50,
        )
        assert query.service == "test"
        assert query.level == "ERROR"
        assert query.search == "exception"
        assert query.since == since
        assert query.until == until
        assert query.limit == 50

    def test_limit_min(self):
        """Test minimum limit constraint."""
        with pytest.raises(ValidationError):
            LogQuery(limit=0)

    def test_limit_max(self):
        """Test maximum limit constraint."""
        with pytest.raises(ValidationError):
            LogQuery(limit=1001)

    def test_limit_boundaries(self):
        """Test limit at boundaries."""
        query_min = LogQuery(limit=1)
        assert query_min.limit == 1

        query_max = LogQuery(limit=1000)
        assert query_max.limit == 1000
