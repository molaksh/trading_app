#!/bin/bash
# Run live trading daemon for crypto (Kraken) - 24/7 continuous
#
# This container connects to real Kraken API with live orders.
# Runs as a DAEMON (continuous loop, not batch mode).
#
# WARNING: This connects to REAL Kraken API with real money.
# Use only after testing thoroughly in paper mode.
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
echo "Crypto LIVE Trading Daemon (Kraken)"
echo "=========================================="
echo "⚠️  WARNING: Connecting to REAL Kraken API"
echo "    This will execute REAL orders with REAL money"
echo ""
echo "Mode: 24/7 continuous daemon"
echo "Entry: python crypto_main.py"
echo "=========================================="
echo ""

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment from .env..."
    source .env
fi

# Check for Kraken API credentials
if [ -z "$KRAKEN_API_KEY" ] || [ -z "$KRAKEN_API_SECRET" ]; then
    echo "Error: Kraken API credentials not found."
    echo "Set environment variables:"
    echo "  export KRAKEN_API_KEY='your-api-key'"
    echo "  export KRAKEN_API_SECRET='your-api-secret'"
    exit 1
fi

echo "✓ Kraken API credentials detected"
echo ""

# Scope + host paths
ENV_VALUE="live"
BROKER_VALUE="kraken"
MODE_VALUE="crypto"
MARKET_VALUE="global"

SCOPE=$(printf "%s_%s_%s_%s" "$ENV_VALUE" "$BROKER_VALUE" "$MODE_VALUE" "$MARKET_VALUE" | tr '[:upper:]' '[:lower:]')
SCOPE_DIR="$PERSISTENCE_ROOT_HOST/$SCOPE"
LEDGER_FILE="$SCOPE_DIR/ledger/trades.jsonl"

# Ensure scope directories + ledger file exist on host
setup_scope_directories "$SCOPE_DIR" "$LEDGER_FILE"

# Stop and remove old container
stop_and_remove_container "live-kraken-crypto-global" "$SCOPE_DIR"

# Rebuild image
rebuild_image "live-kraken-crypto-global"

# Run container (DAEMON MODE: continues running 24/7)
echo "Starting container: live-kraken-crypto-global (daemon)..."
echo ""

docker run -d \
  --name live-kraken-crypto-global \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -e ENV="$ENV_VALUE" \
  -e BROKER="$BROKER_VALUE" \
  -e MODE="$MODE_VALUE" \
  -e MARKET="$MARKET_VALUE" \
  -e SCOPE="$SCOPE" \
  -e PERSISTENCE_ROOT=/app/persist \
  -e MARKET_TIMEZONE=UTC \
  -e CASH_ONLY_TRADING=true \
  -e KRAKEN_API_KEY="$KRAKEN_API_KEY" \
  -e KRAKEN_API_SECRET="$KRAKEN_API_SECRET" \
  -e CRYPTO_DOWNTIME_START_UTC="${CRYPTO_DOWNTIME_START_UTC:-03:00}" \
  -e CRYPTO_DOWNTIME_END_UTC="${CRYPTO_DOWNTIME_END_UTC:-05:00}" \
  -e CRYPTO_SCHEDULER_TICK_SECONDS="${CRYPTO_SCHEDULER_TICK_SECONDS:-60}" \
  -e PYTHONUNBUFFERED=1 \
  live-kraken-crypto-global \
  python crypto_main.py

echo ""
echo "Container ID: $(docker ps -q -f name=live-kraken-crypto-global)"
echo ""

# Verify container is running
echo "=========================================="
echo "Post-start verification"
echo "=========================================="

if docker ps -q -f name=live-kraken-crypto-global | grep -q .; then
    echo "✔ Container running (LIVE daemon mode)"
    echo "✔ Logs: docker logs -f live-kraken-crypto-global"
    echo "✔ Stop: docker stop live-kraken-crypto-global"
    echo ""
    echo "Scheduler state:"
    echo "  Location: $SCOPE_DIR/state/crypto_scheduler_state.json"
    echo "  Downtime: ${CRYPTO_DOWNTIME_START_UTC:-03:00}-${CRYPTO_DOWNTIME_END_UTC:-05:00} UTC"
    echo ""
    echo "⚠️  REMINDER: Orders are LIVE. Monitor logs closely."
else
    echo "✗ Container failed to start"
    docker logs live-kraken-crypto-global || true
    exit 1
fi
