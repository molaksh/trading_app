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

echo "=========================================="
echo "US Alpaca Paper Trading Container"
echo "=========================================="
echo ""

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment from .env..."
    source .env
fi

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
  -e ENV=paper \
  -e BROKER=alpaca \
  -e MODE=swing \
  -e MARKET=us \
  -e BASE_DIR=/app/logs \
  -e MARKET_TIMEZONE=America/New_York \
  -e ENTRY_WINDOW_MINUTES_BEFORE_CLOSE=5 \
  -e SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE=15 \
  -e ALPACA_API_KEY="${APCA_API_KEY_ID}" \
  -e ALPACA_API_SECRET="${APCA_API_SECRET_KEY}" \
  -e ALPACA_BASE_URL="${APCA_API_BASE_URL}" \
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
