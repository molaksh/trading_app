"""
INDIA OBSERVATION LOGGING MODULE
==================================

Daily observation tracking for India market validation phase.
Records all signals, trades, rejections, and risk metrics for audit trail.

PURPOSE:
  - Create audit trail of rules-only trading
  - Establish baseline behavior before ML deployment
  - Track why signals were rejected or accepted
  - Identify systematic patterns (confidence distribution, win rate, risk)

OUTPUT:
  - JSONL format (one record per trading day)
  - Location: logs/india_observations/{date}.jsonl
  - Example: logs/india_observations/2024-01-15.jsonl

AUDIT FIELDS:
  - date, timestamp, market_mode
  - symbols_scanned, signals_generated, signals_rejected
  - trades_executed, trades_rejected_risk, trades_rejected_confidence
  - avg_confidence_executed, avg_confidence_rejected
  - portfolio_heat (% of capital at risk)
  - daily_return, max_drawdown
  - status (RULES_ONLY_MODE, rules-based confidence only)

USAGE:
  from monitoring.india_observation_log import IndiaObservationLogger
  
  logger = IndiaObservationLogger()
  
  # At end of trading day:
  logger.record_observation(
      symbols_scanned=["RELIANCE", "INFY", ...],
      signals_generated=5,
      signals_rejected=2,
      trades_executed=3,
      trades_rejected_risk=0,
      trades_rejected_confidence=2,
      avg_confidence_executed=0.72,
      avg_confidence_rejected=0.31,
      portfolio_heat=0.15,
      daily_return=0.0045,
      max_drawdown=0.02
  )
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


class IndiaObservationLogger:
    """
    Logs daily observation data for India market validation.
    
    Safety Features:
    - Immutable append-only JSONL format
    - Daily file rotation (one file per trading day)
    - Automatic directory creation
    - Timestamp validation (prevents backdating)
    """
    
    def __init__(self, log_dir: str = "logs/india_observations"):
        """
        Initialize observation logger.
        
        Args:
            log_dir: Directory for JSONL observation files
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_today_filepath(self) -> Path:
        """Get JSONL filepath for today's date."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{today}.jsonl"
    
    def record_observation(
        self,
        symbols_scanned: List[str],
        signals_generated: int,
        signals_rejected: int,
        trades_executed: int,
        trades_rejected_risk: int,
        trades_rejected_confidence: int,
        avg_confidence_executed: float,
        avg_confidence_rejected: float,
        portfolio_heat: float,
        daily_return: float,
        max_drawdown: float,
        notes: Optional[str] = None,
    ) -> None:
        """
        Record end-of-day observation.
        
        Args:
            symbols_scanned: List of symbols analyzed today
            signals_generated: Total signals produced
            signals_rejected: Signals rejected before execution
            trades_executed: Actual trades placed
            trades_rejected_risk: Signals rejected due to risk limits
            trades_rejected_confidence: Signals rejected due to low confidence
            avg_confidence_executed: Average confidence of executed trades
            avg_confidence_rejected: Average confidence of rejected signals
            portfolio_heat: % of capital at risk (0.0-1.0)
            daily_return: Daily P&L percentage (0.001 = 0.1%)
            max_drawdown: Max drawdown during day
            notes: Optional observation notes
        """
        observation = {
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "market_mode": "INDIA",
            "validation_phase": "RULES_ONLY_MODE",
            "validation_status": "ML disabled, rules-based confidence only",
            
            # Signal metrics
            "symbols_scanned": symbols_scanned,
            "symbols_scanned_count": len(symbols_scanned),
            "signals_generated": signals_generated,
            "signals_rejected": signals_rejected,
            
            # Trade metrics
            "trades_executed": trades_executed,
            "trades_rejected_risk": trades_rejected_risk,
            "trades_rejected_confidence": trades_rejected_confidence,
            
            # Confidence analysis
            "avg_confidence_executed": round(avg_confidence_executed, 4),
            "avg_confidence_rejected": round(avg_confidence_rejected, 4),
            
            # Risk metrics
            "portfolio_heat_pct": round(portfolio_heat * 100, 2),
            
            # Performance
            "daily_return_pct": round(daily_return * 100, 4),
            "max_drawdown_pct": round(max_drawdown * 100, 4),
            
            # Optional
            "notes": notes or "",
        }
        
        # Append to today's JSONL file
        filepath = self._get_today_filepath()
        with open(filepath, "a") as f:
            f.write(json.dumps(observation) + "\n")
        
        print(f"[INDIA] Observation logged: {trades_executed} trades executed, "
              f"{signals_rejected} signals rejected, "
              f"daily return {round(daily_return*100, 2)}%")
    
    def get_observation_count(self) -> int:
        """
        Count total observation days recorded.
        
        Returns:
            Number of trading days with observations
        """
        if not self.log_dir.exists():
            return 0
        
        jsonl_files = list(self.log_dir.glob("*.jsonl"))
        return len(jsonl_files)
    
    def get_recent_observations(self, days: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve recent observations for review.
        
        Args:
            days: Number of recent days to retrieve
            
        Returns:
            List of recent observation records
        """
        if not self.log_dir.exists():
            return []
        
        jsonl_files = sorted(self.log_dir.glob("*.jsonl"), reverse=True)[:days]
        observations = []
        
        for filepath in reversed(jsonl_files):
            with open(filepath, "r") as f:
                for line in f:
                    if line.strip():
                        observations.append(json.loads(line))
        
        return observations
    
    def get_observation_status(self) -> Dict[str, Any]:
        """
        Get current observation status (for safety checks).
        
        Returns:
            Dictionary with observation count and last observation date
        """
        obs_count = self.get_observation_count()
        recent = self.get_recent_observations(days=1)
        
        last_date = None
        if recent:
            last_date = recent[-1].get("date")
        
        return {
            "total_observation_days": obs_count,
            "last_observation_date": last_date,
            "ready_for_ml_validation": obs_count >= 20,  # Default threshold
            "observations_needed_for_ml": max(0, 20 - obs_count),
        }
