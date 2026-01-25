"""
Performance Monitor by Confidence Tier (Phase H)

Tracks win rates, returns, and drawdowns per confidence level.
Detects when performance degrades for specific confidence tiers.
"""

import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Track and monitor performance metrics by confidence tier.
    
    Tracks:
    - Win rate per confidence level
    - Average return per confidence level
    - Max drawdown per confidence level
    """
    
    def __init__(
        self,
        min_tier_trades: int = 10,           # Min trades per tier before checking
        win_rate_alert_threshold: float = 0.40,  # Flag if win rate drops below 40%
        avg_return_alert_threshold: float = -0.01,  # Flag if avg return < -1%
    ):
        """
        Initialize performance monitor.
        
        Args:
            min_tier_trades: Minimum trades in tier before checking anomalies
            win_rate_alert_threshold: Min acceptable win rate
            avg_return_alert_threshold: Min acceptable avg return
        """
        self.min_tier_trades = min_tier_trades
        self.win_rate_alert_threshold = win_rate_alert_threshold
        self.avg_return_alert_threshold = avg_return_alert_threshold
        
        # Performance by confidence tier
        # {confidence: [returns list]}
        self.tier_returns = defaultdict(list)
        # {confidence: [wins (1 or 0)]}
        self.tier_wins = defaultdict(list)
        
        # Drawdowns by tier
        self.tier_peak_prices = defaultdict(float)
        self.tier_max_drawdowns = defaultdict(float)
        
        # Alerts
        self.alerts = []
        self.degradations_detected = 0
    
    def add_trade(
        self,
        confidence: int,
        entry_price: float,
        exit_price: float,
        pnl_pct: float,
        won: bool,
    ):
        """
        Add trade result by confidence tier.
        
        Args:
            confidence: Confidence level 1-5
            entry_price: Entry price
            exit_price: Exit price
            pnl_pct: Return as percentage (e.g., 0.05 = 5%)
            won: Whether trade was a winner
        """
        if not 1 <= confidence <= 5:
            logger.warning(f"Invalid confidence {confidence}")
            return
        
        # Add return
        self.tier_returns[confidence].append(pnl_pct)
        
        # Add win/loss
        self.tier_wins[confidence].append(1 if won else 0)
        
        # Track drawdown
        if entry_price > self.tier_peak_prices[confidence]:
            self.tier_peak_prices[confidence] = entry_price
        
        if entry_price > 0:
            drawdown = (self.tier_peak_prices[confidence] - exit_price) / self.tier_peak_prices[confidence]
            if drawdown > self.tier_max_drawdowns[confidence]:
                self.tier_max_drawdowns[confidence] = drawdown
    
    def calculate_tier_metrics(self, confidence: int) -> Dict:
        """
        Calculate metrics for a confidence tier.
        
        Returns:
            Dict with win_rate, avg_return, max_drawdown, trade_count
        """
        if confidence not in self.tier_returns:
            return {
                "confidence": confidence,
                "trade_count": 0,
                "win_rate": None,
                "avg_return": None,
                "max_drawdown": None,
            }
        
        returns = self.tier_returns[confidence]
        wins = self.tier_wins[confidence]
        
        if len(returns) == 0:
            return {
                "confidence": confidence,
                "trade_count": 0,
                "win_rate": None,
                "avg_return": None,
                "max_drawdown": None,
            }
        
        win_rate = sum(wins) / len(wins) if len(wins) > 0 else None
        avg_return = np.mean(returns) if len(returns) > 0 else None
        max_dd = self.tier_max_drawdowns.get(confidence, 0)
        
        return {
            "confidence": confidence,
            "trade_count": len(returns),
            "win_rate": win_rate,
            "avg_return": avg_return,
            "max_drawdown": max_dd,
        }
    
    def check_tier_degradation(self, confidence: int) -> Tuple[bool, Optional[str]]:
        """
        Check if a confidence tier has degraded.
        
        Returns:
            (is_degraded, reason)
        """
        metrics = self.calculate_tier_metrics(confidence)
        
        if metrics["trade_count"] < self.min_tier_trades:
            return False, None  # Not enough data
        
        degradations = []
        
        # Check win rate
        if metrics["win_rate"] is not None and metrics["win_rate"] < self.win_rate_alert_threshold:
            degradations.append(
                f"Win rate {metrics['win_rate']:.1%} < {self.win_rate_alert_threshold:.1%}"
            )
        
        # Check avg return
        if metrics["avg_return"] is not None and metrics["avg_return"] < self.avg_return_alert_threshold:
            degradations.append(
                f"Avg return {metrics['avg_return']:.2%} < {self.avg_return_alert_threshold:.2%}"
            )
        
        if degradations:
            reason = f"Confidence {confidence} degradation: {', '.join(degradations)}"
            self.degradations_detected += 1
            self.alerts.append(("PERFORMANCE_DEGRADATION", reason))
            return True, reason
        
        return False, None
    
    def check_all_tiers(self) -> Dict:
        """
        Check performance across all confidence tiers.
        
        Returns:
            Dict with degradations and metrics
        """
        degradations = []
        tier_metrics = {}
        
        for confidence in range(1, 6):
            metrics = self.calculate_tier_metrics(confidence)
            tier_metrics[confidence] = metrics
            
            is_degraded, reason = self.check_tier_degradation(confidence)
            if is_degraded:
                degradations.append({
                    "confidence": confidence,
                    "reason": reason,
                    "metrics": metrics,
                })
                logger.warning(f"DEGRADATION: {reason}")
        
        return {
            "has_degradations": len(degradations) > 0,
            "degradations": degradations,
            "tier_metrics": tier_metrics,
        }
    
    def get_summary(self) -> Dict:
        """Get monitoring summary."""
        tier_metrics = {}
        for confidence in range(1, 6):
            tier_metrics[confidence] = self.calculate_tier_metrics(confidence)
        
        total_trades = sum(
            metrics["trade_count"] for metrics in tier_metrics.values()
        )
        
        return {
            "total_trades": total_trades,
            "degradations_detected": self.degradations_detected,
            "tier_metrics": tier_metrics,
        }
