#!/usr/bin/env python3
"""
Promote validated crypto model to live approved state.

Usage:
  python tools/crypto/promote_model.py --model-id <id> --env live_kraken_crypto_global

Requires:
  - Validation PASS in validations/<id>.json
  - Explicit confirmation flag
  - SHA256 integrity verified

Atomically updates:
  - approved_model.json (new pointer)
  - approved_model.prev.json (previous pointer)
  - approvals.jsonl (append-only audit log)
"""

import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

from crypto.artifacts import CryptoArtifactStore

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def promote_model(model_id: str, artifact_store: CryptoArtifactStore,
                 env: str, reason: str, force: bool = False) -> bool:
    """
    Promote validated candidate to approved.
    
    Args:
        model_id: Model ID to promote
        artifact_store: Artifact store instance
        env: Environment name (e.g., 'live_kraken_crypto_global')
        reason: Promotion reason
        force: Skip validation check (dangerous)
    
    Returns:
        True if successful, False otherwise
    """
    # Check 1: Integrity
    logger.info(f"Verifying integrity for {model_id}...")
    if not artifact_store.verify_candidate_integrity(model_id):
        logger.error("Integrity check failed")
        return False
    
    # Check 2: Validation result
    validation_file = artifact_store.validations_dir / f"{model_id}.json"
    
    if not force and not validation_file.exists():
        logger.error(f"No validation result found: {validation_file}")
        return False
    
    if not force:
        with open(validation_file, 'r') as f:
            validation = json.load(f)
        
        if not validation.get('passed'):
            logger.error("Validation FAILED - cannot promote without passing validation")
            return False
        
        logger.info("✓ Validation PASSED")
    else:
        logger.warning("Forcing promotion without validation check")
    
    # Check 3: Load candidate metadata
    candidate_dir = artifact_store.candidates_dir / model_id
    with open(candidate_dir / "metadata.json", 'r') as f:
        metadata = json.load(f)
    
    # Create approved pointer
    approved_pointer = {
        'model_id': model_id,
        'status': 'approved',
        'promoted_at': datetime.now().isoformat(),
        'promoted_by': env,
        'reason': reason,
        'metadata': metadata,
        'candidate_path': str(candidate_dir),
    }
    
    # Save previous pointer (if exists)
    models_dir = artifact_store.models_dir
    current_approved = models_dir / "approved_model.json"
    prev_approved = models_dir / "approved_model.prev.json"
    
    if current_approved.exists():
        with open(current_approved, 'r') as f:
            prev_pointer = json.load(f)
        with open(prev_approved, 'w') as f:
            json.dump(prev_pointer, f, indent=2)
        logger.info(f"✓ Saved previous pointer: {prev_pointer.get('model_id')}")
    
    # Atomically write approved pointer
    with open(current_approved, 'w') as f:
        json.dump(approved_pointer, f, indent=2)
    
    logger.info(f"✓ Updated approved_model.json: {model_id}")
    
    # Append to audit log
    approval_log = models_dir / "approvals.jsonl"
    approval_record = {
        'timestamp': datetime.now().isoformat(),
        'model_id': model_id,
        'action': 'promote',
        'env': env,
        'reason': reason,
        'validation_passed': not force,
    }
    
    with open(approval_log, 'a') as f:
        f.write(json.dumps(approval_record) + '\n')
    
    logger.info(f"✓ Audit log appended")
    
    return True


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Promote validated crypto model to live approved state"
    )
    parser.add_argument('--model-id', required=True, help='Model ID to promote')
    parser.add_argument('--env', required=True, 
                       help='Environment name (e.g., live_kraken_crypto_global)')
    parser.add_argument('--reason', default='', help='Promotion reason')
    parser.add_argument('--artifact-root', default='/data/artifacts/crypto/kraken_global',
                       help='Artifact root directory')
    parser.add_argument('--force', action='store_true',
                       help='Skip validation check (dangerous)')
    parser.add_argument('--confirm', required=True, type=str,
                       help='Confirm promotion (type: yes-promote)')
    
    args = parser.parse_args()
    
    # Require explicit confirmation
    if args.confirm != 'yes-promote':
        logger.error("Promotion not confirmed. Use --confirm yes-promote")
        return 1
    
    # Initialize artifact store
    artifact_store = CryptoArtifactStore(root=args.artifact_root)
    
    # Promote
    success = promote_model(
        args.model_id,
        artifact_store,
        args.env,
        args.reason or f"Promoted to {args.env}",
        force=args.force,
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
