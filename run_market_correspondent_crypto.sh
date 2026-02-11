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

# Extract API keys & config
NEWSAPI_KEY="${NEWSAPI_KEY:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
CRYPTOCOMPARE_API_KEY="${CRYPTOCOMPARE_API_KEY:-}"
TWITTER_BEARER_TOKEN="${TWITTER_BEARER_TOKEN:-}"

echo "Phase F Multi-Source News Fetcher Configuration:"
echo "  RSS Feeds: ${PHASE_F_RSS_ENABLED:-true}"
echo "  Web Scraper: ${PHASE_F_WEB_SCRAPER_ENABLED:-true}"
echo "  CoinTelegraph: ${COINTELEGRAPH_ENABLED:-false}"
echo "  CryptoCompare: $([ -n "$CRYPTOCOMPARE_API_KEY" ] && echo 'configured' || echo 'not configured')"
echo "  Twitter: ${TWITTER_SCRAPER_ENABLED:-false}"

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
  -e PHASE_F_USE_MULTI_SOURCE_FETCHER="${PHASE_F_USE_MULTI_SOURCE_FETCHER:-true}" \
  -e PHASE_F_RUN_SCHEDULE_UTC="${PHASE_F_RUN_SCHEDULE_UTC:-03:00}" \
  -e NEWSAPI_KEY="$NEWSAPI_KEY" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e PHASE_F_RSS_ENABLED="${PHASE_F_RSS_ENABLED:-true}" \
  -e PHASE_F_WEB_SCRAPER_ENABLED="${PHASE_F_WEB_SCRAPER_ENABLED:-true}" \
  -e COINTELEGRAPH_ENABLED="${COINTELEGRAPH_ENABLED:-false}" \
  -e CRYPTOCOMPARE_API_KEY="$CRYPTOCOMPARE_API_KEY" \
  -e TWITTER_BEARER_TOKEN="$TWITTER_BEARER_TOKEN" \
  -e TWITTER_SCRAPER_ENABLED="${TWITTER_SCRAPER_ENABLED:-false}" \
  "$IMAGE_NAME" \
  python phase_f_main.py --daemon

echo "Phase F container started: $CONTAINER_NAME"
echo "Logs: docker logs -f $CONTAINER_NAME"
echo "Scheduler state: cat persist/phase_f/crypto/scheduler_state.json"
