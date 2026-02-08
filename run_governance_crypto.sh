#!/bin/bash
#
# Run Phase C governance job (weekly, one-time execution)
#
# Container: governance-crypto
# Image: governance-crypto
# SCOPE: N/A (reads from paper_kraken_crypto_global + live_kraken_crypto_global)
#
# This runs as a ONE-TIME job (not daemon) - executes governance pipeline
# and exits when complete. Scheduled via cron for Sunday 3:15 AM ET.
#
# Usage:
#   ./run_governance_crypto.sh                    # Real execution (with persistence)
#   ./run_governance_crypto.sh --dry-run          # Dry-run (read-only)
#   docker logs governance-crypto                 # View logs
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
echo "Phase C: Crypto Governance Job"
echo "=========================================="
echo "Mode: One-time execution (not daemon)"
echo "Entry: python governance_main.py"
echo "=========================================="
echo ""

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment from .env..."
    source .env
fi

# Determine execution mode
DRY_RUN_FLAG=""
if [ "$1" == "--dry-run" ]; then
    echo "Mode: DRY-RUN (read-only, no persistence)"
    DRY_RUN_FLAG="--dry-run"
else
    echo "Mode: REAL EXECUTION (full persistence)"
fi
echo ""

# Stop and remove old container if it exists (governance doesn't persist state like daemon)
echo "Cleaning up previous governance containers..."
docker rm -f governance-crypto 2>/dev/null || true

# Rebuild image
rebuild_image "governance-crypto"

# Create log directory for governance
GOVERNANCE_LOG_DIR="$PERSISTENCE_ROOT_HOST/governance_logs"
mkdir -p "$GOVERNANCE_LOG_DIR"

# Run container (ONE-TIME MODE: runs job and exits)
echo "Starting governance job..."
docker run \
  --name governance-crypto \
  --rm \
  -v "$PERSISTENCE_ROOT_HOST:/app/persist" \
  -e PERSISTENCE_ROOT=/app/persist \
  -e GOVERNANCE_ENABLED=true \
  -e GOVERNANCE_AI_MODEL="${GOVERNANCE_AI_MODEL:-gpt-4o}" \
  -e GOVERNANCE_LOOKBACK_DAYS="${GOVERNANCE_LOOKBACK_DAYS:-7}" \
  -e PYTHONUNBUFFERED=1 \
  -e TZ=UTC \
  governance-crypto \
  python governance_main.py $DRY_RUN_FLAG

echo ""
echo "=========================================="
echo "Governance job completed"
echo "=========================================="
echo ""
echo "Artifacts location:"
echo "  Proposals: $PERSISTENCE_ROOT_HOST/governance/crypto/proposals/"
echo "  Events:    $PERSISTENCE_ROOT_HOST/governance/crypto/logs/governance_events.jsonl"
echo ""
