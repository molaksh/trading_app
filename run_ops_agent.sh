#!/bin/bash
#
# Run Phase E: Interactive Ops & Concierge Agent (24/7)
#
# The ops agent handles Telegram inquiries about system state.
# READ-ONLY, SAFE, BOUNDED.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/docker_utils.sh"

PERSISTENCE_ROOT_HOST="${PERSISTENCE_ROOT_HOST:-$SCRIPT_DIR/logs}"
mkdir -p "$PERSISTENCE_ROOT_HOST"

echo "==========================================="
echo "Phase E: Ops Agent (24/7)"
echo "==========================================="
echo ""

if [ -f ".env" ]; then
    source .env
fi

# Check for Telegram token
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ ERROR: TELEGRAM_BOT_TOKEN not set"
    echo ""
    echo "Steps to set up:"
    echo "1. Talk to @BotFather on Telegram"
    echo "2. Create a new bot: /newbot"
    echo "3. Copy the token"
    echo "4. export TELEGRAM_BOT_TOKEN='your-token-here'"
    echo ""
    exit 1
fi

if [ -z "$TELEGRAM_ALLOWED_CHAT_IDS" ]; then
    echo "❌ ERROR: TELEGRAM_ALLOWED_CHAT_IDS not set"
    echo ""
    echo "Steps to get your chat ID:"
    echo "1. Message the bot any text"
    echo "2. Run: curl https://api.telegram.org/bot\$TELEGRAM_BOT_TOKEN/getUpdates"
    echo "3. Find 'chat.id' in response"
    echo "4. export TELEGRAM_ALLOWED_CHAT_IDS='your-chat-id'"
    echo ""
    exit 1
fi

# Stop and remove old container
docker rm -f ops-agent 2>/dev/null || true

# Rebuild image
rebuild_image "ops-agent"

# Run container continuously
echo "Starting ops agent container..."
docker run -d \
  --name ops-agent \
  --restart unless-stopped \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  -e TELEGRAM_ALLOWED_CHAT_IDS="$TELEGRAM_ALLOWED_CHAT_IDS" \
  -e PERSISTENCE_ROOT=/app/persist \
  -e PYTHONUNBUFFERED=1 \
  -e TZ=UTC \
  ops-agent \
  python ops_main.py

echo "✓ Ops agent started"
echo ""
echo "View logs: docker logs -f ops-agent"
echo "Stop: docker stop ops-agent"
echo ""
