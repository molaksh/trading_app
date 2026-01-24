#!/usr/bin/env python3
"""
Quick test of ML dataset building functionality.
Tests label generation, feature snapshots, and dataset aggregation without full main.py.
"""

import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Test imports
try:
    from config.settings import (
        LABEL_HORIZON_DAYS, LABEL_TARGET_RETURN, LABEL_MAX_DRAWDOWN,
        LOOKBACK_DAYS, MIN_HISTORY_DAYS
    )
    logger.info("✓ Config imports successful")
except Exception as e:
    logger.error(f"✗ Config import failed: {e}")
    sys.exit(1)

try:
    from dataset.label_generator import compute_label, compute_labels_for_symbol
    logger.info("✓ Label generator imports successful")
except Exception as e:
    logger.error(f"✗ Label generator import failed: {e}")
    sys.exit(1)

try:
    from dataset.feature_snapshot import create_feature_snapshots, validate_snapshots
    logger.info("✓ Feature snapshot imports successful")
except Exception as e:
    logger.error(f"✗ Feature snapshot import failed: {e}")
    sys.exit(1)

try:
    from dataset.dataset_builder import DatasetBuilder, build_dataset_pipeline
    logger.info("✓ Dataset builder imports successful")
except Exception as e:
    logger.error(f"✗ Dataset builder import failed: {e}")
    sys.exit(1)

# Test with a small set of symbols
logger.info("\n" + "=" * 90)
logger.info("Testing dataset pipeline with sample symbols")
logger.info("=" * 90)

test_symbols = ['AAPL', 'MSFT', 'GOOGL']  # Small test set

try:
    filepath = build_dataset_pipeline(test_symbols, lookback_days=LOOKBACK_DAYS)
    
    if filepath:
        # Read back and verify
        import pandas as pd
        if filepath.endswith('.parquet'):
            dataset = pd.read_parquet(filepath)
        else:
            dataset = pd.read_csv(filepath)
        
        logger.info(f"\n✓ Dataset loaded successfully")
        logger.info(f"  Shape: {dataset.shape}")
        logger.info(f"  Columns: {list(dataset.columns)}")
        logger.info(f"  Sample row:\n{dataset.iloc[0].to_string()}")
        
        # Verify no NaN
        if dataset.isna().any().any():
            logger.warning("  ⚠ Dataset contains NaN values")
        else:
            logger.info("  ✓ No NaN values")
        
        # Verify label distribution
        logger.info(f"  Label distribution: {dict(dataset['label'].value_counts().sort_index())}")
        
    else:
        logger.error("✗ Dataset building returned None")
        sys.exit(1)

except Exception as e:
    logger.error(f"✗ Dataset building failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

logger.info("\n" + "=" * 90)
logger.info("✓ All tests passed!")
logger.info("=" * 90)
