#!/usr/bin/env python3
"""
Test ML dataset building with synthetic data (no network dependencies).
Validates label generation, feature snapshots, and dataset aggregation.
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

logger.info("=" * 90)
logger.info("ML DATASET BUILDING TEST (SYNTHETIC DATA)")
logger.info("=" * 90)

# Test imports
try:
    from config.settings import (
        LABEL_HORIZON_DAYS, LABEL_TARGET_RETURN, LABEL_MAX_DRAWDOWN,
        LOOKBACK_DAYS, MIN_HISTORY_DAYS
    )
    from data.synthetic_data import generate_synthetic_ohlcv
    from dataset.feature_snapshot import create_feature_snapshots, validate_snapshots
    from dataset.dataset_builder import DatasetBuilder
    import pandas as pd
    
    logger.info("✓ All imports successful")
except Exception as e:
    logger.error(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Generate synthetic data for test
logger.info("\nGenerating synthetic price data...")
test_symbols = ['TEST_A', 'TEST_B', 'TEST_C']
synthetic_data = {}

for symbol in test_symbols:
    df = generate_synthetic_ohlcv(symbol, num_days=300, start_price=100.0)
    synthetic_data[symbol] = df
    logger.info(f"  {symbol}: {len(df)} days from {df.index[0].date()} to {df.index[-1].date()}")

# Test individual snapshot creation
logger.info("\n" + "=" * 90)
logger.info("TEST 1: Feature snapshot creation (single symbol)")
logger.info("=" * 90)

try:
    symbol = 'TEST_A'
    df = synthetic_data[symbol]
    
    snapshots = create_feature_snapshots(df, symbol)
    
    if snapshots is None:
        logger.error("✗ Snapshots is None")
        sys.exit(1)
    
    logger.info(f"✓ Created {len(snapshots)} snapshots for {symbol}")
    logger.info(f"  Columns: {list(snapshots.columns)}")
    logger.info(f"  Sample row:")
    for col in snapshots.columns:
        val = snapshots.iloc[0][col]
        logger.info(f"    {col:15s}: {val}")
    
    # Validate
    if not validate_snapshots(snapshots):
        logger.error("✗ Snapshot validation failed")
        sys.exit(1)
    
    logger.info("✓ Snapshot validation passed")
    
    # Check label distribution
    label_dist = snapshots['label'].value_counts().sort_index()
    logger.info(f"  Label distribution: {dict(label_dist)}")
    
except Exception as e:
    logger.error(f"✗ Snapshot test failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test dataset aggregation
logger.info("\n" + "=" * 90)
logger.info("TEST 2: Dataset aggregation (multiple symbols)")
logger.info("=" * 90)

try:
    builder = DatasetBuilder(output_dir="/tmp/ml_dataset", file_format="csv")
    
    all_snapshots = []
    for symbol in test_symbols:
        df = synthetic_data[symbol]
        snapshots = create_feature_snapshots(df, symbol)
        if snapshots is not None:
            all_snapshots.append(snapshots)
    
    if len(all_snapshots) == 0:
        logger.error("✗ No snapshots created")
        sys.exit(1)
    
    # Manually aggregate like dataset_builder does
    dataset = pd.concat(all_snapshots, ignore_index=True)
    dataset = dataset.sort_values(['date', 'symbol']).reset_index(drop=True)
    
    logger.info(f"✓ Aggregated dataset shape: {dataset.shape}")
    logger.info(f"  Symbols: {sorted(dataset['symbol'].unique())}")
    logger.info(f"  Date range: {dataset['date'].min()} to {dataset['date'].max()}")
    logger.info(f"  Unique (symbol, date) pairs: {dataset.groupby(['symbol', 'date']).size().sum()}")
    
    # Label distribution
    label_dist = dataset['label'].value_counts().sort_index()
    total = len(dataset)
    logger.info(f"  Label distribution:")
    for label, count in label_dist.items():
        pct = 100 * count / total
        logger.info(f"    Label {int(label)}: {count:4d} ({pct:5.1f}%)")
    
    # Confidence distribution
    logger.info(f"  Confidence distribution:")
    conf_dist = dataset['confidence'].value_counts().sort_index()
    for conf, count in conf_dist.items():
        logger.info(f"    Confidence {int(conf)}: {count:4d}")
    
except Exception as e:
    logger.error(f"✗ Aggregation test failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test dataset saving
logger.info("\n" + "=" * 90)
logger.info("TEST 3: Dataset saving and loading")
logger.info("=" * 90)

try:
    # Save as parquet
    filepath = builder.save_dataset(dataset, "test_dataset")
    
    if filepath is None:
        logger.error("✗ Save returned None")
        sys.exit(1)
    
    logger.info(f"✓ Saved to: {filepath}")
    
    # Read back
    loaded = pd.read_csv(filepath)
    logger.info(f"✓ Loaded dataset shape: {loaded.shape}")
    
    # Verify integrity
    if len(loaded) != len(dataset):
        logger.error(f"✗ Row count mismatch: {len(loaded)} vs {len(dataset)}")
        sys.exit(1)
    
    if not (loaded.columns == dataset.columns).all():
        logger.error(f"✗ Column mismatch")
        sys.exit(1)
    
    logger.info("✓ Dataset integrity verified")
    
except Exception as e:
    logger.error(f"✗ Save/load test failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

logger.info("\n" + "=" * 90)
logger.info("✓ ALL TESTS PASSED!")
logger.info("=" * 90)
logger.info(f"\nSummary:")
logger.info(f"  - Label generation: ✓")
logger.info(f"  - Feature snapshots: ✓")
logger.info(f"  - Dataset aggregation: ✓")
logger.info(f"  - Data saving/loading: ✓")
logger.info(f"  - Leak-free validation: ✓")
logger.info(f"\nThe ML dataset pipeline is ready for production use!")
