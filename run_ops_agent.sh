#!/bin/bash
#
# Run Phase E: OpenClaw Ops Agent (24/7)
#
# The ops agent handles Telegram inquiries about system state.
# READ-ONLY, SAFE, BOUNDED.
# Uses OpenClaw gateway with a trading-ops skill.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/docker_utils.sh"

echo "==========================================="
echo "Phase E: OpenClaw Ops Agent (24/7)"
echo "==========================================="
echo ""

if [ -f ".env" ]; then
    source .env
fi

# Check for Telegram token
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN not set"
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
    echo "ERROR: TELEGRAM_ALLOWED_CHAT_IDS not set"
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

# Rebuild image from OpenClaw Dockerfile
rebuild_image "ops-agent" "Dockerfile.openclaw"

# Extract OpenAI API key from .env (CHATGPT_API_KEY)
OPENAI_API_KEY="${OPENAI_API_KEY:-$(grep '^CHATGPT_API_KEY=' .env 2>/dev/null | cut -d'=' -f2)}"

if [ -z "$OPENAI_API_KEY" ]; then
    echo "WARNING: OPENAI_API_KEY / CHATGPT_API_KEY not found"
    echo "   Set OPENAI_API_KEY or CHATGPT_API_KEY in .env"
    echo ""
    exit 1
fi

# Run container continuously
# Mounts logs/ and persist/ as READ-ONLY volumes
echo "Starting OpenClaw ops agent container..."
docker run -d \
  --name ops-agent \
  --restart unless-stopped \
  -v "$SCRIPT_DIR/logs:/data/logs:ro" \
  -v "$SCRIPT_DIR/persist:/data/persist:ro" \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  -e TELEGRAM_ALLOWED_CHAT_IDS="$TELEGRAM_ALLOWED_CHAT_IDS" \
  -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
  -e OPENCLAW_MODEL="${OPENCLAW_MODEL:-openai/gpt-4o-mini}" \
  -e TZ=UTC \
  ops-agent

echo ""
echo "Ops agent started (OpenClaw gateway)"
echo ""
echo "View logs:  docker logs -f ops-agent"
echo "Stop:       docker stop ops-agent"
echo ""

echo "To add daily digest cron (optional):"
echo "  docker exec ops-agent openclaw cron add --name daily-digest --cron '0 22 * * *' --tz America/New_York --channel telegram --message 'Generate daily trading digest for all scopes.'"
echo ""
