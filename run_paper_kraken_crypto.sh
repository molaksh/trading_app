#!/bin/bash
#
# Build and run crypto paper trading container (24/7 daemon)
#
# Container: paper-kraken-crypto-global
# Image: paper-kraken-crypto-global
# SCOPE: paper_kraken_crypto_global
#
# This now runs as a DAEMON (continuous 24/7) instead of batch.
# - Runs python crypto_main.py (scheduler loop, not python main.py)
# - Persists state so tasks don't rerun after restart
# - Has daily downtime window for ML training (03:00-05:00 UTC by default)
# - To stop: docker stop paper-kraken-crypto-global
# - To view logs: docker logs -f paper-kraken-crypto-global
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
echo "Crypto Paper Trading Daemon (Kraken)"
echo "=========================================="
echo "Mode: 24/7 continuous (not batch)"
echo "Entry: python crypto_main.py"
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

# Run container (DAEMON MODE: continues running)
echo "Starting container: paper-kraken-crypto-global (daemon)..."
docker run -d \
  --name paper-kraken-crypto-global \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -e ENV="$ENV_VALUE" \
  -e BROKER="$BROKER_VALUE" \
  -e MODE="$MODE_VALUE" \
  -e MARKET="$MARKET_VALUE" \
  -e SCOPE="$SCOPE" \
  -e PERSISTENCE_ROOT=/app/persist \
  -e MARKET_TIMEZONE=America/New_York \
  -e TZ=America/New_York \
  -e CASH_ONLY_TRADING=true \
  -e KRAKEN_API_KEY="${KRAKEN_API_KEY:-stub}" \
  -e KRAKEN_API_SECRET="${KRAKEN_API_SECRET:-stub}" \
  -e CRYPTO_DOWNTIME_START_UTC="${CRYPTO_DOWNTIME_START_UTC:-08:00}" \
  -e CRYPTO_DOWNTIME_END_UTC="${CRYPTO_DOWNTIME_END_UTC:-10:00}" \
  -e CRYPTO_SCHEDULER_TICK_SECONDS="${CRYPTO_SCHEDULER_TICK_SECONDS:-60}" \
  -e PYTHONUNBUFFERED=1 \
  paper-kraken-crypto-global \
  python crypto_main.py

echo ""
echo "Container ID: $(docker ps -q -f name=paper-kraken-crypto-global)"
echo ""

# Verify container is running
echo "=========================================="
echo "Post-start verification"
echo "=========================================="

if docker ps -q -f name=paper-kraken-crypto-global | grep -q .; then
    echo "✔ Container running (daemon mode)"
    echo "✔ Logs: docker logs -f paper-kraken-crypto-global"
    echo "✔ Stop: docker stop paper-kraken-crypto-global"
    echo "✔ Status: docker ps | grep paper-kraken"
    echo ""
    echo "Scheduler state:"
    echo "  Location: $SCOPE_DIR/state/crypto_scheduler_state.json"
    echo "  Downtime: 3-5 AM ET (08:00-10:00 UTC)"
    docker logs paper-kraken-crypto-global || true
    exit 1
fi
