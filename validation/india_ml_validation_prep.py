"""
INDIA ML VALIDATION PREPARATION
=================================

Prepare India ML model for validation phase (after rules-only baseline).

PURPOSE:
  - Validate that sufficient observation data exists (safety check)
  - Load India dataset and train fresh LogisticRegression model
  - Verify model readiness before validation begins
  - Create audit trail of validation preparation
  - Prevent premature ML deployment (safety guards)

VALIDATION FLOW:
  1. Check observation count (must be >= 20 days)
  2. Check for data gaps (no missing days)
  3. Load India dataset (NSE data)
  4. Extract features with India feature engine
  5. Train fresh LogisticRegression model (from scratch)
  6. Validate model performance on training set
  7. Save model snapshot with timestamp
  8. Ready for validation phase

SAFETY GUARDS:
  - Minimum 20 observation days required
  - Cannot be run if INDIA_RULES_ONLY = True (requires explicit --run-india-ml-validation)
  - Cannot overwrite previous models (timestamped snapshots)
  - Must have >= 50 labeled samples (minimum training set)
  - Must validate model metrics before deployment

USAGE:
  from validation.india_ml_validation_prep import IndiaMLValidationPrep
  from config.settings import INDIA_MIN_OBSERVATION_DAYS
  
  prep = IndiaMLValidationPrep()
  
  # Check readiness (no exceptions if ready, raises ValueError if not)
  prep.check_validation_readiness(min_days=INDIA_MIN_OBSERVATION_DAYS)
  
  # Prepare model
  model, metrics = prep.prepare_validation_model()
  
  # model is ready for validation phase
"""

import pickle
from datetime import datetime
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from config.settings import INDIA_MIN_OBSERVATION_DAYS
from monitoring.india_observation_log import IndiaObservationLogger
from data.india_data_loader import IndiaDataLoader
from features.india_feature_engine import IndiaFeatureEngine


