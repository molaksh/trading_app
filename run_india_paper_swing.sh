#!/bin/bash
#
# Build and run India NSE paper trading container
#
# Container: paper-nse-swing-india
# Image: paper-nse-swing-india
# SCOPE: paper_nse_simulator_swing_india
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Host persistence directory (outside container)
PERSISTENCE_ROOT_HOST="${PERSISTENCE_ROOT_HOST:-$SCRIPT_DIR/logs}"
mkdir -p "$PERSISTENCE_ROOT_HOST"

echo "=========================================="
echo "India NSE Paper Trading Container"
echo "=========================================="
echo ""

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment from .env..."
    source .env
fi

# Stop old container if running
echo "Stopping old container (if running)..."
docker stop paper-nse-swing-india 2>/dev/null || true

# Remove old container if exists
echo "Removing old container (if exists)..."
docker rm paper-nse-swing-india 2>/dev/null || true

# Remove old image if exists
echo "Removing old image (if exists)..."
docker rmi paper-nse-swing-india 2>/dev/null || true

# Build Docker image
echo "Building Docker image: paper-nse-swing-india..."
docker build -f Dockerfile.india -t paper-nse-swing-india .

# Run container
echo "Starting container: paper-nse-swing-india..."
docker run -d \
  --name paper-nse-swing-india \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -e ENV=paper \
  -e BROKER=nse_simulator \
  -e MODE=swing \
  -e MARKET=india \
  -e PERSISTENCE_ROOT=/app/persist \
  -e MARKET_TIMEZONE=Asia/Kolkata \
  -e ENTRY_WINDOW_MINUTES_BEFORE_CLOSE=20 \
  -e SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE=15 \
  paper-nse-swing-india python -m execution.scheduler

echo ""
echo "✅ Container started successfully!"
echo ""
echo "View logs:"
echo "  docker logs -f paper-nse-swing-india"
echo ""
echo "Check status:"
echo "  docker ps | grep paper-nse"
echo ""
echo "Stop container:"
echo "  docker stop paper-nse-swing-india"
echo ""
