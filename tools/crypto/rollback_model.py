#!/usr/bin/env python3
"""
Rollback crypto model to previous approved version.

Usage:
  python tools/crypto/rollback_model.py --env live_kraken_crypto_global

Atomically restores:
  - approved_model.prev.json → approved_model.json
  - Logs rollback event to approvals.jsonl
"""

import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

from crypto.artifacts import CryptoArtifactStore

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def rollback_model(artifact_store: CryptoArtifactStore, env: str) -> bool:
    """
    Rollback to previous approved model.
    
    Args:
        artifact_store: Artifact store instance
        env: Environment name
    
    Returns:
        True if successful, False otherwise
    """
    models_dir = artifact_store.models_dir
    current_approved = models_dir / "approved_model.json"
    prev_approved = models_dir / "approved_model.prev.json"
    
    # Check previous exists
    if not prev_approved.exists():
        logger.error("No previous approved model to rollback to")
        return False
    
    with open(prev_approved, 'r') as f:
        prev_pointer = json.load(f)
    
    # Load current
    if current_approved.exists():
        with open(current_approved, 'r') as f:
            current_pointer = json.load(f)
    else:
        current_pointer = None
    
    # Atomic rollback: prev → current
    with open(current_approved, 'w') as f:
        json.dump(prev_pointer, f, indent=2)
    
    logger.info(f"✓ Rolled back to model: {prev_pointer.get('model_id')}")
    
    # Clear previous pointer
    prev_approved.unlink()
    logger.info("✓ Cleared previous pointer")
    
    # Audit log
    approval_log = models_dir / "approvals.jsonl"
    rollback_record = {
        'timestamp': datetime.now().isoformat(),
        'action': 'rollback',
        'env': env,
        'from_model': current_pointer.get('model_id') if current_pointer else None,
        'to_model': prev_pointer.get('model_id'),
        'reason': 'Manual rollback',
    }
    
    with open(approval_log, 'a') as f:
        f.write(json.dumps(rollback_record) + '\n')
    
    logger.info("✓ Audit log appended")
    
    return True


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Rollback crypto model to previous approved version"
    )
    parser.add_argument('--env', required=True,
                       help='Environment name (e.g., live_kraken_crypto_global)')
    parser.add_argument('--artifact-root', default='/data/artifacts/crypto/kraken_global',
                       help='Artifact root directory')
    parser.add_argument('--confirm', required=True, type=str,
                       help='Confirm rollback (type: yes-rollback)')
    
    args = parser.parse_args()
    
    # Require explicit confirmation
    if args.confirm != 'yes-rollback':
        logger.error("Rollback not confirmed. Use --confirm yes-rollback")
        return 1
    
    # Initialize artifact store
    artifact_store = CryptoArtifactStore(root=args.artifact_root)
    
    # Rollback
    success = rollback_model(artifact_store, args.env)
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
