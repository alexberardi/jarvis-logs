import json
import os
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.models import LogEntry


class LokiClient:
    """Client for pushing logs to and querying from Loki."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv("LOKI_URL", "http://loki:3100")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def push(self, entry: LogEntry) -> bool:
        """Push a single log entry to Loki."""
        return await self.push_batch([entry])

    async def push_batch(self, entries: list[LogEntry]) -> bool:
        """Push multiple log entries to Loki in a single request."""
        if not entries:
            return True

        # Group entries by service and level for efficient Loki streams
        streams: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for entry in entries:
            key = (entry.service, entry.level)
            if key not in streams:
                streams[key] = []
            streams[key].append(entry.to_loki_format())

        # Build Loki push payload
        payload = {
            "streams": [
                {
                    "stream": {"service": service, "level": level},
                    "values": values,
                }
                for (service, level), values in streams.items()
            ]
        }

        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.base_url}/loki/api/v1/push",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            return response.status_code == 204
        except httpx.RequestError:
            return False

    async def query(
        self,
        service: str | None = None,
        level: str | None = None,
        search: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query logs from Loki using LogQL."""
        # Build LogQL query
        label_matchers = []
        if service:
            label_matchers.append(f'service="{service}"')
        if level:
            label_matchers.append(f'level="{level}"')

        if label_matchers:
            query = "{" + ",".join(label_matchers) + "}"
        else:
            query = '{service=~".+"}'  # Match all services

        if search:
            query += f' |~ "{search}"'

        # Time range
        end_time = until or datetime.utcnow()
        start_time = since or (end_time - timedelta(hours=1))

        params = {
            "query": query,
            "start": str(int(start_time.timestamp() * 1e9)),
            "end": str(int(end_time.timestamp() * 1e9)),
            "limit": limit,
            "direction": "backward",  # Most recent first
        }

        client = await self._get_client()
        try:
            response = await client.get(
                f"{self.base_url}/loki/api/v1/query_range",
                params=params,
            )
            if response.status_code != 200:
                return []

            data = response.json()
            results = []

            for stream in data.get("data", {}).get("result", []):
                labels = stream.get("stream", {})
                for value in stream.get("values", []):
                    ts_ns, message = value
                    # Parse context from message if present
                    context = None
                    if " | " in message:
                        msg_parts = message.rsplit(" | ", 1)
                        message = msg_parts[0]
                        try:
                            context = json.loads(msg_parts[1])
                        except json.JSONDecodeError:
                            pass

                    results.append({
                        "timestamp": datetime.fromtimestamp(int(ts_ns) / 1e9).isoformat(),
                        "service": labels.get("service"),
                        "level": labels.get("level"),
                        "message": message,
                        "context": context,
                    })

            return results
        except httpx.RequestError:
            return []

    async def health_check(self) -> bool:
        """Check if Loki is reachable."""
        client = await self._get_client()
        try:
            response = await client.get(f"{self.base_url}/ready")
            return response.status_code == 200
        except httpx.RequestError:
            return False


# Global client instance
loki_client = LokiClient()
