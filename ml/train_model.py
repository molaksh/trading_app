"""
Train LogisticRegression model on historical dataset.

Time-safe evaluation: train on first 70% of data, test on remaining 30%.
No shuffling to preserve temporal order.
"""

import logging
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from pathlib import Path

logger = logging.getLogger(__name__)

# Feature columns to use (numerical only)
FEATURE_COLUMNS = [
    "dist_20sma",
    "dist_200sma",
    "sma20_slope",
    "atr_pct",
    "vol_ratio",
    "pullback_depth",
]


def load_dataset(dataset_path: str) -> pd.DataFrame:
    """
    Load ML-ready dataset from CSV or Parquet.

    Args:
        dataset_path: Path to dataset file

    Returns:
        DataFrame with features and labels
    """
    path = Path(dataset_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")
    
    if path.suffix == ".csv":
        df = pd.read_csv(dataset_path)
    elif path.suffix == ".parquet":
        df = pd.read_parquet(dataset_path)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")
    
    # Ensure date column is parsed as datetime
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    
    return df


def prepare_features(df: pd.DataFrame, include_confidence: bool = False) -> tuple:
    """
    Prepare feature matrix and labels for training.

    Validates all required features exist and no NaN values.

    Args:
        df: DataFrame with features and labels
        include_confidence: If True, add rule-based confidence as a feature

    Returns:
        Tuple of (X, y) where X is feature matrix, y is label array
    """
    # Check required columns
    required_cols = FEATURE_COLUMNS + ["label"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Build feature list
    features = FEATURE_COLUMNS.copy()
    if include_confidence and "confidence" in df.columns:
        features.append("confidence")
    
    # Extract features and labels
    X = df[features].copy()
    y = df["label"].copy()
    
    # Check for NaN values
    if X.isna().any().any():
        logger.warning(f"Found NaN values in features. Removing {X.isna().any(axis=1).sum()} rows.")
        valid_idx = ~X.isna().any(axis=1)
        X = X[valid_idx]
        y = y[valid_idx]
    
    if y.isna().any():
        logger.warning(f"Found NaN values in labels. Removing {y.isna().sum()} rows.")
        valid_idx = ~y.isna()
        X = X[valid_idx]
        y = y[valid_idx]
    
    # Validate labels
    unique_labels = set(y.unique())
    if not unique_labels.issubset({0, 1}):
        raise ValueError(f"Labels must be binary (0/1). Found: {unique_labels}")
    
    logger.info(f"Prepared features: {features}")
    logger.info(f"Feature matrix shape: {X.shape}")
    logger.info(f"Label distribution: {(y.value_counts() / len(y) * 100).round(1).to_dict()}")
    
    return X.values, y.values, features


def time_based_split(X: np.ndarray, y: np.ndarray, train_ratio: float = 0.7) -> tuple:
    """
    Split data into train/test using temporal order (no shuffling).

    Args:
        X: Feature matrix (samples × features)
        y: Labels
        train_ratio: Fraction for training (default 0.7)

    Returns:
        Tuple of (X_train, X_test, y_train, y_test)
    """
    split_idx = int(len(X) * train_ratio)
    
    X_train = X[:split_idx]
    X_test = X[split_idx:]
    y_train = y[:split_idx]
    y_test = y[split_idx:]
    
    logger.info(f"Train set: {len(X_train)} samples ({train_ratio*100:.0f}%)")
    logger.info(f"Test set: {len(X_test)} samples ({(1-train_ratio)*100:.0f}%)")
    logger.info(f"Train label distribution: {np.bincount(y_train.astype(int))}")
    logger.info(f"Test label distribution: {np.bincount(y_test.astype(int))}")
    
    return X_train, X_test, y_train, y_test


def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    include_confidence: bool = False,
) -> tuple:
    """
    Train LogisticRegression model with feature standardization.

    Args:
        X_train: Training feature matrix
        y_train: Training labels
        include_confidence: Whether confidence was included as feature

    Returns:
        Tuple of (model, scaler, feature_names)
    """
    logger.info("\n" + "=" * 80)
    logger.info("MODEL TRAINING")
    logger.info("=" * 80)
    
    # Standardize features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    
    # Train LogisticRegression
    model = LogisticRegression(
        max_iter=1000,
        random_state=42,
        solver="lbfgs",
        class_weight="balanced",  # Handle imbalanced data
    )
    model.fit(X_train_scaled, y_train)
    
    # Log model info
    train_accuracy = model.score(X_train_scaled, y_train)
    logger.info(f"LogisticRegression trained successfully")
    logger.info(f"Training accuracy: {train_accuracy:.2%}")
    logger.info(f"Model coefficients: {dict(zip(FEATURE_COLUMNS, model.coef_[0]))}")
    
    return model, scaler, FEATURE_COLUMNS + (["confidence"] if include_confidence else [])


def evaluate_model(
    model,
    scaler,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> dict:
    """
    Evaluate model on test set.

    Args:
        model: Trained LogisticRegression
        scaler: Fitted StandardScaler
        X_test: Test feature matrix
        y_test: Test labels

    Returns:
        Dict with metrics
    """
    X_test_scaled = scaler.transform(X_test)
    
    accuracy = model.score(X_test_scaled, y_test)
    y_pred = model.predict(X_test_scaled)
    
    # Compute per-class metrics
    tp = np.sum((y_pred == 1) & (y_test == 1))
    fp = np.sum((y_pred == 1) & (y_test == 0))
    tn = np.sum((y_pred == 0) & (y_test == 0))
    fn = np.sum((y_pred == 0) & (y_test == 1))
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    metrics = {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }
    
    logger.info(f"\nTest set evaluation:")
    logger.info(f"  Accuracy:  {accuracy:.2%}")
    logger.info(f"  Precision: {precision:.2%}")
    logger.info(f"  Recall:    {recall:.2%}")
    logger.info(f"  F1 Score:  {f1:.2%}")
    
    return metrics


def train_and_evaluate(
    dataset_path: str,
    include_confidence: bool = False,
    train_ratio: float = 0.7,
) -> dict:
    """
    Complete pipeline: load → prepare → split → train → evaluate.

    Args:
        dataset_path: Path to ML dataset
        include_confidence: Include rule-based confidence as feature
        train_ratio: Train/test split ratio

    Returns:
        Dict with model, scaler, metrics, and test data
    """
    logger.info("\n" + "=" * 80)
    logger.info("ML MODEL TRAINING PIPELINE")
    logger.info("=" * 80)
    
    # Load dataset
    logger.info(f"\nLoading dataset from: {dataset_path}")
    df = load_dataset(dataset_path)
    logger.info(f"Dataset shape: {df.shape}")
    
    # Prepare features
    X, y, features = prepare_features(df, include_confidence=include_confidence)
    
    # Time-based split
    X_train, X_test, y_train, y_test = time_based_split(X, y, train_ratio=train_ratio)
    
    # Train model
    model, scaler, feature_names = train_model(X_train, y_train, include_confidence)
    
    # Evaluate
    metrics = evaluate_model(model, scaler, X_test, y_test)
    
    return {
        "model": model,
        "scaler": scaler,
        "features": feature_names,
        "metrics": metrics,
        "X_test": X_test,
        "y_test": y_test,
        "dataset": df,
    }
