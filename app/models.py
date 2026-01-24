from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """Log entry received from microservices."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    service: str = Field(..., min_length=1, max_length=64)
    level: str = Field(..., pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    message: str
    context: dict[str, Any] | None = None

    def to_loki_format(self) -> tuple[str, str]:
        """Convert to Loki push format: (timestamp_ns, log_line)."""
        ts_ns = str(int(self.timestamp.timestamp() * 1e9))
        log_line = self.message
        if self.context:
            import json
            log_line = f"{self.message} | {json.dumps(self.context)}"
        return ts_ns, log_line


class LogBatch(BaseModel):
    """Batch of log entries for bulk ingestion."""

    logs: list[LogEntry]


class LogQuery(BaseModel):
    """Query parameters for log retrieval."""

    service: str | None = None
    level: str | None = None
    search: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)
