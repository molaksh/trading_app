"""
System Guard (Phase H)

Orchestrates all monitors and triggers auto-protection when degradation is detected.
Coordinates monitoring decisions and implements reversible auto-protection logic.
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd

from monitoring.confidence_monitor import ConfidenceDistributionMonitor
from monitoring.performance_monitor import PerformanceMonitor
from monitoring.feature_drift import FeatureDriftMonitor

logger = logging.getLogger(__name__)


class SystemGuard:
    """
    Orchestrates monitoring and auto-protection.
    
    Runs all monitors and decides when to trigger auto-protection.
    Can automatically disable ML sizing when degradation is detected.
    """
    
    def __init__(
        self,
        use_ml_sizing: bool = True,
        enable_confidence_monitoring: bool = True,
        enable_performance_monitoring: bool = True,
        enable_feature_drift_monitoring: bool = True,
        auto_protection_enabled: bool = True,
        max_consecutive_alerts: int = 3,  # Trigger protection after this many alerts
    ):
        """
        Initialize system guard.
        
        Args:
            use_ml_sizing: Whether ML sizing is enabled
            enable_confidence_monitoring: Monitor confidence distribution
            enable_performance_monitoring: Monitor performance by tier
            enable_feature_drift_monitoring: Monitor feature drift
            auto_protection_enabled: Enable automatic protection responses
            max_consecutive_alerts: Trigger protection after N consecutive alerts
        """
        self.use_ml_sizing = use_ml_sizing
        self.enable_confidence_monitoring = enable_confidence_monitoring
        self.enable_performance_monitoring = enable_performance_monitoring
        self.enable_feature_drift_monitoring = enable_feature_drift_monitoring
        self.auto_protection_enabled = auto_protection_enabled
        self.max_consecutive_alerts = max_consecutive_alerts
        
        # Monitors
        self.confidence_monitor = ConfidenceDistributionMonitor() if enable_confidence_monitoring else None
        self.performance_monitor = PerformanceMonitor() if enable_performance_monitoring else None
        self.feature_drift_monitor = None  # Initialized later with feature names
        
        # Auto-protection state
        self.ml_sizing_enabled = use_ml_sizing
        self.protection_active = False
        self.protection_triggered_at = None
        
        # Statistics
        self.consecutive_alerts = 0
        self.total_alerts = 0
        self.degradations_detected = 0
        self.protection_activations = 0
        
        # Alert log
        self.alerts = []
    
    def initialize_feature_drift_monitor(self, feature_names: List[str]):
        """Initialize feature drift monitor with feature names."""
        if self.enable_feature_drift_monitoring:
            self.feature_drift_monitor = FeatureDriftMonitor(feature_names)
            logger.info(f"Feature drift monitor initialized for {len(feature_names)} features")
    
    def add_signal(self, confidence: int, signal_date=None):
        """Add signal for confidence monitoring."""
        if self.confidence_monitor is not None:
            if signal_date is None:
                signal_date = pd.Timestamp.now()
            self.confidence_monitor.add_signal(confidence, signal_date)
    
    def add_trade(self, confidence: int, entry_price: float, exit_price: float, contract_count: float):
        """Add trade result for performance monitoring."""
        if self.performance_monitor is not None:
            pnl_pct = (exit_price - entry_price) / entry_price
            won = pnl_pct > 0
            self.performance_monitor.add_trade(confidence, entry_price, exit_price, pnl_pct, won)
    
    def add_features(self, feature_dict: Dict, date):
        """Add features for drift monitoring."""
        if self.feature_drift_monitor is not None:
            self.feature_drift_monitor.add_features(feature_dict, date)
    
    def check_degradation(self) -> Dict:
        """
        Check all monitors for degradation.
        
        Returns:
            Dict with degradation status and details
        """
        degradation_events = []
        current_date = pd.Timestamp.now()
        
        # Check confidence distribution
        if self.confidence_monitor is not None:
            confidence_check = self.confidence_monitor.check_for_anomalies(current_date)
            if confidence_check.get("has_anomalies", False):
                degradation_events.append({
                    "type": "CONFIDENCE_ANOMALY",
                    "details": confidence_check,
                })
        
        # Check performance by tier
        if self.performance_monitor is not None:
            perf_check = self.performance_monitor.check_all_tiers()
            if perf_check.get("has_degradation", False):
                degradation_events.append({
                    "type": "PERFORMANCE_DEGRADATION",
                    "details": perf_check,
                })
        
        # Check feature drift
        if self.feature_drift_monitor is not None:
            drift_check = self.feature_drift_monitor.detect_drift()
            if drift_check.get("has_drift", False):
                degradation_events.append({
                    "type": "FEATURE_DRIFT",
                    "details": drift_check,
                })
        
        # Update alert tracking
        if len(degradation_events) > 0:
            self.consecutive_alerts += 1
            self.total_alerts += 1
        else:
            self.consecutive_alerts = 0
        
        # Check if auto-protection should be triggered
        has_degradation = len(degradation_events) > 0
        should_trigger_protection = (
            self.auto_protection_enabled and
            has_degradation and
            self.consecutive_alerts >= self.max_consecutive_alerts
        )
        
        return {
            "has_degradation": has_degradation,
            "degradation_events": degradation_events,
            "consecutive_alerts": self.consecutive_alerts,
            "should_trigger_protection": should_trigger_protection,
        }
    
    def trigger_auto_protection(self, reason: str = ""):
        """
        Trigger auto-protection.
        
        Disables ML sizing and tightens risk controls.
        """
        if not self.auto_protection_enabled:
            logger.warning("Auto-protection is disabled")
            return
        
        if self.protection_active:
            logger.info("Auto-protection already active")
            return
        
        self.protection_active = True
        self.protection_triggered_at = datetime.now()
        self.protection_activations += 1
        self.ml_sizing_enabled = False
        
        msg = f"AUTO-PROTECTION TRIGGERED: {reason}"
        logger.warning(msg)
        self.alerts.append(("AUTO_PROTECTION", msg))
    
    def disable_auto_protection(self, reason: str = ""):
        """
        Disable auto-protection and restore normal operation.
        
        This is reversible - allows re-enabling ML sizing after investigation.
        """
        if not self.protection_active:
            logger.info("Auto-protection not active")
            return
        
        self.protection_active = False
        self.protection_triggered_at = None
        self.ml_sizing_enabled = self.use_ml_sizing
        self.consecutive_alerts = 0
        
        msg = f"AUTO-PROTECTION DISABLED: {reason}"
        logger.info(msg)
        self.alerts.append(("PROTECTION_DISABLED", msg))
    
    def update_daily_snapshots(self):
        """Update daily snapshots for monitors."""
        date = pd.Timestamp.now()
        if self.confidence_monitor is not None:
            self.confidence_monitor.update_daily_snapshot(date)
    
    def get_status(self) -> Dict:
        """Get overall system status."""
        return {
            "protection_active": self.protection_active,
            "ml_sizing_enabled": self.ml_sizing_enabled,
            "consecutive_alerts": self.consecutive_alerts,
            "total_alerts": self.total_alerts,
            "degradations_detected": self.degradations_detected,
            "protection_activations": self.protection_activations,
        }
    
    def get_summary(self) -> Dict:
        """Get comprehensive monitoring summary."""
        summary = {
            "system_guard": self.get_status(),
            "protection": {
                "active": self.protection_active,
                "triggered_at": str(self.protection_triggered_at) if self.protection_triggered_at else None,
            },
        }
        
        if self.confidence_monitor is not None:
            summary["confidence_monitor"] = self.confidence_monitor.get_summary()
        
        if self.performance_monitor is not None:
            summary["performance_monitor"] = self.performance_monitor.get_summary()
        
        if self.feature_drift_monitor is not None:
            summary["feature_drift_monitor"] = self.feature_drift_monitor.get_summary()
        
        return summary
