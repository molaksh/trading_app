"""
Feature Drift Monitor (Phase H)

Detects when input features deviate significantly from historical baseline.
Used to identify when trading conditions have changed.
"""

import logging
from typing import Dict, List, Optional, Tuple
from collections import deque

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class FeatureDriftMonitor:
    """
    Monitor feature distributions for drift.
    
    Compares recent feature statistics to long-term baseline.
    Flags features that deviate significantly.
    """
    
    def __init__(
        self,
        feature_names: List[str],
        std_dev_threshold: float = 3.0,    # Flag if >3 std devs away
        lookback_window: int = 60,         # Recent window for comparison (days)
        baseline_window: int = 250,        # Long-term baseline (trading days)
        min_samples: int = 20,             # Min samples before checking
    ):
        """
        Initialize feature drift monitor.
        
        Args:
            feature_names: List of feature names to monitor
            std_dev_threshold: Z-score threshold for flagging drift
            lookback_window: Recent window size (days)
            baseline_window: Baseline window size (days/samples)
            min_samples: Minimum samples before checking
        """
        self.feature_names = feature_names
        self.std_dev_threshold = std_dev_threshold
        self.lookback_window = lookback_window
        self.baseline_window = baseline_window
        self.min_samples = min_samples
        
        # Historical feature values
        # {feature_name: deque of values}
        self.feature_history = {name: deque(maxlen=baseline_window) for name in feature_names}
        
        # Baseline statistics (computed from long-term data)
        self.baseline_stats = {}  # {feature_name: {mean, std}}
        
        # Recent statistics
        self.recent_stats = {}
        
        # Alerts and statistics
        self.alerts = []
        self.drifts_detected = 0
    
    def add_features(self, feature_dict: Dict[str, float], date: pd.Timestamp):
        """
        Add feature values for a date.
        
        Args:
            feature_dict: {feature_name: value}
            date: Date of features
        """
        for name, value in feature_dict.items():
            if name in self.feature_history:
                self.feature_history[name].append(value)
    
    def compute_baseline_stats(self):
        """Compute baseline statistics from historical data."""
        self.baseline_stats = {}
        
        for name in self.feature_names:
            history = list(self.feature_history[name])
            
            if len(history) < self.min_samples:
                continue
            
            self.baseline_stats[name] = {
                "mean": np.mean(history),
                "std": np.std(history),
                "min": np.min(history),
                "max": np.max(history),
            }
    
    def compute_recent_stats(self):
        """Compute statistics for recent window."""
        self.recent_stats = {}
        
        for name in self.feature_names:
            history = list(self.feature_history[name])
            
            if len(history) < self.lookback_window:
                recent = history
            else:
                recent = history[-self.lookback_window:]
            
            if len(recent) == 0:
                continue
            
            self.recent_stats[name] = {
                "mean": np.mean(recent),
                "std": np.std(recent),
                "min": np.min(recent),
                "max": np.max(recent),
            }
    
    def detect_drift(self) -> Dict:
        """
        Detect feature drift.
        
        Returns:
            Dict with drift flags and details
        """
        if len(self.baseline_stats) == 0:
            self.compute_baseline_stats()
        
        self.compute_recent_stats()
        
        drifts = []
        
        for name in self.feature_names:
            if name not in self.baseline_stats or name not in self.recent_stats:
                continue
            
            baseline = self.baseline_stats[name]
            recent = self.recent_stats[name]
            
            if baseline["std"] == 0:
                continue  # Skip constant features
            
            # Calculate Z-score for recent mean vs baseline
            z_score = abs(recent["mean"] - baseline["mean"]) / baseline["std"]
            
            if z_score > self.std_dev_threshold:
                drift_info = {
                    "feature": name,
                    "z_score": z_score,
                    "baseline_mean": baseline["mean"],
                    "baseline_std": baseline["std"],
                    "recent_mean": recent["mean"],
                    "recent_std": recent["std"],
                }
                drifts.append(drift_info)
                
                reason = (
                    f"Feature drift: {name} | Z-score: {z_score:.2f} | "
                    f"Baseline: {baseline['mean']:.4f} → Recent: {recent['mean']:.4f}"
                )
                self.drifts_detected += 1
                self.alerts.append(("FEATURE_DRIFT", reason))
                logger.warning(f"DRIFT: {reason}")
        
        return {
            "has_drift": len(drifts) > 0,
            "drifts": drifts,
            "baseline_stats": self.baseline_stats,
            "recent_stats": self.recent_stats,
        }
    
    def get_summary(self) -> Dict:
        """Get monitoring summary."""
        return {
            "drifts_detected": self.drifts_detected,
            "features_monitored": len(self.feature_names),
            "baseline_stats": self.baseline_stats,
            "recent_stats": self.recent_stats,
        }
