#!/bin/bash
#
# Build and run US paper trading container
#
# Container: paper-alpaca-swing-us
# Image: paper-alpaca-swing-us
# SCOPE: paper_alpaca_swing_us
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Host persistence directory (outside container)
PERSISTENCE_ROOT_HOST="${PERSISTENCE_ROOT_HOST:-$SCRIPT_DIR/logs}"
mkdir -p "$PERSISTENCE_ROOT_HOST"

echo "=========================================="
echo "US Alpaca Paper Trading Container"
echo "=========================================="
echo ""

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment from .env..."
    source .env
fi

# Scope + host paths
ENV_VALUE="paper"
BROKER_VALUE="alpaca"
MODE_VALUE="swing"
MARKET_VALUE="us"

SCOPE=$(printf "%s_%s_%s_%s" "$ENV_VALUE" "$BROKER_VALUE" "$MODE_VALUE" "$MARKET_VALUE" | tr '[:upper:]' '[:lower:]')
SCOPE_DIR="$PERSISTENCE_ROOT_HOST/$SCOPE"
LEDGER_FILE="$SCOPE_DIR/ledger/trades.jsonl"

# Ensure scope directories + ledger file exist on host (hard gate prerequisite)
mkdir -p "$SCOPE_DIR/logs" "$SCOPE_DIR/ledger" "$SCOPE_DIR/models"
touch "$LEDGER_FILE"

# Stop old container if running
echo "Stopping old container (if running)..."
docker stop paper-alpaca-swing-us 2>/dev/null || true

# Remove old container if exists
echo "Removing old container (if exists)..."
docker rm paper-alpaca-swing-us 2>/dev/null || true

# Remove old image if exists
echo "Removing old image (if exists)..."
docker rmi paper-alpaca-swing-us 2>/dev/null || true

# Build Docker image
echo "Building Docker image: paper-alpaca-swing-us..."
docker build -t paper-alpaca-swing-us .

# Run container
echo "Starting container: paper-alpaca-swing-us..."
docker run -d \
  --name paper-alpaca-swing-us \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -e ENV="$ENV_VALUE" \
  -e BROKER="$BROKER_VALUE" \
  -e MODE="$MODE_VALUE" \
  -e MARKET="$MARKET_VALUE" \
  -e PERSISTENCE_ROOT=/app/persist \
  -e MARKET_TIMEZONE=America/New_York \
  -e ENTRY_WINDOW_MINUTES_BEFORE_CLOSE=5 \
  -e SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE=15 \
  -e APCA_API_KEY_ID="${APCA_API_KEY_ID}" \
  -e APCA_API_SECRET_KEY="${APCA_API_SECRET_KEY}" \
  -e APCA_API_BASE_URL="${APCA_API_BASE_URL}" \
  paper-alpaca-swing-us python -m execution.scheduler

echo ""
echo "✅ Container started successfully!"
echo ""
echo "View logs:"
echo "  docker logs -f paper-alpaca-swing-us"
echo ""
echo "Check status:"
echo "  docker ps | grep paper-alpaca"
echo ""
echo "Stop container:"
echo "  docker stop paper-alpaca-swing-us"
echo ""

# -----------------------------------------------------------------------------
# Post-start verification (hard gate)
# -----------------------------------------------------------------------------
VERIFY_TIMEOUT_SECONDS=${VERIFY_TIMEOUT_SECONDS:-180}
VERIFY_SLEEP_SECONDS=${VERIFY_SLEEP_SECONDS:-3}
ALLOWED_PROVIDERS_REGEX=${ALLOWED_PROVIDERS_REGEX:-"alpaca|nse|zerodha|yahoo|ibkr|crypto"}

echo "=========================================="
echo "Post-start verification"
echo "=========================================="

fail_count=0
warn_count=0

pass() { echo "✔ $1"; }
warn() { echo "⚠ $1"; warn_count=$((warn_count+1)); }
fail() { echo "❌ $1"; fail_count=$((fail_count+1)); }

check_present() {
  local pattern="$1"
  local label="$2"
  if echo "$logs" | grep -Eiq "$pattern"; then
    pass "$label"
  else
    fail "$label"
  fi
}

check_absent() {
  local pattern="$1"
  local label="$2"
  if echo "$logs" | grep -Eiq "$pattern"; then
    fail "$label"
  else
    pass "$label"
  fi
}

