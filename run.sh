#!/bin/bash
# Development server with hot reload
# Usage: ./run.sh [--docker] [--build]

set -e
cd "$(dirname "$0")"

if [[ "$1" == "--docker" ]]; then
    # Docker development mode (full stack with hot reload)
    BUILD_FLAGS=""
    if [[ "$2" == "--rebuild" ]]; then
        docker compose -f docker-compose.dev.yaml build --no-cache 
        BUILD_FLAGS="--build"
    elif [[ "$2" == "--build" ]]; then
        BUILD_FLAGS="--build"
    fi

    echo "Starting jarvis-logs stack (jarvis-logs + Loki + Grafana)..."
    docker compose -f docker-compose.dev.yaml up $BUILD_FLAGS -d
else
    # Local development mode
    # Load environment variables
    if [ -f .env ]; then
        export $(cat .env | grep -v '^#' | xargs)
    fi

    PORT=${LOG_SERVER_PORT:-8006}

    echo "Starting jarvis-logs server locally on port $PORT..."
    echo "Note: Requires Loki running at ${LOKI_URL:-http://localhost:3100}"
    echo ""
    uvicorn app.main:app --reload --host 0.0.0.0 --port $PORT
fi
