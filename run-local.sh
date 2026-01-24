#!/bin/bash
set -e

cd "$(dirname "$0")"

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default port
PORT=${LOG_SERVER_PORT:-8006}

echo "Starting jarvis-logs server locally on port $PORT..."
echo "Note: Requires Loki running at ${LOKI_URL:-http://localhost:3100}"
echo ""
uvicorn app.main:app --reload --host 0.0.0.0 --port $PORT
