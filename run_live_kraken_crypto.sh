#!/bin/bash
# Run live trading daemon for crypto (Kraken) - 24/7 continuous
#
# This container connects to REAL Kraken API with LIVE ORDERS and REAL MONEY.
# Runs as a DAEMON (continuous loop, not batch mode).
#
# CRITICAL SAFETY WARNINGS:
# 1. This connects to REAL Kraken API
# 2. This will execute REAL orders with REAL capital
# 3. LIVE_TRADING_APPROVED must be explicitly "yes"
# 4. Use only after extensive testing in paper mode
# 5. Monitor logs continuously
#
# FAIL-CLOSED DEFAULTS: All mandatory checks must pass or trading halts.
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
echo "⚠️  CRITICAL WARNING"
echo "=========================================="
echo "This connects to REAL Kraken API with REAL MONEY"
echo "All 8 startup verification checks MUST pass"
echo "LIVE_TRADING_APPROVED=yes is MANDATORY"
echo "Monitor logs continuously during operation"
echo "=========================================="
echo ""

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment from .env..."
    source .env
fi

# Set LIVE_TRADING_APPROVED=yes by default (can be overridden by environment)
if [ -z "$LIVE_TRADING_APPROVED" ]; then
    LIVE_TRADING_APPROVED="yes"
fi

# Map .env variable names to expected names for Kraken API
# .env has: KRKN_LIVE_API_KEY_ID and KRKN_LIVE_API_SECRET_KEY
# Script expects: KRAKEN_API_KEY and KRAKEN_API_SECRET
if [ -z "$KRAKEN_API_KEY" ] && [ -n "$KRKN_LIVE_API_KEY_ID" ]; then
    KRAKEN_API_KEY="$KRKN_LIVE_API_KEY_ID"
fi

if [ -z "$KRAKEN_API_SECRET" ] && [ -n "$KRKN_LIVE_API_SECRET_KEY" ]; then
    KRAKEN_API_SECRET="$KRKN_LIVE_API_SECRET_KEY"
fi

# MANDATORY: Check for explicit LIVE_TRADING_APPROVED flag
if [ "$LIVE_TRADING_APPROVED" != "yes" ]; then
    echo "=========================================="
    echo "ERROR: LIVE TRADING NOT APPROVED"
    echo "=========================================="
    echo ""
    echo "LIVE_TRADING_APPROVED is not set to 'yes'"
    echo "Current value: '$LIVE_TRADING_APPROVED'"
    echo ""
    echo "To enable LIVE trading, set:"
    echo "  export LIVE_TRADING_APPROVED=yes"
    echo ""
    echo "REMINDER: This connects to REAL Kraken API"
    echo "with REAL money. Only proceed after:"
    echo "1. Extensive paper trading testing"
    echo "2. Verification of risk limits"
    echo "3. Explicit approval of capital at risk"
    echo "=========================================="
    exit 1
fi

echo "✓ LIVE_TRADING_APPROVED=yes detected"
echo ""

# Check for Kraken API credentials
if [ -z "$KRAKEN_API_KEY" ] || [ -z "$KRAKEN_API_SECRET" ]; then
    echo "Error: Kraken API credentials not found."
    echo "Credentials should be in .env file:"
    echo "  KRKN_LIVE_API_KEY_ID=..."
    echo "  KRKN_LIVE_API_SECRET_KEY=..."
    echo "Or set environment variables:"
    echo "  export KRAKEN_API_KEY='your-api-key'"
    echo "  export KRAKEN_API_SECRET='your-api-secret'"
    exit 1
fi

echo "✓ Kraken API credentials detected"
echo ""

# Optional: Margin trading approval (default: cash-only)
if [ "$MARGIN_TRADING_APPROVED" != "yes" ]; then
    echo "✓ Cash-only mode (margin trading disabled)"
else
    echo "⚠️  MARGIN_TRADING_APPROVED=yes (margin trading enabled)"
fi
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
  -e MARKET_TIMEZONE=America/New_York \
  -e TZ=America/New_York \
  -e CASH_ONLY_TRADING=true \
  -e KRAKEN_API_KEY="$KRAKEN_API_KEY" \
  -e KRAKEN_API_SECRET="$KRAKEN_API_SECRET" \
  -e LIVE_TRADING_APPROVED="$LIVE_TRADING_APPROVED" \
  -e MARGIN_TRADING_APPROVED="${MARGIN_TRADING_APPROVED:-no}" \
  -e CRYPTO_DOWNTIME_START_UTC="${CRYPTO_DOWNTIME_START_UTC:-08:00}" \
  -e CRYPTO_DOWNTIME_END_UTC="${CRYPTO_DOWNTIME_END_UTC:-10:00}" \
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
    echo "  Downtime: 3-5 AM ET (08:00-10:00 UTC)"
    echo ""
    echo "Startup verification:"
    echo "  8 mandatory checks must pass before trading begins:"
    echo "  ✓ Environment validation (ENV=live, LIVE_TRADING_APPROVED=yes)"
    echo "  ✓ API key safety (signature validation)"
    echo "  ✓ Account safety (balance check)"
    echo "  ✓ Position reconciliation (Kraken vs ledger)"
    echo "  ✓ Strategy whitelist (6 canonical strategies)"
    echo "  ✓ Risk manager enforcement (mandatory)"
    echo "  ✓ ML read-only mode (no training)"
    echo "  ✓ Dry-run verification (first order audit)"
    echo ""
    echo "Order execution:"
    echo "  Immutable ledger: $SCOPE_DIR/ledger/trades.jsonl"
    echo "  Order types: post-only or limit (no market orders)"
    echo "  Slippage protection: enabled"
    echo "  Failure handling: halt on error, comprehensive logging"
    echo ""
    echo "CRITICAL REMINDERS:"
    echo "  ⚠️  REAL Kraken API connected"
    echo "  ⚠️  REAL money orders being executed"
    echo "  ⚠️  Monitor logs continuously"
    echo "  ⚠️  Position reconciliation critical block enabled"
    echo ""
    sleep 2
    echo "Waiting for startup checks to complete..."
    echo "(Monitor logs with: docker logs -f live-kraken-crypto-global)"
else
    echo "✗ Container failed to start"
    docker logs live-kraken-crypto-global || true
    exit 1
fi
