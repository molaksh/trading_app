#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Configuration
CONTAINER_NAME="market-correspondent-crypto"
IMAGE_NAME="market-correspondent-crypto"
PERSISTENCE_ROOT_HOST="${PWD}/persist"
LOGS_ROOT_HOST="${PWD}/logs"

# Extract API keys
NEWSAPI_KEY="${NEWSAPI_KEY:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"

if [ -z "$NEWSAPI_KEY" ]; then
    echo "WARNING: NEWSAPI_KEY not set in .env - NewsAPI will be disabled"
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "WARNING: OPENAI_API_KEY not set in .env - Some features may be limited"
fi

# Build image
echo "Building Phase F image..."
docker build -t "$IMAGE_NAME" -f Dockerfile.phase_f .

# Stop existing container
echo "Stopping existing Phase F container..."
docker stop "$CONTAINER_NAME" 2>/dev/null || true
docker rm "$CONTAINER_NAME" 2>/dev/null || true

# Run container
echo "Starting Phase F daemon..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -v "$LOGS_ROOT_HOST:/app/logs" \
  -e PHASE_F_ENABLED="${PHASE_F_ENABLED:-true}" \
  -e PHASE_F_KILL_SWITCH="${PHASE_F_KILL_SWITCH:-false}" \
  -e PHASE_F_RUN_SCHEDULE_UTC="${PHASE_F_RUN_SCHEDULE_UTC:-03:00}" \
  -e NEWSAPI_KEY="$NEWSAPI_KEY" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  "$IMAGE_NAME" \
  python phase_f_main.py --daemon

echo "Phase F container started: $CONTAINER_NAME"
echo "Logs: docker logs -f $CONTAINER_NAME"
echo "Scheduler state: cat persist/phase_f/crypto/scheduler_state.json"
