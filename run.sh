#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Starting jarvis-logs stack (jarvis-logs + Loki + Grafana)..."
docker compose up --build -d

echo ""
echo "Services started:"
echo "  - jarvis-logs: http://localhost:${LOG_SERVER_PORT:-8006}"
echo "  - Loki:        http://localhost:3100"
echo "  - Grafana:     http://localhost:3000 (admin/jarvis)"
echo ""
echo "To view logs: docker compose logs -f"
echo "To stop:      docker compose down"
