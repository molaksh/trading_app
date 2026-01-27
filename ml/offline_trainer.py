"""
Offline ML trainer for risk-filtering model.

Trains AFTER market close using completed trades only.
Output: Binary classifier predicting "bad" trades (negative expectancy/high MAE).

SAFETY CONSTRAINTS:
- No training during market hours
- Features frozen at entry time
- Target label from exit outcome (no future leakage)
- Simple, interpretable models (logistic regression, XGBoost)
"""

import json
import logging
import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


class OfflineTrainer:
    """Train risk-filter model offline (after market close only)."""

    def __init__(self, model_dir: Path, dataset_builder):
        """
        Initialize trainer.
        
        Args:
            model_dir: Directory to save model artifacts
            dataset_builder: DatasetBuilder instance with dataset
        """
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_builder = dataset_builder
        
        self.model = None
        self.scaler = None
        self.feature_names = None
        self.model_id = None

    def train(
        self,
        mae_threshold: float = 0.03,
        test_size: float = 0.2,
        force: bool = False,
    ) -> Optional[Dict]:
        """Train risk-filter model.
        
        SAFETY: Only runs if dataset has >= 20 closed trades.
        
        Args:
            mae_threshold: MAE threshold for 'bad' label
            test_size: Train/test split ratio
            force: Force training even if dataset is small (for testing)
        
        Returns:
            Model metrics dict or None if training skipped
        """
        logger.info("=" * 80)
        logger.info("OFFLINE MODEL TRAINING")
        logger.info("=" * 80)
        
        # Load dataset
        df = self.dataset_builder.to_dataframe()
        
        if df.empty:
            logger.warning("Dataset is empty. Skipping training.")
            return None
        
        if len(df) < 20 and not force:
            logger.warning(f"Dataset too small ({len(df)} rows). Need >= 20 for training.")
            logger.info("Will train once dataset reaches 20 closed trades.")
            return None
        
        logger.info(f"Training on {len(df)} closed trades")
        
        # Create binary label: 0 = good trade, 1 = bad trade
        df["is_bad"] = df.apply(
            lambda row: 1 if row["realized_pnl_pct"] < 0 or abs(row["mae_pct"]) > mae_threshold else 0,
            axis=1
        )
        
        bad_count = (df["is_bad"] == 1).sum()
        logger.info(f"Bad trades (label=1): {bad_count} / {len(df)} ({100*bad_count/len(df):.1f}%)")
        
        # Build feature matrix from rule_features
        feature_list = self._extract_feature_names(df)
        logger.info(f"Features: {feature_list}")
        
        X, y = self._build_feature_matrix(df, feature_list)
        
        if X.shape[0] < 5:
            logger.warning("Too few samples after feature extraction.")
            return None
        
        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y if len(np.unique(y)) > 1 else None
        )
        
        logger.info(f"Train: {len(X_train)} | Test: {len(X_test)}")
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train logistic regression (simple, interpretable)
        self.model = LogisticRegression(max_iter=1000, random_state=42)
        self.model.fit(X_train_scaled, y_train)
        self.feature_names = feature_list
        
        # Evaluate
        train_score = self.model.score(X_train_scaled, y_train)
        test_score = self.model.score(X_test_scaled, y_test)
        
        logger.info(f"Train accuracy: {train_score:.3f}")
        logger.info(f"Test accuracy: {test_score:.3f}")
        
        # Log feature importance (coefficients)
        self._log_feature_importance(X_train_scaled, feature_list)
        
        # Create model ID
        self.model_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save model
        self._save_model(X_train, X_test, y_train, y_test, train_score, test_score)
        
        logger.info("=" * 80)
        
        return {
            "model_id": self.model_id,
            "train_accuracy": float(train_score),
            "test_accuracy": float(test_score),
            "n_features": len(feature_list),
            "n_trades": len(df),
            "bad_trade_pct": 100 * bad_count / len(df),
        }

    def _extract_feature_names(self, df: pd.DataFrame) -> list:
        """Extract unique feature names from rule_features."""
        all_features = set()
        for features_dict in df["rule_features"]:
            if isinstance(features_dict, dict):
                all_features.update(features_dict.keys())
        return sorted(list(all_features))

    def _build_feature_matrix(self, df: pd.DataFrame, feature_names: list) -> Tuple[np.ndarray, np.ndarray]:
        """Build feature matrix from rule_features."""
        X = []
        for features_dict in df["rule_features"]:
            if isinstance(features_dict, dict):
                row = [features_dict.get(name, 0.0) for name in feature_names]
            else:
                row = [0.0] * len(feature_names)
            X.append(row)
        
        X = np.array(X, dtype=float)
        y = df["is_bad"].values
        
        return X, y

    def _log_feature_importance(self, X_scaled: np.ndarray, feature_names: list) -> None:
        """Log model coefficients (feature importance)."""
        if self.model is None or not hasattr(self.model, "coef_"):
            return
        
        coefs = self.model.coef_[0]
        importance = sorted(
            zip(feature_names, coefs),
            key=lambda x: abs(x[1]),
            reverse=True
        )
        
        logger.info("Top features (by coefficient magnitude):")
        for name, coef in importance[:5]:
            logger.info(f"  {name}: {coef:+.4f}")

    def _save_model(
        self,
        X_train: np.ndarray,
        X_test: np.ndarray,
        y_train: np.ndarray,
        y_test: np.ndarray,
        train_score: float,
        test_score: float,
    ) -> None:
        """Save model artifacts to disk."""
        model_dir = self.model_dir / self.model_id
        model_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model pickle
        model_file = model_dir / "model.pkl"
        with open(model_file, "wb") as f:
            pickle.dump(self.model, f)
        
        # Save scaler
        scaler_file = model_dir / "scaler.pkl"
        with open(scaler_file, "wb") as f:
            pickle.dump(self.scaler, f)
        
        # Save metadata
        metadata = {
            "model_id": self.model_id,
            "training_timestamp": datetime.now().isoformat(),
            "features": self.feature_names,
            "train_accuracy": float(train_score),
            "test_accuracy": float(test_score),
            "n_train_samples": len(X_train),
            "n_test_samples": len(X_test),
            "model_type": "LogisticRegression",
        }
        
        metadata_file = model_dir / "metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Saved model: {model_dir}")

    def load_model(self, model_id: str) -> bool:
        """Load trained model from disk."""
        model_dir = self.model_dir / model_id
        
        try:
            # Load model
            with open(model_dir / "model.pkl", "rb") as f:
                self.model = pickle.load(f)
            
            # Load scaler
            with open(model_dir / "scaler.pkl", "rb") as f:
                self.scaler = pickle.load(f)
            
            # Load metadata
            with open(model_dir / "metadata.json") as f:
                metadata = json.load(f)
            
            self.feature_names = metadata["features"]
            self.model_id = model_id
            
            logger.info(f"Loaded model: {model_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return False

    def predict_risk(self, features_dict: Dict[str, float]) -> Optional[float]:
        """Predict probability that a trade is 'bad' (risk score).
        
        TRADING-TIME USAGE: Call with signal features to get risk score.
        Score in [0, 1]: 0 = low risk, 1 = high risk.
        """
        if self.model is None or self.scaler is None:
            return None
        
        try:
            # Build feature vector
            X = np.array([[features_dict.get(name, 0.0) for name in self.feature_names]], dtype=float)
            X_scaled = self.scaler.transform(X)
            
            # Get probability of "bad" class
            proba = self.model.predict_proba(X_scaled)[0][1]
            return float(proba)
        except Exception as e:
            logger.warning(f"Could not predict risk: {e}")
            return None
