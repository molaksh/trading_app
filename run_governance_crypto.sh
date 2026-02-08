#!/bin/bash
#
# Run governance container 24/7
# Keeps container running with internal job scheduler
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source "$SCRIPT_DIR/scripts/docker_utils.sh"

PERSISTENCE_ROOT_HOST="${PERSISTENCE_ROOT_HOST:-$SCRIPT_DIR/logs}"
mkdir -p "$PERSISTENCE_ROOT_HOST"

echo "==========================================="
echo "Phase C: Governance Container (24/7)"
echo "==========================================="
echo ""

if [ -f ".env" ]; then
    source .env
fi

# Stop and remove old container
docker rm -f governance-crypto 2>/dev/null || true

# Rebuild image
rebuild_image "governance-crypto"

# Run container continuously
echo "Starting governance container..."
docker run -d \
  --name governance-crypto \
  --restart unless-stopped \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -e PERSISTENCE_ROOT=/app/persist \
  -e GOVERNANCE_ENABLED=true \
  -e PYTHONUNBUFFERED=1 \
  -e TZ=UTC \
  governance-crypto \
  python governance_main.py --daemon

echo "✓ Container started"
echo ""
echo "View logs: docker logs -f governance-crypto"
echo "Stop: docker stop governance-crypto"
echo ""