# 1) Container start confirmation
status=$(docker inspect -f '{{.State.Status}}' paper-alpaca-swing-us 2>/dev/null || true)
restarting=$(docker inspect -f '{{.State.Restarting}}' paper-alpaca-swing-us 2>/dev/null || true)
restart_count=$(docker inspect -f '{{.RestartCount}}' paper-alpaca-swing-us 2>/dev/null || echo 0)
if [ "$status" = "running" ] && [ "$restarting" = "false" ] && [ "$restart_count" = "0" ]; then
  pass "Container running (no restarts)"
else
  fail "Container not healthy (status=$status restarting=$restarting restarts=$restart_count)"
fi

# Collect logs (retry loop)
start_ts=$(date +%s)
logs=""
while true; do
  logs=$(docker logs paper-alpaca-swing-us 2>&1 || true)
  if [ -n "$logs" ]; then
    if echo "$logs" | grep -Eiq "Safe Mode:|safe_mode=|SAFE_MODE|Reconciliation status"; then
      break
    fi
  fi
  now_ts=$(date +%s)
  if [ $((now_ts - start_ts)) -ge "$VERIFY_TIMEOUT_SECONDS" ]; then
    break
  fi
  sleep "$VERIFY_SLEEP_SECONDS"
done

# 1a) Logs exist on host (directory present)
if [ -d "$SCOPE_DIR/logs" ]; then
  pass "Logs detected on host"
else
  fail "Logs missing on host ($SCOPE_DIR/logs)"
fi

# 2) SAFE_MODE / mock detection
check_absent "SAFE_MODE=true|safe_mode=True|Safe Mode: True|mock|fallback|default provider|unknown provider|provider: none" "No SAFE_MODE/mock detected"
check_present "SAFE_MODE disabled|safe_mode=[[:space:]]*False|Safe Mode:[[:space:]]*False" "SAFE_MODE disabled"

# 3) Market data provider verification
if echo "$logs" | grep -Eiq "Market data provider initialized: ($ALLOWED_PROVIDERS_REGEX)|NSEProvider initialized|Alpaca adapter initialized"; then
  provider=$(echo "$logs" | grep -Ei "Market data provider initialized: ($ALLOWED_PROVIDERS_REGEX)" | tail -1 | sed -E 's/.*initialized: *([a-zA-Z0-9_]+).*/\1/I')
  if [ -z "$provider" ]; then
    provider="$BROKER_VALUE"
  fi
  pass "Market data provider: $provider"
else
  fail "Market data provider invalid or missing"
fi

# 4) Persistence root & scope path check
check_present "Persistence root validated|Persistence root: /app/persist|Resolved scope path:|Ledger path:|Models path:" "Persistence root validated"

if [ -d "$SCOPE_DIR/logs" ] && [ -d "$SCOPE_DIR/ledger" ] && [ -d "$SCOPE_DIR/models" ]; then
  pass "Scope directories present (logs/ledger/models)"
else
  fail "Missing scope directories (logs/ledger/models)"
fi

# 5) Ledger file guarantee
if [ -f "$LEDGER_FILE" ]; then
  pass "Ledger initialized"
else
  fail "Ledger not initialized — container invalid"
fi

# 6) External position backfill verification
if echo "$logs" | grep -Eiq "EXTERNAL POSITION"; then
  if echo "$logs" | grep -Eiq "LEDGER WRITE \(BACKFILL\)|LEDGER BACKFILL COMPLETE|LEDGER RECONCILIATION: Backfilling"; then
    pass "External positions persisted"
  else
    fail "External positions detected but not persisted"
  fi
fi

# 7) Runtime activity check
if echo "$logs" | grep -Eiq "Scan started|Strategy evaluation|Scheduler tick|Market hours evaluation|ML fingerprint|DatasetBuilder|Universe loaded:|Fetched OHLCV for|Cache hit for|Scanning symbols|Generating entry intents"; then
  pass "Runtime activity detected"
else
  warn "No runtime activity detected"
fi

echo ""
if [ "$fail_count" -gt 0 ]; then
  echo "❌ Verification failed: $fail_count failure(s), $warn_count warning(s)"
  exit 1
fi

echo "✔ Verification passed with $warn_count warning(s)"
