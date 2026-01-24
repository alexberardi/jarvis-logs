#!/bin/bash
set -e

# Run tests for jarvis-logs
# Uses Docker to ensure consistent environment

docker run --rm -v "$(pwd)":/app -w /app python:3.11-slim sh -c "
    pip install -q -r requirements.txt 2>/dev/null
    python -m pytest tests/ \"\$@\"
" -- "$@"
