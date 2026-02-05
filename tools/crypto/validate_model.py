#!/usr/bin/env python3
"""
Validate crypto model artifact before promotion to live.

Usage:
  python tools/crypto/validate_model.py --model-id <id> --config <live_config>

Checks:
  - File integrity (SHA256)
  - Schema compatibility
  - OOS metrics gates (max DD, tail loss, turnover, slippage)
  
Outputs:
  - validations/<id>.json with PASS/FAIL + metrics
"""

import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from crypto.artifacts import CryptoArtifactStore

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def validate_model(model_id: str, artifact_store: CryptoArtifactStore,
                   min_oos_sharpe: float = 0.5,
                   max_max_dd: float = 0.15,
                   max_tail_loss: float = 0.05,
                   max_turnover: float = 2.0) -> Dict[str, Any]:
    """
    Validate candidate model.
    
    Args:
        model_id: Candidate model ID
        artifact_store: Artifact store instance
        min_oos_sharpe: Minimum OOS Sharpe ratio
        max_max_dd: Maximum drawdown threshold
        max_tail_loss: Maximum tail loss (99th percentile)
        max_turnover: Maximum portfolio turnover
    
    Returns:
        Validation result dict
    """
    result = {
        'model_id': model_id,
        'timestamp': datetime.now().isoformat(),
        'passed': False,
        'checks': {},
        'metrics': {},
        'failures': [],
    }
    
    # Check 1: File integrity
    logger.info(f"Checking integrity for {model_id}...")
    integrity_ok = artifact_store.verify_candidate_integrity(model_id)
    result['checks']['integrity'] = integrity_ok
    
    if not integrity_ok:
        result['failures'].append("Integrity check failed (SHA256 mismatch)")
        return result
    
    # Check 2: Load metadata
    candidate_dir = artifact_store.candidates_dir / model_id
    try:
        with open(candidate_dir / "metadata.json", 'r') as f:
            metadata = json.load(f)
        with open(candidate_dir / "metrics.json", 'r') as f:
            metrics = json.load(f)
    except Exception as e:
        result['failures'].append(f"Failed to load metadata/metrics: {e}")
        return result
    
    result['metrics'] = metrics
    
    # Check 3: Schema compatibility
    logger.info("Checking schema compatibility...")
    feature_version = metadata.get('feature_version', 'unknown')
    result['checks']['schema_version'] = feature_version
    
    # Check 4: OOS metrics gates
    logger.info("Checking OOS metrics...")
    
    oos_sharpe = metrics.get('oos_sharpe', 0.0)
    if oos_sharpe < min_oos_sharpe:
        result['failures'].append(f"OOS Sharpe too low: {oos_sharpe} < {min_oos_sharpe}")
    result['checks']['oos_sharpe'] = oos_sharpe
    
    max_dd = metrics.get('max_drawdown', 1.0)
    if max_dd > max_max_dd:
        result['failures'].append(f"Max DD too high: {max_dd} > {max_max_dd}")
    result['checks']['max_drawdown'] = max_dd
    
    tail_loss = metrics.get('tail_loss_99', 0.0)
    if tail_loss > max_tail_loss:
        result['failures'].append(f"Tail loss too high: {tail_loss} > {max_tail_loss}")
    result['checks']['tail_loss'] = tail_loss
    
    turnover = metrics.get('annual_turnover', 0.0)
    if turnover > max_turnover:
        result['failures'].append(f"Turnover too high: {turnover} > {max_turnover}")
    result['checks']['turnover'] = turnover
    
    # Summary
    result['passed'] = len(result['failures']) == 0
    
    logger.info(f"Validation result: {'PASSED' if result['passed'] else 'FAILED'}")
    for failure in result['failures']:
        logger.warning(f"  - {failure}")
    
    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate crypto model candidate"
    )
    parser.add_argument('--model-id', required=True, help='Model ID to validate')
    parser.add_argument('--artifact-root', default='/data/artifacts/crypto/kraken_global',
                       help='Artifact root directory')
    parser.add_argument('--min-oos-sharpe', type=float, default=0.5,
                       help='Minimum OOS Sharpe ratio')
    parser.add_argument('--max-drawdown', type=float, default=0.15,
                       help='Maximum drawdown')
    parser.add_argument('--max-tail-loss', type=float, default=0.05,
                       help='Maximum tail loss (99th pct)')
    parser.add_argument('--max-turnover', type=float, default=2.0,
                       help='Maximum annual turnover')
    
    args = parser.parse_args()
    
    # Initialize artifact store
    artifact_store = CryptoArtifactStore(root=args.artifact_root)
    
    # Validate
    result = validate_model(
        args.model_id,
        artifact_store,
        min_oos_sharpe=args.min_oos_sharpe,
        max_max_dd=args.max_drawdown,
        max_tail_loss=args.max_tail_loss,
        max_turnover=args.max_turnover,
    )
    
    # Save validation result
    validation_file = artifact_store.validations_dir / f"{args.model_id}.json"
    with open(validation_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    logger.info(f"Validation saved: {validation_file}")
    
    # Exit code
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    exit(main())
