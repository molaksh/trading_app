#!/usr/bin/env python3
"""
Integration test: Verify all ML dataset components work together.
Tests imports, configuration, and complete pipeline.
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger(__name__)

print("=" * 90)
print("ML DATASET - INTEGRATION TEST")
print("=" * 90)

# Test 1: Verify configuration
print("\n[1/5] Testing configuration...")
try:
    from config.settings import (
        LABEL_HORIZON_DAYS, LABEL_TARGET_RETURN, LABEL_MAX_DRAWDOWN,
        DATASET_OUTPUT_DIR, DATASET_FILE_FORMAT,
        LOOKBACK_DAYS, MIN_HISTORY_DAYS
    )
    assert LABEL_HORIZON_DAYS == 5, f"Expected 5, got {LABEL_HORIZON_DAYS}"
    assert LABEL_TARGET_RETURN == 0.02, f"Expected 0.02, got {LABEL_TARGET_RETURN}"
    assert LABEL_MAX_DRAWDOWN == -0.01, f"Expected -0.01, got {LABEL_MAX_DRAWDOWN}"
    logger.info("✓ Configuration loaded correctly")
    logger.info(f"  Horizon: {LABEL_HORIZON_DAYS} days")
    logger.info(f"  Target: {LABEL_TARGET_RETURN*100:+.0f}% / Drawdown: {LABEL_MAX_DRAWDOWN*100:.0f}%")
except Exception as e:
    logger.error(f"✗ Configuration test failed: {e}")
    sys.exit(1)

# Test 2: Verify module imports
print("\n[2/5] Testing module imports...")
try:
    from dataset.label_generator import compute_label, compute_labels_for_symbol
    from dataset.feature_snapshot import create_feature_snapshots, validate_snapshots
    from dataset.dataset_builder import DatasetBuilder, build_dataset_pipeline
    logger.info("✓ All dataset modules imported successfully")
except Exception as e:
    logger.error(f"✗ Import test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Verify synthetic data generation
print("\n[3/5] Testing synthetic data generation...")
try:
    from data.synthetic_data import generate_synthetic_ohlcv
    import pandas as pd
    
    df = generate_synthetic_ohlcv("TEST", num_days=300)
    assert len(df) == 300, f"Expected 300 rows, got {len(df)}"
    assert all(col in df.columns for col in ['Open', 'High', 'Low', 'Close', 'Volume'])
    assert df.index.is_monotonic_increasing, "Index not sorted"
    logger.info("✓ Synthetic data generation works")
    logger.info(f"  Generated {len(df)} days of OHLCV data")
except Exception as e:
    logger.error(f"✗ Synthetic data test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Verify complete pipeline (with synthetic data)
print("\n[4/5] Testing complete pipeline...")
try:
    # Generate test data
    test_symbols = ['SYN_A', 'SYN_B']
    test_data = {}
    for symbol in test_symbols:
        test_data[symbol] = generate_synthetic_ohlcv(symbol, num_days=300)
    
    # Build snapshots
    all_snapshots = []
    for symbol in test_symbols:
        df = test_data[symbol]
        snapshots = create_feature_snapshots(df, symbol)
        if snapshots is not None:
            assert validate_snapshots(snapshots), f"Validation failed for {symbol}"
            all_snapshots.append(snapshots)
    
    if not all_snapshots:
        raise ValueError("No snapshots created")
    
    # Aggregate
    import pandas as pd
    dataset = pd.concat(all_snapshots, ignore_index=True)
    dataset = dataset.sort_values(['date', 'symbol']).reset_index(drop=True)
    
    # Verify
    assert len(dataset) > 0, "Dataset is empty"
    assert dataset['label'].isin([0, 1]).all(), "Invalid label values"
    assert dataset['confidence'].isin(range(1, 6)).all(), "Invalid confidence values"
    assert not dataset.isna().any().any(), "Dataset contains NaN"
    
    logger.info("✓ Complete pipeline works")
    logger.info(f"  Total snapshots: {len(dataset)}")
    logger.info(f"  Symbols: {dataset['symbol'].nunique()}")
    label_counts = dataset['label'].value_counts().sort_index()
    logger.info(f"  Label distribution: 0={label_counts.get(0, 0)} 1={label_counts.get(1, 0)}")
    
except Exception as e:
    logger.error(f"✗ Pipeline test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Verify main.py integration
print("\n[5/5] Testing main.py integration...")
try:
    # Check that BUILD_DATASET flag exists
    import main
    assert hasattr(main, 'BUILD_DATASET'), "BUILD_DATASET flag not found in main.py"
    assert main.BUILD_DATASET == False, "BUILD_DATASET should default to False"
    logger.info("✓ main.py integration correct")
    logger.info(f"  BUILD_DATASET flag: {main.BUILD_DATASET}")
    
    # Check that SYMBOLS and LOOKBACK_DAYS are available
    from universe.symbols import SYMBOLS
    from config.settings import LOOKBACK_DAYS
    logger.info(f"  SYMBOLS available: {len(SYMBOLS)} symbols")
    logger.info(f"  LOOKBACK_DAYS: {LOOKBACK_DAYS}")
    
except Exception as e:
    logger.error(f"✗ main.py integration test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Summary
print("\n" + "=" * 90)
logger.info("✓ ALL INTEGRATION TESTS PASSED")
print("=" * 90)
print("\nSystem is ready for ML dataset building!")
print("\nNext steps:")
print("  1. Set BUILD_DATASET = True in main.py")
print("  2. Run: python3 main.py")
print("  3. Or use: python3 quick_start_ml_dataset.py")
print("\nDocumentation:")
print("  - ML_DATASET_README.md: Complete technical reference")
print("  - ML_DATASET_DELIVERY.md: Implementation summary")
print("  - quick_start_ml_dataset.py: Runnable example")
