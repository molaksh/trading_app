"""
Generate ML-based confidence predictions.

Maps model probabilities to confidence scores (1-5).
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Probability-to-confidence mapping
PROB_TO_CONFIDENCE_MAP = {
    0: 1,      # P < 0.55 → confidence 1
    1: 2,      # 0.55 ≤ P < 0.60 → confidence 2
    2: 3,      # 0.60 ≤ P < 0.65 → confidence 3
    3: 4,      # 0.65 ≤ P < 0.72 → confidence 4
    4: 5,      # P ≥ 0.72 → confidence 5
}

PROBABILITY_THRESHOLDS = [0.55, 0.60, 0.65, 0.72]


def probability_to_confidence(probability: float) -> int:
    """
    Map model probability to confidence score (1-5).

    Args:
        probability: Model probability (0-1)

    Returns:
        Confidence score (1-5)
    """
    if probability < PROBABILITY_THRESHOLDS[0]:
        return 1
    elif probability < PROBABILITY_THRESHOLDS[1]:
        return 2
    elif probability < PROBABILITY_THRESHOLDS[2]:
        return 3
    elif probability < PROBABILITY_THRESHOLDS[3]:
        return 4
    else:
        return 5


def predict_probabilities(model, scaler, X: np.ndarray) -> np.ndarray:
    """
    Generate probability predictions from trained model.

    Args:
        model: Trained LogisticRegression
        scaler: Fitted StandardScaler
        X: Feature matrix

    Returns:
        Array of probabilities (shape: n_samples)
    """
    X_scaled = scaler.transform(X)
    probabilities = model.predict_proba(X_scaled)[:, 1]  # Probability of class 1
    return probabilities


def predict_confidence_scores(
    model,
    scaler,
    X: np.ndarray,
) -> np.ndarray:
    """
    Generate ML-based confidence scores (1-5).

    Args:
        model: Trained LogisticRegression
        scaler: Fitted StandardScaler
        X: Feature matrix

    Returns:
        Array of confidence scores (1-5)
    """
    probabilities = predict_probabilities(model, scaler, X)
    confidences = np.array([probability_to_confidence(p) for p in probabilities])
    return confidences


def predict_with_probabilities(
    model,
    scaler,
    X: np.ndarray,
) -> tuple:
    """
    Generate both probabilities and confidence scores.

    Args:
        model: Trained LogisticRegression
        scaler: Fitted StandardScaler
        X: Feature matrix

    Returns:
        Tuple of (probabilities, confidences)
    """
    probabilities = predict_probabilities(model, scaler, X)
    confidences = predict_confidence_scores(model, scaler, X)
    return probabilities, confidences


def add_ml_predictions_to_dataframe(
    df: pd.DataFrame,
    model,
    scaler,
    feature_columns: list,
    include_confidence: bool = False,
) -> pd.DataFrame:
    """
    Add ML predictions as new columns to DataFrame.

    Args:
        df: Input DataFrame with features
        model: Trained LogisticRegression
        scaler: Fitted StandardScaler
        feature_columns: List of feature column names
        include_confidence: Whether confidence was used as feature

    Returns:
        DataFrame with added 'ml_probability' and 'ml_confidence' columns
    """
    # Build feature matrix
    features = feature_columns.copy()
    if include_confidence and "confidence" not in features:
        features.append("confidence")
    
    X = df[features].values
    
    # Predict
    probabilities, confidences = predict_with_probabilities(model, scaler, X)
    
    # Add to DataFrame
    result = df.copy()
    result["ml_probability"] = probabilities
    result["ml_confidence"] = confidences
    
    return result


def summarize_ml_predictions(
    probabilities: np.ndarray,
    confidences: np.ndarray,
) -> dict:
    """
    Generate summary statistics of ML predictions.

    Args:
        probabilities: Array of probabilities
        confidences: Array of confidence scores

    Returns:
        Dict with summary stats
    """
    summary = {
        "prob_mean": float(np.mean(probabilities)),
        "prob_std": float(np.std(probabilities)),
        "prob_min": float(np.min(probabilities)),
        "prob_max": float(np.max(probabilities)),
        "conf_distribution": {
            int(k): int(v) for k, v in zip(*np.unique(confidences, return_counts=True))
        },
        "conf_mean": float(np.mean(confidences)),
    }
    
    logger.info(f"\nML Prediction Summary:")
    logger.info(f"  Probability mean: {summary['prob_mean']:.3f}")
    logger.info(f"  Probability std:  {summary['prob_std']:.3f}")
    logger.info(f"  Probability range: [{summary['prob_min']:.3f}, {summary['prob_max']:.3f}]")
    logger.info(f"  Confidence distribution: {summary['conf_distribution']}")
    logger.info(f"  Confidence mean: {summary['conf_mean']:.2f}")
    
    return summary
