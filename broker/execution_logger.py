"""
Execution logging for paper trading.

Comprehensive logging of all trades:
- Signal generation
- Risk approval
- Order submission
- Fill confirmation
- Position tracking

All logs are machine-readable JSON for automated analysis.

Phase 0: Uses ScopePathResolver for scope-isolated log paths.
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from config.scope import get_scope
from config.scope_paths import get_scope_paths

logger = logging.getLogger(__name__)


class ExecutionLogger:
    """
    Logs all trading activity for audit and analysis.
    
    Creates:
    - Daily JSON trade log (or continuous execution log)
    - Error log for issues
    
    Phase 0: Uses ScopePathResolver for scope-isolated log paths.
    All logs stored under BASE_DIR/<scope>/logs/
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        """
        Initialize execution logger.
        
        Args:
            log_dir: Directory for log files (deprecated, uses ScopePathResolver)
        """
        # Phase 0: Use scope-aware path resolver
        scope = get_scope()
        scope_paths = get_scope_paths(scope)
        
        # Primary log: execution_log.jsonl (continuous, append-only)
        self.trade_log_path = scope_paths.get_execution_log_path()
        
        # Error log in same directory
        logs_dir = scope_paths.get_logs_dir()
        self.error_log_path = logs_dir / "errors.jsonl"
        
        # Ensure parent directories exist
        self.trade_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("=" * 80)
        logger.info(f"EXECUTION LOGGER INITIALIZED (SCOPE: {scope})")
        logger.info(f"  Execution Log: {self.trade_log_path}")
        logger.info(f"  Error Log: {self.error_log_path}")
        logger.info(f"  Base Directory: {logs_dir.parent.parent}")
        logger.info("=" * 80)
    
    def log_signal_generated(
        self,
        symbol: str,
        confidence: int,
        signal_date: datetime,
        features: Dict[str, float],
    ) -> None:
        """
        Log signal generation.
        
        Args:
            symbol: Ticker symbol
            confidence: Confidence score (1-5)
            signal_date: Date signal was generated
            features: Feature values
        """
        entry = {
            "event": "signal_generated",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "confidence": confidence,
            "signal_date": signal_date.isoformat() if isinstance(signal_date, datetime) else str(signal_date),
            "features": features,
        }
        self._write_trade_log(entry)
        logger.info(f"Signal: {symbol} confidence={confidence}")
    
    def log_risk_check(
        self,
        symbol: str,
        confidence: int,
        approved: bool,
        reason: str,
        position_size: Optional[float] = None,
        risk_amount: Optional[float] = None,
    ) -> None:
        """
        Log risk manager decision.
        
        Args:
            symbol: Ticker symbol
            confidence: Confidence score
            approved: Whether trade was approved
            reason: Reason for decision
            position_size: Position size if approved
            risk_amount: Risk amount if approved
        """
        entry = {
            "event": "risk_check",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "confidence": confidence,
            "approved": approved,
            "reason": reason,
            "position_size": position_size,
            "risk_amount": risk_amount,
        }
        self._write_trade_log(entry)
        
        status = "✓" if approved else "✗"
        logger.info(f"{status} Risk check: {symbol} - {reason}")
    
    def log_order_submitted(
        self,
        symbol: str,
        order_id: str,
        side: str,
        quantity: float,
        confidence: int,
        position_size: float,
        risk_amount: float,
    ) -> None:
        """
        Log order submission to broker.
        
        Args:
            symbol: Ticker symbol
            order_id: Broker order ID
            side: "buy" or "sell"
            quantity: Number of shares
            confidence: Confidence score
            position_size: Position size (%)
            risk_amount: Risk amount (%)
        """
        entry = {
            "event": "order_submitted",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "order_id": order_id,
            "side": side.upper(),
            "quantity": quantity,
            "confidence": confidence,
            "position_size": position_size,
            "risk_amount": risk_amount,
        }
        self._write_trade_log(entry)
        
        logger.info(
            f"Order submitted: {side.upper()} {quantity} {symbol} "
            f"(conf={confidence}, order_id={order_id})"
        )
    
    def log_order_filled(
        self,
        symbol: str,
        order_id: str,
        side: str,
        quantity: float,
        fill_price: float,
        fill_time: datetime,
    ) -> None:
        """
        Log order fill confirmation.
        
        Args:
            symbol: Ticker symbol
            order_id: Broker order ID
            side: "buy" or "sell"
            quantity: Filled quantity
            fill_price: Fill price
            fill_time: Fill timestamp
        """
        entry = {
            "event": "order_filled",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "order_id": order_id,
            "side": side.upper(),
            "quantity": quantity,
            "fill_price": fill_price,
            "fill_time": fill_time.isoformat() if isinstance(fill_time, datetime) else str(fill_time),
        }
        self._write_trade_log(entry)
        
        logger.info(
            f"Order filled: {side.upper()} {quantity} {symbol} "
            f"@ ${fill_price:.2f}"
        )
    
    def log_order_rejected(
        self,
        symbol: str,
        order_id: str,
        side: str,
        quantity: float,
        reason: str,
    ) -> None:
        """
        Log order rejection.
        
        Args:
            symbol: Ticker symbol
            order_id: Broker order ID
            side: "buy" or "sell"
            quantity: Requested quantity
            reason: Rejection reason
        """
        entry = {
            "event": "order_rejected",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "order_id": order_id,
            "side": side.upper(),
            "quantity": quantity,
            "reason": reason,
        }
        self._write_trade_log(entry)
        self._write_error_log(entry)
        
        logger.warning(f"Order rejected: {symbol} - {reason}")
    
    def log_monitoring_alert(
        self,
        alert_type: str,
        details: Dict[str, Any],
    ) -> None:
        """
        Log monitoring system alert.
        
        Args:
            alert_type: Type of alert (e.g., "confidence_inflation")
            details: Alert details
        """
        entry = {
            "event": "monitoring_alert",
            "timestamp": datetime.now().isoformat(),
            "alert_type": alert_type,
            "details": details,
        }
        self._write_trade_log(entry)
        self._write_error_log(entry)
        
        logger.warning(f"Monitoring alert: {alert_type}")
    
    def log_auto_protection_triggered(
        self,
        reason: str,
        consecutive_alerts: int,
    ) -> None:
        """
        Log auto-protection trigger.
        
        Args:
            reason: Why protection was triggered
            consecutive_alerts: Number of consecutive alerts
        """
        entry = {
            "event": "auto_protection_triggered",
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "consecutive_alerts": consecutive_alerts,
        }
        self._write_trade_log(entry)
        self._write_error_log(entry)
        
        logger.critical(
            f"AUTO-PROTECTION TRIGGERED: {reason} "
            f"({consecutive_alerts} consecutive alerts)"
        )
    
    def log_exit_signal(
        self,
        symbol: str,
        exit_type: str,
        reason: str,
        entry_date: str,
        holding_days: int,
        confidence: int,
        urgency: str,
    ) -> None:
        """
        Log exit signal generation.
        
        Args:
            symbol: Ticker symbol
            exit_type: SWING_EXIT or EMERGENCY_EXIT
            reason: Exit reason
            entry_date: Position entry date
            holding_days: Days held
            confidence: Original entry confidence
            urgency: 'eod' or 'immediate'
        """
        entry = {
            "event": "exit_signal",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "exit_type": exit_type,
            "reason": reason,
            "entry_date": entry_date,
            "holding_days": holding_days,
            "confidence": confidence,
            "urgency": urgency,
        }
        self._write_trade_log(entry)
        logger.info(f"Exit signal: {symbol} ({exit_type}) - {reason}")
    
    def log_position_closed(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        hold_days: int,
        entry_date: Optional[str] = None,
        exit_type: Optional[str] = None,
        exit_reason: Optional[str] = None,
    ) -> None:
        """
        Log position closure.
        
        Args:
            symbol: Ticker symbol
            quantity: Position size
            entry_price: Entry price
            exit_price: Exit price
            pnl: Profit/loss in dollars
            pnl_pct: Profit/loss in percent
            hold_days: Days held
            entry_date: Position entry date (optional)
            exit_type: SWING_EXIT or EMERGENCY_EXIT (optional)
            exit_reason: Reason for exit (optional)
        """
        entry = {
            "event": "position_closed",
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "hold_days": hold_days,
        }
        
        # Add optional exit metadata for audit trail
        if entry_date:
            entry["entry_date"] = entry_date
        if exit_type:
            entry["exit_type"] = exit_type
        if exit_reason:
            entry["exit_reason"] = exit_reason
        
        self._write_trade_log(entry)
        
        status = "✓" if pnl > 0 else "✗"
        logger.info(
            f"{status} Position closed: {symbol} "
            f"{hold_days}d, PnL: {pnl_pct:+.2%} (${pnl:+.2f})"
        )
    
    def log_error(self, error_type: str, details: str) -> None:
        """
        Log system error.
        
        Args:
            error_type: Type of error
            details: Error details
        """
        entry = {
            "event": "system_error",
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "details": details,
        }
        self._write_error_log(entry)
        logger.error(f"{error_type}: {details}")
    
    def _write_trade_log(self, entry: Dict[str, Any]) -> None:
        """Write entry to trade log."""
        try:
            with open(self.trade_log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write trade log: {e}")
    
    def _write_error_log(self, entry: Dict[str, Any]) -> None:
        """Write entry to error log."""
        try:
            with open(self.error_log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write error log: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get today's trading summary.
        
        Returns:
            Summary statistics from today's trades
        """
        if not self.trade_log_path.exists():
            return {
                "trades": 0,
                "filled": 0,
                "rejected": 0,
                "alerts": 0,
            }
        
        trades = 0
        filled = 0
        rejected = 0
        alerts = 0
        
        try:
            with open(self.trade_log_path, "r") as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("event") == "order_filled":
                        filled += 1
                    elif entry.get("event") == "order_rejected":
                        rejected += 1
                    elif entry.get("event") == "monitoring_alert":
                        alerts += 1
                    trades += 1
        except Exception as e:
            logger.error(f"Failed to read trade log: {e}")
        
        return {
            "trades": trades,
            "filled": filled,
            "rejected": rejected,
            "alerts": alerts,
        }
