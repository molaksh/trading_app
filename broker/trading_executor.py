"""
Trading executor.

Orchestrates the trading flow:
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
import os
from typing import Optional, Dict, Tuple, List
from datetime import datetime, date
import pandas as pd

from broker.adapter import BrokerAdapter
from broker.execution_logger import ExecutionLogger
from broker.trade_ledger import TradeLedger, create_trade_from_fills
from risk.risk_manager import RiskManager
from risk.portfolio_state import PortfolioState
from monitoring.system_guard import SystemGuard
from runtime.trade_permission import get_trade_permission
from strategy.exit_evaluator import ExitEvaluator, ExitSignal

logger = logging.getLogger(__name__)


# ============================================================================
# BUY ACTION DECISION (Scale-In System)
# ============================================================================

class BuyAction:
    """Buy action decision codes."""
    ENTER_NEW = "ENTER_NEW"              # New position entry
    SCALE_IN = "SCALE_IN"                # Add to existing internal position
    SKIP = "SKIP"                        # Skip this signal (cooldown, max entries, etc)
    BLOCK = "BLOCK"                      # Block due to unreconciled or risk


class BuyBlockReason:
    """Reason codes for blocking/skipping buy signals."""
    UNRECONCILED_BROKER_POSITION = "UNRECONCILED_BROKER_POSITION"
    SAFE_MODE_ACTIVE = "SAFE_MODE_ACTIVE"
    SCALE_IN_DISABLED = "SCALE_IN_DISABLED"
    MAX_ENTRIES_REACHED = "MAX_ENTRIES_REACHED"
    ENTRY_COOLDOWN = "ENTRY_COOLDOWN"
    PRICE_NOT_HIGH_ENOUGH = "PRICE_NOT_HIGH_ENOUGH"
    INSUFFICIENT_POSITION_STATE = "INSUFFICIENT_POSITION_STATE"
    RISK_BLOCK = "RISK_BLOCK"


def evaluate_buy_action(
    symbol: str,
    signal_confidence: int,
    unreconciled_broker_symbols: set,
    internal_position: Optional[Dict],
    current_price: float,
    now: datetime,
    config: Dict,
) -> Tuple[str, Optional[str]]:
    """
    Evaluate whether a BUY signal should proceed and how.
    
    Decision flow:
    1. BLOCK if symbol is unreconciled (broker has it but internal ledger does not)
    2. ENTER_NEW if no internal position exists
    3. SKIP/SCALE_IN based on scale-in rules if internal position exists
    
    Args:
        symbol: Ticker symbol
        signal_confidence: Signal confidence (1-5)
        unreconciled_broker_symbols: Set of symbols in broker but not internal ledger
        internal_position: Internal ledger position metadata (or None)
        current_price: Current market price
        now: Current timestamp
        config: Scale-in config dict with keys:
            - SCALE_IN_ENABLED
            - MAX_ENTRIES_PER_SYMBOL
            - MIN_TIME_BETWEEN_ENTRIES_MINUTES
            - MIN_ADD_PCT_ABOVE_LAST_ENTRY
    
    Returns:
        (action, reason_code)
        - action: BuyAction constant
        - reason_code: BuyBlockReason constant if action is SKIP/BLOCK, else None
    """
    # 1) PREFLIGHT: Block unreconciled symbols (broker has position, internal ledger does not)
    if symbol in unreconciled_broker_symbols:
        logger.warning(
            f"BLOCKING BUY - {symbol} is UNRECONCILED "
            f"(broker position but not in internal ledger after backfill)"
        )
        return BuyAction.BLOCK, BuyBlockReason.UNRECONCILED_BROKER_POSITION
    
    # 2) No internal position → ENTER_NEW (classic flow)
    if internal_position is None:
        logger.info(f"BUY ACTION: {symbol} → ENTER_NEW (no existing internal position)")
        return BuyAction.ENTER_NEW, None
    
    # 3) Internal position exists → evaluate scale-in eligibility
    
    # Check if scale-in is enabled
    if not config.get("SCALE_IN_ENABLED", True):
        logger.info(f"BUY ACTION: {symbol} → SKIP (scale-in disabled)")
        return BuyAction.SKIP, BuyBlockReason.SCALE_IN_DISABLED
    
    # Extract position state
    entry_count = internal_position.get("entry_count", 1)
    last_entry_time_str = internal_position.get("last_entry_time")
    last_entry_price = internal_position.get("last_entry_price")
    
    # Check if we have required state for scale-in decisions
    if last_entry_time_str is None or last_entry_price is None:
        logger.warning(
            f"BUY ACTION: {symbol} → SKIP (insufficient position state for scale-in)"
        )
        return BuyAction.SKIP, BuyBlockReason.INSUFFICIENT_POSITION_STATE
    
    # Parse last entry time
    try:
        last_entry_time = datetime.fromisoformat(last_entry_time_str)
    except Exception as e:
        logger.warning(f"BUY ACTION: {symbol} → SKIP (invalid last_entry_time: {e})")
        return BuyAction.SKIP, BuyBlockReason.INSUFFICIENT_POSITION_STATE
    
    # Check max entries limit
    max_entries = config.get("MAX_ENTRIES_PER_SYMBOL", 4)
    if entry_count >= max_entries:
        logger.info(
            f"BUY ACTION: {symbol} → SKIP (max entries reached: {entry_count}/{max_entries})"
        )
        return BuyAction.SKIP, BuyBlockReason.MAX_ENTRIES_REACHED
    
    # Check cooldown period
    min_time_between_minutes = config.get("MIN_TIME_BETWEEN_ENTRIES_MINUTES", 1440)
    time_since_last_entry = (now - last_entry_time).total_seconds() / 60
    if time_since_last_entry < min_time_between_minutes:
        logger.info(
            f"BUY ACTION: {symbol} → SKIP (entry cooldown: "
            f"{time_since_last_entry:.0f}min < {min_time_between_minutes}min)"
        )
        return BuyAction.SKIP, BuyBlockReason.ENTRY_COOLDOWN
    
    # Check price constraint (optional)
    min_add_pct = config.get("MIN_ADD_PCT_ABOVE_LAST_ENTRY", 0.0)
    if min_add_pct > 0:
        required_price = last_entry_price * (1 + min_add_pct)
        if current_price < required_price:
            logger.info(
                f"BUY ACTION: {symbol} → SKIP (price constraint: "
                f"${current_price:.2f} < ${required_price:.2f})"
            )
            return BuyAction.SKIP, BuyBlockReason.PRICE_NOT_HIGH_ENOUGH
    
    # All checks passed → SCALE_IN approved
    logger.info(
        f"BUY ACTION: {symbol} → SCALE_IN (entry {entry_count + 1}/{max_entries}, "
        f"cooldown OK, price OK)"
    )
    return BuyAction.SCALE_IN, None


class TradingExecutor:
    """
    Orchestrates trading flow.
    
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
        trade_ledger: Optional[TradeLedger] = None,
        ml_trainer: Optional[object] = None,
        ml_risk_threshold: float = 0.5,
    ):
        """
        Initialize trading executor.
        
        Args:
            broker: BrokerAdapter instance (e.g., AlpacaAdapter)
            risk_manager: RiskManager for trade approval
            monitor: SystemGuard for degradation detection (optional)
            logger_instance: ExecutionLogger for audit trail (optional)
            exit_evaluator: ExitEvaluator for exit signals (optional)
            trade_ledger: TradeLedger for completed trade accounting (optional)
            ml_trainer: OfflineTrainer for ML risk filtering (optional, read-only)
            ml_risk_threshold: Probability threshold for blocking trades (0-1)
        """
        self.broker = broker
        self.risk_manager = risk_manager
        self.monitor = monitor
        self.exec_logger = logger_instance or ExecutionLogger()
        self.exit_evaluator = exit_evaluator or ExitEvaluator()
        self.trade_ledger = trade_ledger or TradeLedger()
        self.ml_trainer = ml_trainer
        self.ml_risk_threshold = ml_risk_threshold
        self.trade_permission = get_trade_permission()
        
        # PRODUCTION: Two-phase exit system
        from broker.exit_intent_tracker import ExitIntentTracker
        self.exit_intent_tracker = ExitIntentTracker()
        
        # Safe mode flags (set by main.py after reconciliation)
        self.safe_mode_enabled = False
        self.startup_status = "UNKNOWN"
        self.external_symbols = set()  # Symbols in Alpaca but not in ledger (block duplicate buys)
        
        # Track submitted orders
        self.pending_orders: Dict[str, str] = {}  # order_id -> symbol
        self.filled_orders: Dict[str, float] = {}  # symbol -> fill_price
        
        # Track pending entries (filled buys waiting for exit)
        # Maps symbol -> (order_id, fill_timestamp, fill_price, quantity, confidence, risk_amount)
        self.pending_entries: Dict[str, Tuple[str, str, float, float, float, float]] = {}
        
        # Track order metadata for trade ledger
        # Maps order_id -> (confidence, risk_amount)
        self.order_metadata: Dict[str, Tuple[float, float]] = {}
        
        from config.scope import get_scope
        scope = get_scope()
        logger.info("Trading Executor initialized")
        logger.info(f"  Environment: {scope.env}")
        logger.info(f"  Scope: {scope}")
        logger.info(f"  Broker: {broker.__class__.__name__}")
        logger.info(f"  Risk Manager: {risk_manager.__class__.__name__}")
        logger.info(f"  Monitoring: {'Enabled' if monitor else 'Disabled'}")
        logger.info(f"  Exit Evaluator: {'Enabled' if exit_evaluator else 'Disabled'}")
        logger.info(f"  Trade Ledger: Enabled ({len(self.trade_ledger.trades)} existing trades)")
        logger.info(f"  ML Risk Filter: {'Enabled' if ml_trainer else 'Disabled'}")

    def _apply_manual_halt(self) -> None:
        manual_halt = os.getenv("MANUAL_HALT", "false").strip().lower() in {"1", "true", "yes"}
        if manual_halt:
            self.trade_permission.set_block("MANUAL_HALT", "operator halt enabled")
        else:
            self.trade_permission.clear_block("MANUAL_HALT", "operator halt disabled")

    def _maybe_block_on_risk(self, reason: str) -> None:
        reason_lower = reason.lower()
        triggers = [
            "daily loss limit",
            "max trades per day",
            "consecutive loss limit",
            "portfolio heat limit",
            "per-symbol risk exposure limit",
        ]
        if any(trigger in reason_lower for trigger in triggers):
            self.trade_permission.set_block("RISK_LIMIT_BLOCKED", reason)

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

        # Manual halt (operator controlled)
        self._apply_manual_halt()

        # Runtime trade permission gate (no-trade states)
        if not self.trade_permission.trade_allowed():
            block = self.trade_permission.get_primary_block()
            if block is not None:
                logger.error(
                    f"TRADE_SKIPPED_{block.state} | reason={block.reason} | ts={block.timestamp}"
                )
            return False, None
        
        # SAFE MODE CHECK: Block new entries if safe mode is active
        if self.safe_mode_enabled and self.startup_status != "READY":
            logger.warning(
                f"Safe mode active ({self.startup_status}). "
                f"Blocking new entry for {symbol}. Exits only."
            )
            return False, None
        
        # EVALUATE BUY ACTION (scale-in system)
        from config.settings import (
            SCALE_IN_ENABLED,
            MAX_ENTRIES_PER_SYMBOL,
            MIN_TIME_BETWEEN_ENTRIES_MINUTES,
            MIN_ADD_PCT_ABOVE_LAST_ENTRY,
            MAX_ALLOCATION_PER_SYMBOL_PCT,
        )
        
        # Get current market price for scale-in price checks
        try:
            current_price = self.broker.get_last_trade_price(symbol)
        except Exception as e:
            logger.warning(f"Could not get current price for {symbol}: {e}, using 0.0")
            current_price = 0.0
        
        # Get internal position from ledger (not broker)
        internal_position = None
        if hasattr(self.trade_ledger, '_open_positions') and symbol in self.trade_ledger._open_positions:
            internal_position = self.trade_ledger._open_positions[symbol]
        
        # Evaluate buy action
        buy_action, block_reason = evaluate_buy_action(
            symbol=symbol,
            signal_confidence=confidence,
            unreconciled_broker_symbols=self.external_symbols,
            internal_position=internal_position,
            current_price=current_price,
            now=datetime.now(),
            config={
                "SCALE_IN_ENABLED": SCALE_IN_ENABLED,
                "MAX_ENTRIES_PER_SYMBOL": MAX_ENTRIES_PER_SYMBOL,
                "MIN_TIME_BETWEEN_ENTRIES_MINUTES": MIN_TIME_BETWEEN_ENTRIES_MINUTES,
                "MIN_ADD_PCT_ABOVE_LAST_ENTRY": MIN_ADD_PCT_ABOVE_LAST_ENTRY,
            }
        )
        
        # Handle decision
        if buy_action == BuyAction.BLOCK:
            logger.warning(f"BUY BLOCKED: {symbol} | reason={block_reason}")
            return False, None
        
        if buy_action == BuyAction.SKIP:
            logger.info(f"BUY SKIPPED: {symbol} | reason={block_reason}")
            return False, None
        
        # Proceed with ENTER_NEW or SCALE_IN
        if buy_action == BuyAction.SCALE_IN:
            logger.info(f"Proceeding with SCALE_IN for {symbol}")
        elif buy_action == BuyAction.ENTER_NEW:
            logger.info(f"Proceeding with ENTER_NEW for {symbol}")
        
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

        # Guardrail 1: Skip if an order for this symbol is already pending in this session
        if symbol in self.pending_orders.values():
            logger.info(f"Skipping {symbol} — pending order already submitted in this session")
            return False, None

        # Guardrail 2: Skip if we have a recorded pending entry awaiting exit (REMOVED - now handled by add-on logic above)
        # Note: This was too restrictive - prevented add-on buys. Now using allocation-based logic instead.
        
        # Guardrail 3: ML RISK CHECK (read-only, advisory)
        # If ML model is loaded, use it to filter high-risk trades
        if self.ml_trainer and self.ml_trainer.model is not None:
            ml_risk_score = self.ml_trainer.predict_risk(features)
            if ml_risk_score is not None:
                logger.info(f"ML Risk Score: {ml_risk_score:.3f} (threshold: {self.ml_risk_threshold:.3f})")
                
                if ml_risk_score > self.ml_risk_threshold:
                    logger.warning(
                        f"ML RISK FILTER: Trade {symbol} has high risk probability ({ml_risk_score:.1%}). "
                        f"Blocking entry (rules still allow)."
                    )
                    self.exec_logger.log_error(
                        "ml_risk_filter_applied",
                        f"{symbol}: ML risk score {ml_risk_score:.3f} exceeds threshold {self.ml_risk_threshold:.3f}"
                    )
                    return False, None
                else:
                    logger.info(f"ML RISK FILTER: {symbol} approved (low risk)")
        
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
            self._maybe_block_on_risk(decision.reason)
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
            
            # Track metadata for trade ledger
            self.order_metadata[order_result.order_id] = (confidence, decision.risk_amount)
            
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
                    
                    # Track as pending entry for trade ledger
                    # Store: (order_id, fill_timestamp, fill_price, quantity, confidence, risk_amount)
                    # We'll finalize the Trade when exit fill is confirmed
                    fill_timestamp_iso = fill_time.isoformat()
                    
                    # Get confidence and risk_amount from order metadata
                    confidence, risk_amount = self.order_metadata.get(order_id, (3.0, 0.0))
                    
                    self.pending_entries[symbol] = (
                        order_id,
                        fill_timestamp_iso,
                        fill_price,
                        order_result.filled_qty,
                        confidence,
                        risk_amount,
                    )
                    logger.debug(f"Tracked pending entry for trade ledger: {symbol}")
                    
                    # Clean up order metadata
                    if order_id in self.order_metadata:
                        del self.order_metadata[order_id]
                    
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
        force_immediate: bool = False,
    ) -> bool:
        """
        Execute an exit signal - either immediately or record intent for later.
        
        PRODUCTION: Two-phase swing exit system:
        - SWING exits with urgency='eod': Record intent, execute next day
        - EMERGENCY exits or urgency='immediate': Execute now
        - force_immediate=True: Override two-phase (for manual exits)
        
        Args:
            exit_signal: ExitSignal to execute
            force_immediate: Force immediate execution (default: False)
        
        Returns:
            True if exit submitted OR intent recorded successfully
        """
        from config.settings import SWING_EXIT_TWO_PHASE_ENABLED
        from broker.exit_intent_tracker import ExitIntent, ExitIntentState
        
        symbol = exit_signal.symbol
        
        # Determine if we should execute immediately or record intent
        should_execute_now = (
            force_immediate or
            exit_signal.urgency == 'immediate' or
            not SWING_EXIT_TWO_PHASE_ENABLED
        )
        
        if not should_execute_now:
            # Two-phase: Record exit intent for next-day execution
            logger.info(
                f"TWO-PHASE EXIT: Recording intent for {symbol} "
                f"(urgency={exit_signal.urgency}, type={exit_signal.exit_type.value}). "
                f"Will execute during next execution window."
            )
            
            intent = ExitIntent(
                symbol=symbol,
                state=ExitIntentState.EXIT_PLANNED,
                decision_timestamp=datetime.now().isoformat(),
                decision_date=date.today().isoformat(),
                exit_type=exit_signal.exit_type.value,
                exit_reason=exit_signal.reason,
                entry_date=exit_signal.entry_date.isoformat(),
                holding_days=exit_signal.holding_days,
                confidence=exit_signal.confidence,
                urgency=exit_signal.urgency
            )
            
            self.exit_intent_tracker.add_intent(intent)
            
            # Log intent recorded
            self.exec_logger.log_exit_signal(
                symbol=symbol,
                exit_type=exit_signal.exit_type.value,
                reason=f"INTENT RECORDED: {exit_signal.reason}",
                entry_date=exit_signal.entry_date.isoformat(),
                holding_days=exit_signal.holding_days,
                confidence=exit_signal.confidence,
                urgency=exit_signal.urgency,
            )
            
            return True
        
        # Immediate execution path (original logic)
        try:
            # Get current position
            position = self.broker.get_position(symbol)
            if not position:
                logger.warning(f"No position to close: {symbol}")
                # Clean up intent if exists
                if self.exit_intent_tracker.has_intent(symbol):
                    self.exit_intent_tracker.mark_executed(symbol)
                return False
            
            # Get portfolio position for entry metadata
            portfolio_positions = self.risk_manager.portfolio.open_positions
            if symbol not in portfolio_positions or not portfolio_positions[symbol]:
                logger.warning(f"Position {symbol} not in portfolio state")
                if self.exit_intent_tracker.has_intent(symbol):
                    self.exit_intent_tracker.mark_executed(symbol)
                return False
            
            portfolio_pos = portfolio_positions[symbol][0]  # FIFO
            
            # PRODUCTION: Use limit orders for planned exits, market orders only for emergencies
            order_type = "limit" if exit_signal.urgency == 'eod' else "market"
            current_price = position.current_price
            
            if order_type == "limit":
                # Limit order: Use current price as limit (conservative fill)
                close_result = self.broker.submit_limit_order(
                    symbol=symbol,
                    quantity=abs(position.quantity),
                    side="sell" if position.is_long() else "buy",
                    limit_price=current_price,
                    time_in_force="day",
                )
                logger.info(f"Submitted LIMIT exit order for {symbol} @ {current_price:.2f}")
            else:
                # Market order: Emergency/immediate exits only
                close_result = self.broker.submit_market_order(
                    symbol=symbol,
                    quantity=abs(position.quantity),
                    side="sell" if position.is_long() else "buy",
                    time_in_force="day",
                )
                logger.warning(f"Submitted MARKET exit order for {symbol} (emergency)")
            
            # Calculate PnL
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
            
            # Finalize completed trade in ledger
            self._finalize_trade(
                symbol=symbol,
                exit_order_id=close_result.order_id,
                exit_timestamp=datetime.now().isoformat(),
                exit_price=current_price,
                exit_quantity=abs(position.quantity),
                exit_type=exit_signal.exit_type.value,
                exit_reason=exit_signal.reason,
            )
            
            # Update portfolio state
            self.risk_manager.portfolio.close_trade(
                symbol=symbol,
                exit_date=pd.Timestamp.now(),
                exit_price=current_price,
            )
            
            # Clean up exit intent if it existed
            if self.exit_intent_tracker.has_intent(symbol):
                self.exit_intent_tracker.mark_executed(symbol)
            
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
    
    def execute_pending_exit_intents(self) -> int:
        """
        Execute all pending exit intents (two-phase swing exits).
        
        This is called during the exit execution window (e.g., 5-30 min after market open).
        
        Returns:
            Number of exit orders submitted
        """
        from config.settings import SWING_EXIT_TWO_PHASE_ENABLED
        from broker.exit_intent_tracker import ExitIntentState
        from strategy.exit_evaluator import ExitSignal, ExitType
        
        if not SWING_EXIT_TWO_PHASE_ENABLED:
            logger.debug("Two-phase exits disabled - skipping pending intent execution")
            return 0
        
        pending_intents = self.exit_intent_tracker.get_all_intents(state=ExitIntentState.EXIT_PLANNED)
        
        if not pending_intents:
            logger.debug("No pending exit intents to execute")
            return 0
        
        logger.info("=" * 80)
        logger.info(f"EXECUTING PENDING EXIT INTENTS ({len(pending_intents)} intents)")
        logger.info("=" * 80)
        
        executed_count = 0
        
        for intent in pending_intents:
            try:
                # Convert intent back to ExitSignal for execution
                exit_signal = ExitSignal(
                    symbol=intent.symbol,
                    exit_type=ExitType(intent.exit_type),
                    reason=intent.exit_reason,
                    timestamp=datetime.now(),  # Current execution time
                    entry_date=date.fromisoformat(intent.entry_date),
                    holding_days=intent.holding_days,
                    confidence=intent.confidence or 0,
                    urgency=intent.urgency
                )
                
                # Execute with force_immediate=True to bypass two-phase check
                success = self.execute_exit(exit_signal, force_immediate=True)
                
                if success:
                    executed_count += 1
                    logger.info(
                        f"✓ Executed pending exit: {intent.symbol} "
                        f"(decided: {intent.decision_date}, executed: {date.today().isoformat()})"
                    )
                else:
                    logger.warning(f"Failed to execute pending exit: {intent.symbol}")
            
            except Exception as e:
                logger.error(f"Error executing pending exit for {intent.symbol}: {e}")
        
        logger.info(f"Executed {executed_count}/{len(pending_intents)} pending exit intents")
        return executed_count
    
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
            "trade_permission": self.trade_permission.snapshot(),
        }
    
    def _finalize_trade(
        self,
        symbol: str,
        exit_order_id: str,
        exit_timestamp: str,
        exit_price: float,
        exit_quantity: float,
        exit_type: str,
        exit_reason: str,
    ) -> None:
        """
        Finalize a completed trade in the ledger.
        
        Creates a Trade object from entry and exit fills and adds to ledger.
        This is called AFTER exit fill is confirmed.
        
        Args:
            symbol: Ticker symbol
            exit_order_id: Exit order ID
            exit_timestamp: Exit fill timestamp (ISO format)
            exit_price: Exit fill price
            exit_quantity: Exit fill quantity
            exit_type: "SWING_EXIT" | "EMERGENCY_EXIT"
            exit_reason: Human-readable exit reason
        """
        try:
            # Get entry fill data
            if symbol not in self.pending_entries:
                logger.warning(
                    f"Cannot finalize trade for {symbol}: no pending entry found. "
                    f"This can happen if system restarted between entry and exit."
                )
                return
            
            entry_order_id, entry_timestamp, entry_price, entry_quantity, confidence, risk_amount = self.pending_entries[symbol]
            
            # Create completed trade
            trade = create_trade_from_fills(
                symbol=symbol,
                entry_order_id=entry_order_id,
                entry_fill_timestamp=entry_timestamp,
                entry_fill_price=entry_price,
                entry_fill_quantity=entry_quantity,
                exit_order_id=exit_order_id,
                exit_fill_timestamp=exit_timestamp,
                exit_fill_price=exit_price,
                exit_fill_quantity=exit_quantity,
                exit_type=exit_type,
                exit_reason=exit_reason,
                confidence=confidence,
                risk_amount=risk_amount,
                fees=0.0,  # Alpaca paper trading has no fees
            )
            
            # Add to ledger
            self.trade_ledger.add_trade(trade)
            
            # Remove from pending entries
            del self.pending_entries[symbol]
            
        except Exception as e:
            # Logging failures must not block execution
            logger.error(f"Failed to finalize trade for {symbol}: {e}")
