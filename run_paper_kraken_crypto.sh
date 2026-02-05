#!/bin/bash
# Run paper trading container for crypto (Kraken) global scope
# This container tests trading strategies with simulated trades

set -e

DOCKER_IMAGE="trading_app:latest"
CONTAINER_NAME="trading_app_paper_kraken_crypto"
CONFIG="config/crypto/paper.kraken.crypto.global.yaml"

# Check if image exists
if ! docker image inspect $DOCKER_IMAGE > /dev/null 2>&1; then
    echo "Error: Docker image '$DOCKER_IMAGE' not found. Build it first with:"
    echo "  docker build -t trading_app:latest ."
    exit 1
fi

echo "=========================================="
echo "Starting Paper Trading Container"
echo "  Scope: paper_kraken_crypto_global"
echo "  Broker: Kraken (Simulated)"
echo "  Config: $CONFIG"
echo "=========================================="

# Load environment variables from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Create data directories if needed
mkdir -p data/artifacts/crypto/kraken_global/{models,candidates,validations,shadow}
mkdir -p data/logs/crypto/kraken_global/{observations,trades,approvals,registry}
mkdir -p data/datasets/crypto/kraken_global/{training,validation,live}
mkdir -p data/ledger/crypto/kraken_global
mkdir -p data/persist/crypto/kraken_global

# Check if running in background mode
BACKGROUND_MODE=${1:-""}
if [ "$BACKGROUND_MODE" == "-d" ] || [ "$BACKGROUND_MODE" == "--detach" ]; then
    DOCKER_FLAGS="-d"
    echo "Running in BACKGROUND mode..."
else
    DOCKER_FLAGS="-it"
    echo "Running in INTERACTIVE mode..."
fi

# Run container
docker run \
    --name "$CONTAINER_NAME" \
    --rm \
    $DOCKER_FLAGS \
    -e SCOPE="paper_kraken_crypto_global" \
    -e CONFIG="$CONFIG" \
    -e LOG_LEVEL="INFO" \
    -e PERSISTENCE_ROOT="/app/persist" \
    -e CASH_ONLY_TRADING="true" \
    -e KRKN_LIVE_API_KEY_ID="${KRKN_LIVE_API_KEY_ID}" \
    -e KRKN_LIVE_API_SECRET_KEY="${KRKN_LIVE_API_SECRET_KEY}" \
    -e APCA_API_BASE_URL="${APCA_API_BASE_URL}" \
    -e APCA_API_KEY_ID="${APCA_API_KEY_ID}" \
    -e APCA_API_SECRET_KEY="${APCA_API_SECRET_KEY}" \
    -v "$(pwd)/config:/app/config:ro" \
    -v "$(pwd)/data:/data" \
    -v "$(pwd)/data/persist:/app/persist" \
    -v "$(pwd)/logs:/app/logs" \
    "$DOCKER_IMAGE" \
    python main.py

if [ "$BACKGROUND_MODE" == "-d" ] || [ "$BACKGROUND_MODE" == "--detach" ]; then
    echo "=========================================="
    echo "Paper trading container started in background"
    echo "  Container: $CONTAINER_NAME"
    echo "  Logs: docker logs -f $CONTAINER_NAME"
    echo "=========================================="
else
    echo "=========================================="
    echo "Paper trading container stopped"
    echo "=========================================="
fi
