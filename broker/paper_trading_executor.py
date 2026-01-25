"""
Paper trading executor.

Orchestrates the paper trading flow:
1. Generate signals after market close
2. Submit orders before market open
3. Track fills and positions
4. Monitor degradation
5. Log all activity

This module connects signal generation to broker execution.
It enforces RiskManager approval before every order.
"""

import logging
from typing import Optional, Dict, Tuple
from datetime import datetime
import pandas as pd

from broker.adapter import BrokerAdapter
from broker.execution_logger import ExecutionLogger
from risk.risk_manager import RiskManager
from risk.portfolio_state import PortfolioState
from monitoring.system_guard import SystemGuard

logger = logging.getLogger(__name__)


class PaperTradingExecutor:
    """
    Orchestrates paper trading flow.
    
    Responsibility:
    1. Take signals with confidence
    2. Get RiskManager approval
    3. Submit orders to broker
    4. Track fills
    5. Monitor positions
    6. Log everything
    
    Safety:
    - Enforces risk manager approval on every trade
    - Respects daily trade limits
    - Respects position sizing limits
    - Integrated with monitoring system
    """
    
    def __init__(
        self,
        broker: BrokerAdapter,
        risk_manager: RiskManager,
        monitor: Optional[SystemGuard] = None,
        logger_instance: Optional[ExecutionLogger] = None,
    ):
        """
        Initialize paper trading executor.
        
        Args:
            broker: BrokerAdapter instance (e.g., AlpacaAdapter)
            risk_manager: RiskManager for trade approval
            monitor: SystemGuard for degradation detection (optional)
            logger_instance: ExecutionLogger for audit trail (optional)
        """
        self.broker = broker
        self.risk_manager = risk_manager
        self.monitor = monitor
        self.exec_logger = logger_instance or ExecutionLogger()
        
        # Track submitted orders
        self.pending_orders: Dict[str, str] = {}  # order_id -> symbol
        self.filled_orders: Dict[str, float] = {}  # symbol -> fill_price
        
        logger.info("Paper Trading Executor initialized")
        logger.info(f"  Broker: {broker.__class__.__name__}")
        logger.info(f"  Risk Manager: {risk_manager.__class__.__name__}")
        logger.info(f"  Monitoring: {'Enabled' if monitor else 'Disabled'}")
    
    def execute_signal(
        self,
        symbol: str,
        confidence: int,
        signal_date: datetime,
        features: Dict[str, float],
    ) -> Tuple[bool, Optional[str]]:
        """
        Execute a trading signal end-to-end.
        
        Flow:
        1. Log signal generation
        2. Get RiskManager approval
        3. Submit order to broker
        4. Track order
        5. Log execution
        
        Args:
            symbol: Ticker symbol
            confidence: Confidence score (1-5)
            signal_date: Date signal was generated
            features: Feature dictionary for logging
        
        Returns:
            Tuple of (success: bool, order_id: Optional[str])
            - success: True if order submitted
            - order_id: Broker order ID if successful
        """
        logger.info("=" * 80)
        logger.info(f"EXECUTING SIGNAL: {symbol} (confidence={confidence})")
        logger.info("=" * 80)
        
        # Step 1: Log signal
        try:
            self.exec_logger.log_signal_generated(
                symbol=symbol,
                confidence=confidence,
                signal_date=signal_date,
                features=features,
            )
        except Exception as e:
            logger.error(f"Failed to log signal: {e}")
        
        # Step 2: Check auto-protection status
        if self.monitor and self.monitor.get_status()["protection_active"]:
            logger.warning(f"Auto-protection is active. Skipping trade: {symbol}")
            self.exec_logger.log_error(
                "auto_protection_active",
                f"Cannot execute signal for {symbol}: auto-protection active"
            )
            return False, None
        
        # Step 3: Get RiskManager approval
        decision = self.risk_manager.evaluate_trade(
            symbol=symbol,
            entry_price=None,  # Will be filled at next open
            confidence=confidence,
        )
        
        self.exec_logger.log_risk_check(
            symbol=symbol,
            confidence=confidence,
            approved=decision.approved,
            reason=decision.reason,
            position_size=decision.position_size if decision.approved else None,
            risk_amount=decision.risk_amount if decision.approved else None,
        )
        
        if not decision.approved:
            logger.warning(f"Risk check failed: {decision.reason}")
            return False, None
        
        # Step 4: Submit order to broker
        try:
            order_result = self.broker.submit_market_order(
                symbol=symbol,
                quantity=decision.position_size,
                side="buy",
                time_in_force="opg",  # At market open
            )
            
            logger.info(f"Order result: {order_result}")
            
            # Log submission
            self.exec_logger.log_order_submitted(
                symbol=symbol,
                order_id=order_result.order_id,
                side="buy",
                quantity=decision.position_size,
                confidence=confidence,
                position_size=decision.position_size,
                risk_amount=decision.risk_amount,
            )
            
            # Track order
            self.pending_orders[order_result.order_id] = symbol
            
            # Step 5: Log to monitoring if enabled
            if self.monitor:
                self.monitor.add_signal(
                    confidence=confidence,
                    signal_date=signal_date,
                )
            
            logger.info(f"✓ Order submitted: {order_result.order_id}")
            return True, order_result.order_id
        
        except Exception as e:
            error_msg = f"Failed to submit order: {e}"
            logger.error(error_msg)
            self.exec_logger.log_error("order_submission_failed", error_msg)
            return False, None
    
    def poll_order_fills(self) -> Dict[str, Tuple[float, datetime]]:
        """
        Poll all pending orders for fills.
        
        Returns:
            Dict of symbol -> (fill_price, fill_time) for newly filled orders
        """
        newly_filled = {}
        orders_to_remove = []
        
        for order_id, symbol in list(self.pending_orders.items()):
            try:
                order_result = self.broker.get_order_status(order_id)
                
                if order_result.is_filled():
                    # Order filled
                    fill_price = order_result.filled_price
                    fill_time = order_result.fill_time or datetime.now()
                    
                    self.exec_logger.log_order_filled(
                        symbol=symbol,
                        order_id=order_id,
                        side="buy",
                        quantity=order_result.filled_qty,
                        fill_price=fill_price,
                        fill_time=fill_time,
                    )
                    
                    newly_filled[symbol] = (fill_price, fill_time)
                    orders_to_remove.append(order_id)
                    
                    logger.info(f"✓ {symbol} filled @ ${fill_price:.2f}")
                
                elif order_result.status.value in ("rejected", "expired", "cancelled"):
                    # Order failed
                    self.exec_logger.log_order_rejected(
                        symbol=symbol,
                        order_id=order_id,
                        side="buy",
                        quantity=order_result.quantity,
                        reason=order_result.rejection_reason or order_result.status.value,
                    )
                    
                    orders_to_remove.append(order_id)
                    
                    logger.warning(f"✗ {symbol} {order_result.status.value}")
            
            except Exception as e:
                logger.error(f"Failed to poll order {order_id}: {e}")
        
        # Remove processed orders
        for order_id in orders_to_remove:
            del self.pending_orders[order_id]
        
        return newly_filled
    
    def close_position(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        entry_date: datetime,
    ) -> bool:
        """
        Close a position.
        
        Args:
            symbol: Ticker symbol
            entry_price: Entry price
            current_price: Current price
            entry_date: Date position was entered
        
        Returns:
            True if close order submitted
        """
        try:
            # Calculate position size (need to query current position)
            position = self.broker.get_position(symbol)
            if not position:
                logger.warning(f"No position to close: {symbol}")
                return False
            
            # Submit close order
            close_result = self.broker.submit_market_order(
                symbol=symbol,
                quantity=abs(position.quantity),
                side="sell" if position.is_long() else "buy",
                time_in_force="day",
            )
            
            # Calculate PnL
            hold_days = (datetime.now() - entry_date).days
            pnl = (current_price - entry_price) * position.quantity
            pnl_pct = (current_price - entry_price) / entry_price
            
            # Log
            self.exec_logger.log_position_closed(
                symbol=symbol,
                quantity=abs(position.quantity),
                entry_price=entry_price,
                exit_price=current_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_days=max(1, hold_days),
            )
            
            logger.info(f"✓ Position closed: {symbol} ({pnl_pct:+.2%})")
            return True
        
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            return False
    
    def get_account_status(self) -> Dict:
        """
        Get current account status.
        
        Returns:
            Dict with:
            - equity: Account equity
            - buying_power: Available buying power
            - pending_orders: Number of pending orders
            - open_positions: Number of open positions
        """
        try:
            positions = self.broker.get_positions()
            
            return {
                "equity": self.broker.account_equity,
                "buying_power": self.broker.buying_power,
                "pending_orders": len(self.pending_orders),
                "open_positions": len(positions),
                "positions": {
                    sym: {
                        "qty": pos.quantity,
                        "avg_price": pos.avg_entry_price,
                        "current_price": pos.current_price,
                        "pnl": pos.unrealized_pnl,
                        "pnl_pct": pos.unrealized_pnl_pct,
                    }
                    for sym, pos in positions.items()
                },
            }
        
        except Exception as e:
            logger.error(f"Failed to get account status: {e}")
            return {}
    
    def get_execution_summary(self) -> Dict:
        """
        Get execution summary.
        
        Returns:
            Dict with trading metrics
        """
        return {
            "execution_logger": self.exec_logger.get_summary(),
            "account_status": self.get_account_status(),
        }
