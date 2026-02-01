#!/usr/bin/env python3
"""
QUICK START: Building and Using the ML Dataset

This is a complete working example showing how to:
1. Build a dataset with your symbols
2. Load and inspect it
3. Prepare for ML training
"""

# ============================================================================
# STEP 1: BUILD DATASET
# ============================================================================

def build_dataset_example():
    """Build dataset for a list of symbols."""
    from dataset.dataset_builder import build_dataset_pipeline
    from universe.symbols import SYMBOLS
    from config.settings import LOOKBACK_DAYS
    
    print("Building ML dataset...")
    filepath = build_dataset_pipeline(SYMBOLS, LOOKBACK_DAYS)
    
    if filepath:
        print(f"✓ Dataset saved to: {filepath}")
        return filepath
    else:
        print("✗ Dataset building failed")
        return None


# ============================================================================
# STEP 2: LOAD AND INSPECT
# ============================================================================

def inspect_dataset_example(filepath):
    """Load and inspect the dataset."""
    import pandas as pd
    
    # Load dataset
    if filepath.endswith('.parquet'):
        df = pd.read_parquet(filepath)
    else:
        df = pd.read_csv(filepath)
    
    print(f"\nDataset Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    
    # Label distribution
    print(f"\nLabel Distribution:")
    label_counts = df['label'].value_counts().sort_index()
    label_pct = (df['label'].value_counts(normalize=True).sort_index() * 100)
    for label, count in label_counts.items():
        print(f"  Label {label}: {count:5d} ({label_pct[label]:5.1f}%)")
    
    # Data quality
    print(f"\nData Quality:")
    print(f"  Missing values: {df.isna().sum().sum()}")
    print(f"  Duplicate rows: {df.duplicated().sum()}")
    
    # Date range
    print(f"\nDate Range:")
    print(f"  From: {df['date'].min()}")
    print(f"  To:   {df['date'].max()}")
    
    # Symbols
    print(f"\nSymbols: {sorted(df['symbol'].unique())}")
    
    # Sample rows
    print(f"\nSample Rows:")
    print(df.head(3)[['date', 'symbol', 'close', 'confidence', 'label']].to_string())
    
    return df


# ============================================================================
# STEP 3: PREPARE FOR ML TRAINING
# ============================================================================

def prepare_for_training_example(df):
    """Prepare dataset for sklearn/XGBoost training."""
    import pandas as pd
    import numpy as np
    
    # Feature columns (exclude date, symbol, and label)
    feature_cols = [
        'close', 'sma_20', 'sma_200', 'dist_20sma', 'dist_200sma',
        'sma20_slope', 'atr_pct', 'vol_ratio', 'pullback_depth', 'confidence'
    ]
    
    X = df[feature_cols].copy()
    y = df['label'].copy()
    
    print(f"\nML-Ready Data:")
    print(f"  X shape: {X.shape} (samples × features)")
    print(f"  y shape: {y.shape} (samples)")
    print(f"  Feature types: {X.dtypes.unique()}")
    print(f"  No NaN: {not X.isna().any().any()}")
    print(f"  Label values: {sorted(y.unique())}")
    
    # Example: train/test split by time (not random!)
    train_size = int(0.8 * len(df))
    
    X_train = X[:train_size]
    X_test = X[train_size:]
    y_train = y[:train_size]
    y_test = y[train_size:]
    
    print(f"\nTime-Series Train/Test Split:")
    print(f"  Train: {len(X_train)} samples ({100*len(X_train)/len(df):.0f}%)")
    print(f"  Test:  {len(X_test)} samples ({100*len(X_test)/len(df):.0f}%)")
    print(f"  Train label dist: {dict(y_train.value_counts().sort_index())}")
    print(f"  Test label dist:  {dict(y_test.value_counts().sort_index())}")
    
    return X_train, X_test, y_train, y_test


# ============================================================================
# STEP 4: TRAIN A SIMPLE MODEL (EXAMPLE)
# ============================================================================

def train_model_example(X_train, X_test, y_train, y_test):
    """Train a simple gradient boosting model."""
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.metrics import roc_auc_score, accuracy_score
    except ImportError:
        print("\nNote: Requires scikit-learn. Install with: pip install scikit-learn")
        return
    
    print("\nTraining Gradient Boosting Model...")
    
    model = GradientBoostingClassifier(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)
    y_proba_test = model.predict_proba(X_test)[:, 1]
    
    train_acc = accuracy_score(y_train, y_pred_train)
    test_acc = accuracy_score(y_test, y_pred_test)
    test_auc = roc_auc_score(y_test, y_proba_test)
    
    print(f"  Train Accuracy: {train_acc:.4f}")
    print(f"  Test Accuracy:  {test_acc:.4f}")
    print(f"  Test AUC:       {test_auc:.4f}")
    
    # Feature importance
    feature_cols = [
        'close', 'sma_20', 'sma_200', 'dist_20sma', 'dist_200sma',
        'sma20_slope', 'atr_pct', 'vol_ratio', 'pullback_depth', 'confidence'
    ]
    importances = model.feature_importances_
    
    print(f"\nTop Features:")
    for feat, imp in sorted(zip(feature_cols, importances), key=lambda x: -x[1])[:5]:
        print(f"  {feat:15s}: {imp:.4f}")
    
    return model


# ============================================================================
# MAIN: RUN COMPLETE PIPELINE
# ============================================================================

if __name__ == '__main__':
    import logging
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s"
    )
    
    print("=" * 80)
    print("ML DATASET QUICK START")
    print("=" * 80)
    
    # Step 1: Build
    filepath = build_dataset_example()
    if not filepath:
        exit(1)
    
    # Step 2: Inspect
    df = inspect_dataset_example(filepath)
    
    # Step 3: Prepare
    X_train, X_test, y_train, y_test = prepare_for_training_example(df)
    
    # Step 4: Train (optional, requires sklearn)
    train_model_example(X_train, X_test, y_train, y_test)
    
    print("\n" + "=" * 80)
    print("✓ Complete ML pipeline ready!")
    print("=" * 80)
