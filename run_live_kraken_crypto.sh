#!/bin/bash
# Run live trading container for crypto (Kraken) global scope
# This container connects to real Kraken API (read-only or with API key restrictions)

set -e

DOCKER_IMAGE="trading_app:latest"
CONTAINER_NAME="trading_app_live_kraken_crypto"
CONFIG="config/crypto/live.kraken.crypto.global.yaml"

# Check if image exists
if ! docker image inspect $DOCKER_IMAGE > /dev/null 2>&1; then
    echo "Error: Docker image '$DOCKER_IMAGE' not found. Build it first with:"
    echo "  docker build -t trading_app:latest ."
    exit 1
fi

# Check for Kraken API credentials
if [ -z "$KRAKEN_API_KEY" ] || [ -z "$KRAKEN_API_SECRET" ]; then
    echo "Error: Kraken API credentials not found."
    echo "Set environment variables:"
    echo "  export KRAKEN_API_KEY='your-api-key'"
    echo "  export KRAKEN_API_SECRET='your-api-secret'"
    exit 1
fi

echo "=========================================="
echo "Starting Live Trading Container"
echo "  Scope: live_kraken_crypto_global"
echo "  Broker: Kraken (Live)"
echo "  Config: $CONFIG"
echo "  WARNING: This will connect to REAL Kraken API"
echo "=========================================="

# Create data directories if needed
mkdir -p data/artifacts/crypto/kraken_global/{models,candidates,validations,shadow}
mkdir -p data/logs/crypto/kraken_global/{observations,trades,approvals,registry}
mkdir -p data/datasets/crypto/kraken_global/{training,validation,live}
mkdir -p data/ledger/crypto/kraken_global

# Run container with API credentials
docker run \
    --name "$CONTAINER_NAME" \
    --rm \
    -it \
    -e SCOPE="live_kraken_crypto_global" \
    -e CONFIG="$CONFIG" \
    -e LOG_LEVEL="INFO" \
    -e KRAKEN_API_KEY="$KRAKEN_API_KEY" \
    -e KRAKEN_API_SECRET="$KRAKEN_API_SECRET" \
    -v "$(pwd)/config:/app/config:ro" \
    -v "$(pwd)/data:/data" \
    -v "$(pwd)/logs:/app/logs" \
    "$DOCKER_IMAGE" \
    python main.py

echo "=========================================="
echo "Live trading container stopped"
echo "=========================================="
