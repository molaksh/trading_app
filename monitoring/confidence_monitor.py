"""
Confidence Distribution Monitor (Phase H)

Tracks the distribution of confidence scores and detects anomalies:
- Confidence inflation (too many high-confidence signals)
- Confidence collapse (too few high-confidence signals)
- Sudden distribution shifts

Used for monitoring system health, not for signal filtering.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import deque

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class ConfidenceDistributionMonitor:
    """
    Monitor confidence score distribution for anomalies.
    
    Tracks rolling window of confidence scores and compares to baseline.
    """
    
    def __init__(
        self,
        confidence_inflation_pct: float = 0.30,  # Flag if >30% are confidence 5
        confidence_collapse_pct: float = 0.10,   # Flag if <10% are confidence 4-5
        min_window_size: int = 20,               # Min signals before checking
        lookback_days: int = 60,                 # Baseline window (days of data)
    ):
        """
        Initialize confidence distribution monitor.
        
        Args:
            confidence_inflation_pct: Alert if high-confidence % exceeds this
            confidence_collapse_pct: Alert if high-confidence % below this
            min_window_size: Minimum signals before checking anomalies
            lookback_days: Days of historical data for baseline
        """
        self.confidence_inflation_pct = confidence_inflation_pct
        self.confidence_collapse_pct = confidence_collapse_pct
        self.min_window_size = min_window_size
        self.lookback_days = lookback_days
        
        # Rolling window of confidence scores
        self.confidence_scores = deque(maxlen=1000)  # Max 1000 signals
        self.score_dates = deque(maxlen=1000)
        
        # Daily snapshots for trend analysis
        self.daily_snapshots = {}  # {date: {1: count, 2: count, ...}}
        
        # Alerts and statistics
        self.alerts = []
        self.anomalies_detected = 0
    
    def add_signal(
        self,
        confidence: int,
        signal_date: pd.Timestamp,
    ):
        """Add a signal with its confidence score."""
        if not 1 <= confidence <= 5:
            logger.warning(f"Invalid confidence {confidence}, skipping")
            return
        
        self.confidence_scores.append(confidence)
        self.score_dates.append(signal_date)
    
    def update_daily_snapshot(self, date: pd.Timestamp) -> Dict[int, float]:
        """
        Update daily snapshot with confidence distribution.
        
        Returns:
            Dict of {confidence_level: percentage}
        """
        if len(self.confidence_scores) == 0:
            return {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        
        # Count signals by confidence level
        counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for score in self.confidence_scores:
            counts[score] += 1
        
        total = len(self.confidence_scores)
        percentages = {k: (v / total * 100) for k, v in counts.items()}
        
        # Store snapshot
        self.daily_snapshots[date] = percentages
        
        return percentages
    
    def check_confidence_inflation(self, current_pcts: Dict[int, float]) -> Tuple[bool, Optional[str]]:
        """
        Check if confidence is inflated (too many high-confidence signals).
        
        Returns:
            (is_anomaly, reason)
        """
        if len(self.confidence_scores) < self.min_window_size:
            return False, None
        
        # High confidence = 4 or 5
        high_conf_pct = current_pcts.get(4, 0) + current_pcts.get(5, 0)
        
        if high_conf_pct > self.confidence_inflation_pct * 100:
            reason = (
                f"Confidence inflation detected: {high_conf_pct:.1f}% are "
                f"confidence 4-5 (threshold: {self.confidence_inflation_pct*100:.1f}%)"
            )
            self.anomalies_detected += 1
            self.alerts.append(("CONFIDENCE_INFLATION", reason))
            return True, reason
        
        return False, None
    
    def check_confidence_collapse(self, current_pcts: Dict[int, float]) -> Tuple[bool, Optional[str]]:
        """
        Check if confidence has collapsed (too few high-confidence signals).
        
        Returns:
            (is_anomaly, reason)
        """
        if len(self.confidence_scores) < self.min_window_size:
            return False, None
        
        # High confidence = 4 or 5
        high_conf_pct = current_pcts.get(4, 0) + current_pcts.get(5, 0)
        
        if high_conf_pct < self.confidence_collapse_pct * 100:
            reason = (
                f"Confidence collapse detected: only {high_conf_pct:.1f}% are "
                f"confidence 4-5 (threshold: {self.confidence_collapse_pct*100:.1f}%)"
            )
            self.anomalies_detected += 1
            self.alerts.append(("CONFIDENCE_COLLAPSE", reason))
            return True, reason
        
        return False, None
    
    def check_for_anomalies(self, current_date: pd.Timestamp) -> Dict:
        """
        Check all confidence anomalies.
        
        Returns:
            Dict with anomaly flags and details
        """
        if len(self.confidence_scores) == 0:
            return {"has_anomalies": False, "anomalies": []}
        
        # Get current distribution
        current_pcts = self.update_daily_snapshot(current_date)
        
        anomalies = []
        
        # Check inflation
        is_inflation, reason = self.check_confidence_inflation(current_pcts)
        if is_inflation:
            anomalies.append({"type": "CONFIDENCE_INFLATION", "reason": reason})
            logger.warning(f"ANOMALY: {reason}")
        
        # Check collapse
        is_collapse, reason = self.check_confidence_collapse(current_pcts)
        if is_collapse:
            anomalies.append({"type": "CONFIDENCE_COLLAPSE", "reason": reason})
            logger.warning(f"ANOMALY: {reason}")
        
        return {
            "has_anomalies": len(anomalies) > 0,
            "anomalies": anomalies,
            "current_distribution": current_pcts,
        }
    
    def get_summary(self) -> Dict:
        """Get monitoring summary."""
        if len(self.confidence_scores) == 0:
            return {
                "total_signals": 0,
                "anomalies_detected": 0,
                "current_distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            }
        
        # Current distribution
        counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for score in self.confidence_scores:
            counts[score] += 1
        
        total = len(self.confidence_scores)
        pcts = {k: (v / total * 100) for k, v in counts.items()}
        
        return {
            "total_signals": total,
            "anomalies_detected": self.anomalies_detected,
            "current_distribution": pcts,
            "daily_snapshots_count": len(self.daily_snapshots),
        }
