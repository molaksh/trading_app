#!/bin/bash
#
# Build and run crypto paper trading container
#
# Container: paper-kraken-crypto-global
# Image: paper-kraken-crypto-global
# SCOPE: paper_kraken_crypto_global
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load docker utilities
source "$SCRIPT_DIR/scripts/docker_utils.sh"

# Host persistence directory (outside container)
PERSISTENCE_ROOT_HOST="${PERSISTENCE_ROOT_HOST:-$SCRIPT_DIR/logs}"
mkdir -p "$PERSISTENCE_ROOT_HOST"

echo "=========================================="
echo "Crypto Paper Trading Container (Kraken)"
echo "=========================================="
echo ""

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment from .env..."
    source .env
fi

# Scope + host paths
ENV_VALUE="paper"
BROKER_VALUE="kraken"
MODE_VALUE="crypto"
MARKET_VALUE="global"

SCOPE=$(printf "%s_%s_%s_%s" "$ENV_VALUE" "$BROKER_VALUE" "$MODE_VALUE" "$MARKET_VALUE" | tr '[:upper:]' '[:lower:]')
SCOPE_DIR="$PERSISTENCE_ROOT_HOST/$SCOPE"
LEDGER_FILE="$SCOPE_DIR/ledger/trades.jsonl"

# Ensure scope directories + ledger file exist on host (hard gate prerequisite)
setup_scope_directories "$SCOPE_DIR" "$LEDGER_FILE"

# Stop and remove old container (persists logs automatically)
stop_and_remove_container "paper-kraken-crypto-global" "$SCOPE_DIR"

# Rebuild image
rebuild_image "paper-kraken-crypto-global"

# Run container
echo "Starting container: paper-kraken-crypto-global..."
docker run -d \
  --name paper-kraken-crypto-global \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -e ENV="$ENV_VALUE" \
  -e BROKER="$BROKER_VALUE" \
  -e MODE="$MODE_VALUE" \
  -e MARKET="$MARKET_VALUE" \
  -e SCOPE="$SCOPE" \
  -e PERSISTENCE_ROOT=/app/persist \
  -e MARKET_TIMEZONE=UTC \
  -e CASH_ONLY_TRADING=true \
  -e KRAKEN_API_KEY="${KRAKEN_API_KEY:-stub}" \
  -e KRAKEN_API_SECRET="${KRAKEN_API_SECRET:-stub}" \
  -e PYTHONUNBUFFERED=1 \
  paper-kraken-crypto-global \
  python main.py

echo ""
echo "Container ID: $(docker ps -q -f name=paper-kraken-crypto-global)"
echo ""

# Verify container is running
echo "=========================================="
echo "Post-start verification"
echo "=========================================="

if docker ps -q -f name=paper-kraken-crypto-global | grep -q .; then
    echo "✔ Container running"
    echo "✔ Logs: docker logs -f paper-kraken-crypto-global"
    echo "✔ Status: docker ps | grep paper-kraken"
else
    echo "✗ Container failed to start"
    docker logs paper-kraken-crypto-global || true
    exit 1
fi
