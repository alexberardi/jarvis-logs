#!/bin/bash
# Production server
# Usage: ./run-prod.sh [--build]

set -e
cd "$(dirname "$0")"

BUILD_FLAGS=""
if [[ "$1" == "--build" ]]; then
    BUILD_FLAGS="--build"
fi

echo "Starting jarvis-logs stack (jarvis-logs + Loki + Grafana)..."
docker compose -f docker-compose.prod.yaml up -d $BUILD_FLAGS

echo ""
echo "Services started:"
echo "  - jarvis-logs: http://localhost:${LOG_SERVER_PORT:-8006}"
echo "  - Loki:        http://localhost:3100"
echo "  - Grafana:     http://localhost:3000 (admin/jarvis)"
echo ""
echo "Logs: docker compose -f docker-compose.prod.yaml logs -f"
echo "Stop: docker compose -f docker-compose.prod.yaml down"
