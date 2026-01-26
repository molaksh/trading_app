"""
Paper trading executor.

Orchestrates the paper trading flow:
1. Generate signals after market close
2. Submit orders before market open
3. Track fills and positions
4. Monitor degradation
5. Evaluate exit signals (swing + emergency)
6. Log all activity

This module connects signal generation to broker execution.
It enforces RiskManager approval before every order.
"""

import logging
from typing import Optional, Dict, Tuple, List
from datetime import datetime, date
import pandas as pd

from broker.adapter import BrokerAdapter
from broker.execution_logger import ExecutionLogger
from risk.risk_manager import RiskManager
from risk.portfolio_state import PortfolioState
from monitoring.system_guard import SystemGuard
from strategy.exit_evaluator import ExitEvaluator, ExitSignal

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
        exit_evaluator: Optional[ExitEvaluator] = None,
    ):
        """
        Initialize paper trading executor.
        
        Args:
            broker: BrokerAdapter instance (e.g., AlpacaAdapter)
            risk_manager: RiskManager for trade approval
            monitor: SystemGuard for degradation detection (optional)
            logger_instance: ExecutionLogger for audit trail (optional)
            exit_evaluator: ExitEvaluator for exit signals (optional)
        """
        self.broker = broker
        self.risk_manager = risk_manager
        self.monitor = monitor
        self.exec_logger = logger_instance or ExecutionLogger()
        self.exit_evaluator = exit_evaluator or ExitEvaluator()
        
        # Track submitted orders
        self.pending_orders: Dict[str, str] = {}  # order_id -> symbol
        self.filled_orders: Dict[str, float] = {}  # symbol -> fill_price
        
        logger.info("Paper Trading Executor initialized")
        logger.info(f"  Broker: {broker.__class__.__name__}")
        logger.info(f"  Risk Manager: {risk_manager.__class__.__name__}")
        logger.info(f"  Monitoring: {'Enabled' if monitor else 'Disabled'}")
        logger.info(f"  Exit Evaluator: {'Enabled' if exit_evaluator else 'Disabled'}")
    
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
        entry_price = float(features.get("close", 0) or 0)
        current_prices = {sym: entry_price for sym in self.risk_manager.portfolio.open_positions.keys()}
        current_prices[symbol] = entry_price

        decision = self.risk_manager.evaluate_trade(
            symbol=symbol,
            entry_price=entry_price,
            confidence=confidence,
            current_prices=current_prices,
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
                time_in_force="day",  # Submit immediately during regular hours
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
        Poll all pending orders for fills and update portfolio state.
        
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
                    
                    # Record fill in portfolio state (if not already there)
                    # This syncs broker fills with our portfolio tracking
                    try:
                        # Try to get existing portfolio position metadata
                        # If this is a new fill, we need to add it to portfolio state
                        portfolio_positions = self.risk_manager.portfolio.open_positions
                        if symbol not in portfolio_positions or not portfolio_positions[symbol]:
                            # Position not in portfolio yet - this shouldn't happen normally
                            # but can occur if we restart after fills
                            logger.debug(f"Syncing fill to portfolio state: {symbol}")
                            self.risk_manager.portfolio.open_trade(
                                symbol=symbol,
                                entry_date=pd.Timestamp(fill_time),
                                entry_price=fill_price,
                                position_size=order_result.filled_qty,
                                risk_amount=0.0,  # Unknown at this point
                                confidence=3,  # Default confidence
                            )
                    except Exception as e:
                        logger.warning(f"Could not sync {symbol} to portfolio state: {e}")
                    
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
    
    def evaluate_exits_eod(
        self,
        eod_data: Optional[Dict[str, pd.Series]] = None,
        evaluation_date: Optional[date] = None,
    ) -> List[ExitSignal]:
        """
        Evaluate EOD swing exits for all open positions.
        
        SWING TRADING: Only call this with end-of-day data.
        Never triggers same-day exit.
        Exits execute at next market open.
        
        Args:
            eod_data: Dict of symbol -> EOD OHLCV Series with indicators
            evaluation_date: Date of evaluation (defaults to today)
        
        Returns:
            List of ExitSignal for positions that should exit
        """
        exit_signals = []
        
        try:
            # Get all open positions
            positions = self.broker.get_positions()
            portfolio_positions = self.risk_manager.portfolio.open_positions
            
            for symbol, broker_pos in positions.items():
                # Get position metadata from portfolio state
                if symbol not in portfolio_positions or not portfolio_positions[symbol]:
                    logger.warning(f"Position {symbol} in broker but not in portfolio state")
                    continue
                
                portfolio_pos = portfolio_positions[symbol][0]  # FIFO
                
                # Evaluate swing exit
                exit_signal = self.exit_evaluator.evaluate_eod(
                    symbol=symbol,
                    entry_date=portfolio_pos.entry_date.date(),
                    entry_price=portfolio_pos.entry_price,
                    current_price=broker_pos.current_price,
                    confidence=portfolio_pos.confidence,
                    eod_data=eod_data.get(symbol) if eod_data else None,
                    evaluation_date=evaluation_date,
                )
                
                if exit_signal:
                    exit_signals.append(exit_signal)
                    
                    # Log exit signal
                    self.exec_logger.log_exit_signal(
                        symbol=exit_signal.symbol,
                        exit_type=exit_signal.exit_type.value,
                        reason=exit_signal.reason,
                        entry_date=exit_signal.entry_date.isoformat(),
                        holding_days=exit_signal.holding_days,
                        confidence=exit_signal.confidence,
                        urgency=exit_signal.urgency,
                    )
                    
                    logger.info(
                        f"EOD Exit Signal: {symbol} - {exit_signal.reason} "
                        f"(held {exit_signal.holding_days} days)"
                    )
            
            return exit_signals
        
        except Exception as e:
            logger.error(f"Failed to evaluate EOD exits: {e}")
            return []
    
    def evaluate_exits_emergency(
        self,
        atr_data: Optional[Dict[str, float]] = None,
        evaluation_date: Optional[date] = None,
    ) -> List[ExitSignal]:
        """
        Evaluate intraday emergency exits for all open positions.
        
        CAPITAL PROTECTION: Continuous during market hours.
        Will NOT trigger same-day exit unless catastrophic.
        Should be RARE in normal market conditions.
        
        Args:
            atr_data: Dict of symbol -> ATR for volatility checks
            evaluation_date: Date of evaluation (defaults to today)
        
        Returns:
            List of ExitSignal for positions with emergency exits
        """
        exit_signals = []
        
        try:
            # Get all open positions
            positions = self.broker.get_positions()
            portfolio_positions = self.risk_manager.portfolio.open_positions
            portfolio_equity = self.risk_manager.portfolio.current_equity
            
            for symbol, broker_pos in positions.items():
                # Get position metadata
                if symbol not in portfolio_positions or not portfolio_positions[symbol]:
                    continue
                
                portfolio_pos = portfolio_positions[symbol][0]  # FIFO
                
                # Evaluate emergency exit
                exit_signal = self.exit_evaluator.evaluate_emergency(
                    symbol=symbol,
                    entry_date=portfolio_pos.entry_date.date(),
                    entry_price=portfolio_pos.entry_price,
                    current_price=broker_pos.current_price,
                    position_size=broker_pos.quantity,
                    portfolio_equity=portfolio_equity,
                    confidence=portfolio_pos.confidence,
                    atr=atr_data.get(symbol) if atr_data else None,
                    evaluation_date=evaluation_date,
                )
                
                if exit_signal:
                    exit_signals.append(exit_signal)
                    
                    # Log emergency exit signal
                    self.exec_logger.log_exit_signal(
                        symbol=exit_signal.symbol,
                        exit_type=exit_signal.exit_type.value,
                        reason=exit_signal.reason,
                        entry_date=exit_signal.entry_date.isoformat(),
                        holding_days=exit_signal.holding_days,
                        confidence=exit_signal.confidence,
                        urgency=exit_signal.urgency,
                    )
                    
                    logger.warning(
                        f"EMERGENCY Exit Signal: {symbol} - {exit_signal.reason} "
                        f"(held {exit_signal.holding_days} days)"
                    )
            
            return exit_signals
        
        except Exception as e:
            logger.error(f"Failed to evaluate emergency exits: {e}")
            return []
    
    def execute_exit(
        self,
        exit_signal: ExitSignal,
    ) -> bool:
        """
        Execute an exit signal by closing the position.
        
        Args:
            exit_signal: ExitSignal to execute
        
        Returns:
            True if exit order submitted successfully
        """
        symbol = exit_signal.symbol
        
        try:
            # Get current position
            position = self.broker.get_position(symbol)
            if not position:
                logger.warning(f"No position to close: {symbol}")
                return False
            
            # Get portfolio position for entry metadata
            portfolio_positions = self.risk_manager.portfolio.open_positions
            if symbol not in portfolio_positions or not portfolio_positions[symbol]:
                logger.warning(f"Position {symbol} not in portfolio state")
                return False
            
            portfolio_pos = portfolio_positions[symbol][0]  # FIFO
            
            # Submit close order
            close_result = self.broker.submit_market_order(
                symbol=symbol,
                quantity=abs(position.quantity),
                side="sell" if position.is_long() else "buy",
                time_in_force="day",
            )
            
            # Calculate PnL
            current_price = position.current_price
            pnl = (current_price - portfolio_pos.entry_price) * position.quantity
            pnl_pct = (current_price - portfolio_pos.entry_price) / portfolio_pos.entry_price
            
            # Log position closure with exit metadata
            self.exec_logger.log_position_closed(
                symbol=symbol,
                quantity=abs(position.quantity),
                entry_price=portfolio_pos.entry_price,
                exit_price=current_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_days=exit_signal.holding_days,
                entry_date=exit_signal.entry_date.isoformat(),
                exit_type=exit_signal.exit_type.value,
                exit_reason=exit_signal.reason,
            )
            
            # Update portfolio state
            self.risk_manager.portfolio.close_trade(
                symbol=symbol,
                exit_date=pd.Timestamp.now(),
                exit_price=current_price,
            )
            
            logger.info(
                f"✓ Exit executed: {symbol} ({exit_signal.exit_type.value}) "
                f"PnL: {pnl_pct:+.2%} - {exit_signal.reason}"
            )
            return True
        
        except Exception as e:
            logger.error(f"Failed to execute exit for {symbol}: {e}")
            return False
    
    def close_position(
        self,
        symbol: str,
        reason: Optional[str] = None,
        exit_type: str = "MANUAL",
    ) -> bool:
        """
        Close a position manually.
        
        Args:
            symbol: Ticker symbol
            reason: Reason for closing (optional)
            exit_type: Exit classification (default: MANUAL)
        
        Returns:
            True if close order submitted
        """
        try:
            # Get current position
            position = self.broker.get_position(symbol)
            if not position:
                logger.warning(f"No position to close: {symbol}")
                return False
            
            # Get portfolio position for entry metadata
            portfolio_positions = self.risk_manager.portfolio.open_positions
            if symbol not in portfolio_positions or not portfolio_positions[symbol]:
                logger.warning(f"Position {symbol} not in portfolio state")
                return False
            
            portfolio_pos = portfolio_positions[symbol][0]  # FIFO
            
            # Submit close order
            close_result = self.broker.submit_market_order(
                symbol=symbol,
                quantity=abs(position.quantity),
                side="sell" if position.is_long() else "buy",
                time_in_force="day",
            )
            
            # Calculate PnL
            current_price = position.current_price
            hold_days = (datetime.now() - portfolio_pos.entry_date).days
            pnl = (current_price - portfolio_pos.entry_price) * position.quantity
            pnl_pct = (current_price - portfolio_pos.entry_price) / portfolio_pos.entry_price
            
            # Log with exit metadata
            self.exec_logger.log_position_closed(
                symbol=symbol,
                quantity=abs(position.quantity),
                entry_price=portfolio_pos.entry_price,
                exit_price=current_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                hold_days=max(1, hold_days),
                entry_date=portfolio_pos.entry_date.date().isoformat(),
                exit_type=exit_type,
                exit_reason=reason,
            )
            
            # Update portfolio state
            self.risk_manager.portfolio.close_trade(
                symbol=symbol,
                exit_date=pd.Timestamp.now(),
                exit_price=current_price,
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