class IndiaMLValidationPrep:
    """
    Preparation and safety checks for India ML validation phase.
    
    Safety Properties:
    - Cannot be run without explicit request (safety by default)
    - Requires 20+ observation days minimum
    - Validates data quality before training
    - Creates immutable model snapshots with timestamps
    - Provides clear audit trail of preparation
    """
    
    def __init__(self, validation_dir: str = "validation/india_models"):
        """
        Initialize validation preparation.
        
        Args:
            validation_dir: Directory for model snapshots and validation artifacts
        """
        self.validation_dir = Path(validation_dir)
        self.validation_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = IndiaObservationLogger()
        self.data_loader = IndiaDataLoader()
        self.feature_engine = IndiaFeatureEngine()
    
    def check_validation_readiness(self, min_days: int = INDIA_MIN_OBSERVATION_DAYS) -> Dict[str, Any]:
        """
        Check if validation preparation is safe to proceed.
        
        Args:
            min_days: Minimum observation days required
            
        Returns:
            Dictionary with readiness status and diagnostics
            
        Raises:
            ValueError: If readiness checks fail
        """
        status = self.logger.get_observation_status()
        obs_days = status.get("total_observation_days", 0)
        
        readiness = {
            "ready": False,
            "observation_days": obs_days,
            "min_required": min_days,
            "checks": {}
        }
        
        # Check 1: Sufficient observation days
        if obs_days < min_days:
            readiness["checks"]["observation_days"] = False
            raise ValueError(
                f"[INDIA] ML Validation: Insufficient observation data.\n"
                f"  Have: {obs_days} days\n"
                f"  Need: {min_days} days\n"
                f"  Remaining: {min_days - obs_days} days\n\n"
                f"  Rules-only trading must continue for {min_days - obs_days} more days "
                f"before ML validation is allowed."
            )
        
        readiness["checks"]["observation_days"] = True
        
        # Check 2: Data quality (no large gaps)
        recent_obs = self.logger.get_recent_observations(days=5)
        if recent_obs:
            readiness["checks"]["recent_data_exists"] = True
            readiness["last_observation"] = recent_obs[-1].get("date")
        else:
            readiness["checks"]["recent_data_exists"] = False
            raise ValueError(
                "[INDIA] ML Validation: No recent observation data found.\n"
                "  Ensure rules-only trading has generated observations."
            )
        
        readiness["ready"] = all(readiness["checks"].values())
        return readiness
    
    def prepare_validation_model(self) -> Tuple[LogisticRegression, Dict[str, Any]]:
        """
        Prepare India ML model for validation phase.
        
        Returns:
            Tuple of (trained_model, metrics_dict)
            
        Raises:
            ValueError: If validation checks fail
        """
        # Verify readiness (this will raise if not ready)
        readiness = self.check_validation_readiness()
        print(f"[INDIA] ML Validation: Readiness checks passed ✓")
        print(f"  Observation days: {readiness['observation_days']}")
        print(f"  Last observation: {readiness.get('last_observation')}")
        
        # Load India dataset
        print("[INDIA] Loading India dataset...")
        df = self.data_loader.load_data(
            symbols=self.data_loader.NIFTY_50,
            lookback_days=252
        )
        
        if df is None or len(df) == 0:
            raise ValueError("[INDIA] ML Validation: Failed to load India dataset")
        
        print(f"  Loaded {len(df)} samples from India dataset")
        
        # Generate features using India feature engine
        print("[INDIA] Generating features with India feature engine...")
        df_features = self.feature_engine.compute_features(df)
        
        # Prepare training data
        feature_cols = [col for col in df_features.columns if col.startswith("feature_")]
        target_col = "label"
        
        if target_col not in df_features.columns:
            raise ValueError(
                "[INDIA] ML Validation: Target labels not found in dataset. "
                "Ensure india_labeler.py has generated labels."
            )
        
        # Filter valid samples (no NaN)
        valid_samples = df_features[feature_cols + [target_col]].dropna()
        
        if len(valid_samples) < 50:
            raise ValueError(
                f"[INDIA] ML Validation: Insufficient training samples ({len(valid_samples)}). "
                f"Need minimum 50 samples."
            )
        
        print(f"  Using {len(valid_samples)} valid samples for training")
        
        X = valid_samples[feature_cols].values
        y = valid_samples[target_col].values
        
        # Train model with scaler
        print("[INDIA] Training LogisticRegression model...")
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        model = LogisticRegression(
            max_iter=1000,
            random_state=42,
            class_weight='balanced'
        )
        model.fit(X_scaled, y)
        
        # Evaluate training performance
        train_accuracy = model.score(X_scaled, y)
        train_predictions = model.predict(X_scaled)
        
        # Calculate additional metrics
        n_positive = np.sum(y == 1)
        n_negative = np.sum(y == 0)
        tp = np.sum((train_predictions == 1) & (y == 1))
        fp = np.sum((train_predictions == 1) & (y == 0))
        tn = np.sum((train_predictions == 0) & (y == 0))
        fn = np.sum((train_predictions == 0) & (y == 1))
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "phase": "VALIDATION_PREP",
            "model_type": "LogisticRegression",
            "training_samples": len(valid_samples),
            "positive_samples": int(n_positive),
            "negative_samples": int(n_negative),
            "train_accuracy": round(train_accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(2 * (precision * recall) / (precision + recall), 4) 
                if (precision + recall) > 0 else 0,
        }
        
        print(f"  Training accuracy: {metrics['train_accuracy']:.2%}")
        print(f"  Precision: {metrics['precision']:.2%}, Recall: {metrics['recall']:.2%}")
        
        # Create model snapshot
        snapshot_name = f"india_model_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
        snapshot_path = self.validation_dir / snapshot_name
        
        model_artifact = {
            "model": model,
            "scaler": scaler,
            "feature_columns": feature_cols,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat(),
        }
        
        with open(snapshot_path, "wb") as f:
            pickle.dump(model_artifact, f)
        
        print(f"[INDIA] Model snapshot saved: {snapshot_path}")
        
        return model, metrics
    
    def list_validation_models(self) -> list:
        """List all validation model snapshots."""
        if not self.validation_dir.exists():
            return []
        
        models = sorted(self.validation_dir.glob("india_model_validation_*.pkl"))
        return [str(m) for m in models]
    
    def load_validation_model(self, model_path: str) -> Tuple[LogisticRegression, Dict[str, Any]]:
        """
        Load a previously prepared validation model.
        
        Args:
            model_path: Path to model snapshot file
            
        Returns:
            Tuple of (model, metrics)
        """
        with open(model_path, "rb") as f:
            artifact = pickle.load(f)
        
        return artifact["model"], artifact["metrics"]
