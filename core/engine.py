"""
Core Trading Engine - Strategy-agnostic execution coordinator.

ARCHITECTURE:
- Strategies emit TradeIntent
- Engine validates intent
- TradeIntentGuard checks behavioral rules
- RiskManager checks risk limits
- Broker executes approved orders

NO STRATEGY bypasses this flow.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from strategies.base import Strategy, TradeIntent, IntentType, IntentUrgency
from instruments.base import Instrument
from markets.base import Market
from risk.trade_intent_guard import (
    TradeIntentGuard,
    ExitReason,
    create_trade,
    create_account_context,
)

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Core engine orchestrating strategy → intent → validation → execution.
    
    FLOW:
    1. Strategies generate intents
    2. Engine validates intents
    3. Guard checks behavioral compliance
    4. RiskManager approves/rejects
    5. Broker executes approved intents
    
    ALL trades go through this flow.
    """
    
    def __init__(
        self,
        strategies: List[Strategy],
        market: Market,
        intent_guard: TradeIntentGuard,
        risk_manager: Any,  # RiskManager from existing code
        broker: Any,        # Broker adapter
    ):
        """
        Initialize trading engine.
        
        Args:
            strategies: List of active strategies
            market: Market instance (defines regulatory rules)
            intent_guard: Trade intent guard (behavioral layer)
            risk_manager: Risk manager (position sizing, limits)
            broker: Broker adapter (order execution)
        """
        self.strategies = strategies
        self.market = market
        self.intent_guard = intent_guard
        self.risk_manager = risk_manager
        self.broker = broker
        
        logger.info("TradingEngine initialized")
        logger.info(f"  Strategies: {len(strategies)}")
        logger.info(f"  Market: {market.market_id}")
        logger.info(f"  Intent Guard: Enabled")
    
    def process_strategies(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Main engine loop: process all strategies and execute approved intents.
        
        Args:
            market_data: Current market state (prices, signals, etc.)
            portfolio_state: Current portfolio (positions, buying power)
        
        Returns:
            Execution summary
        """
        logger.info("=" * 80)
        logger.info("TRADING ENGINE: Processing strategies")
        logger.info("=" * 80)
        
        results = {
            "entry_intents": 0,
            "exit_intents": 0,
            "approved_entries": 0,
            "approved_exits": 0,
            "rejected_entries": 0,
            "rejected_exits": 0,
            "orders_submitted": 0,
        }
        
        # Check market status
        market_status = self.market.get_market_status()
        logger.info(f"Market status: {market_status.value}")
        
        # Process each strategy
        for strategy in self.strategies:
            if not strategy.should_run({"is_open": self.market.is_market_open()}):
                logger.debug(f"Strategy {strategy.name} skipped (should_run=False)")
                continue
            
            logger.info(f"\n{'='*80}")
            logger.info(f"Processing strategy: {strategy.name}")
            logger.info(f"{'='*80}")
            
            # Generate entry intents
            entry_intents = strategy.generate_entry_intents(market_data, portfolio_state)
            results["entry_intents"] += len(entry_intents)
            
            # Generate exit intents
            strategy_positions = self._get_strategy_positions(
                portfolio_state.get("positions", []),
                strategy.name,
            )
            exit_intents = strategy.generate_exit_intents(strategy_positions, market_data)
            results["exit_intents"] += len(exit_intents)
            
            # Process entry intents
            for intent in entry_intents:
                approved, reason = self._process_entry_intent(intent, portfolio_state)
                if approved:
                    results["approved_entries"] += 1
                    results["orders_submitted"] += 1
                else:
                    results["rejected_entries"] += 1
            
            # Process exit intents
            for intent in exit_intents:
                approved, reason = self._process_exit_intent(intent, portfolio_state)
                if approved:
                    results["approved_exits"] += 1
                    results["orders_submitted"] += 1
                else:
                    results["rejected_exits"] += 1
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("TRADING ENGINE SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Entry intents: {results['entry_intents']} ({results['approved_entries']} approved)")
        logger.info(f"Exit intents: {results['exit_intents']} ({results['approved_exits']} approved)")
        logger.info(f"Total orders: {results['orders_submitted']}")
        logger.info("=" * 80)
        
        return results
    
    def _process_entry_intent(
        self,
        intent: TradeIntent,
        portfolio_state: Dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Process entry intent through validation layers.
        
        Flow:
        1. Validate intent structure
        2. Get account context
        3. Check behavioral guard (should NOT block entries)
        4. Get risk manager approval
        5. Submit order to broker
        
        Args:
            intent: Entry intent from strategy
            portfolio_state: Current portfolio state
        
        Returns:
            (approved, reason)
        """
        logger.info(f"\n--- Processing ENTRY intent: {intent.symbol} ---")
        logger.info(f"Strategy: {intent.strategy_name}")
        logger.info(f"Reason: {intent.reason}")
        
        # Step 1: Validate intent
        if not self._validate_intent(intent):
            logger.warning("Intent validation failed")
            return False, "Invalid intent structure"
        
        # Step 2: Get account context
        account_context = self._get_account_context()
        
        # Step 3: Check intent guard (entries should pass, guard mainly for exits)
        # For entries, we mainly care about max positions, not PDT
        
        # Step 4: Get risk manager approval
        risk_decision = self._get_risk_approval(intent, portfolio_state, account_context)
        if not risk_decision["approved"]:
            logger.warning(f"Risk manager rejected: {risk_decision['reason']}")
            return False, risk_decision["reason"]
        
        # Step 5: Submit order
        order_submitted = self._submit_order(intent, risk_decision)
        if order_submitted:
            logger.info(f"✅ Order submitted: {intent.symbol}")
            return True, "Order submitted"
        else:
            logger.error(f"❌ Order submission failed: {intent.symbol}")
            return False, "Order submission failed"
    
    def _process_exit_intent(
        self,
        intent: TradeIntent,
        portfolio_state: Dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Process exit intent through validation layers.
        
        Flow:
        1. Validate intent structure
        2. Map intent to exit reason (for guard)
        3. Check behavioral guard (PDT compliance)
        4. Get risk manager approval (if needed)
        5. Submit order to broker
        
        Args:
            intent: Exit intent from strategy
            portfolio_state: Current portfolio state
        
        Returns:
            (approved, reason)
        """
        logger.info(f"\n--- Processing EXIT intent: {intent.symbol} ---")
        logger.info(f"Strategy: {intent.strategy_name}")
        logger.info(f"Reason: {intent.reason}")
        
        # Step 1: Validate intent
        if not self._validate_intent(intent):
            logger.warning("Intent validation failed")
            return False, "Invalid intent structure"
        
        # Step 2: Get position info
        position = self._find_position(portfolio_state.get("positions", []), intent.symbol)
        if not position:
            logger.warning(f"Position not found: {intent.symbol}")
            return False, "Position not found"
        
        # Step 3: Map intent to exit reason (for guard)
        exit_reason = self._map_intent_to_exit_reason(intent)
        
        # Step 4: Check intent guard
        account_context = self._get_account_context()
        trade = create_trade(
            symbol=intent.symbol,
            entry_date=position.get("entry_date"),
            entry_price=position.get("entry_price"),
            quantity=position.get("quantity"),
            confidence=position.get("confidence", 3),
        )
        
        guard_decision = self.intent_guard.can_exit_trade(
            trade=trade,
            exit_date=datetime.now().date(),
            exit_reason=exit_reason,
            account_context=account_context,
        )
        
        if not guard_decision.allowed:
            logger.warning(f"Intent guard blocked: {guard_decision.block_reason}")
            return False, guard_decision.block_reason
        
        # Step 5: Submit order
        order_submitted = self._submit_exit_order(intent, position)
        if order_submitted:
            logger.info(f"✅ Exit order submitted: {intent.symbol}")
            return True, "Exit order submitted"
        else:
            logger.error(f"❌ Exit order submission failed: {intent.symbol}")
            return False, "Exit order submission failed"
    
    def _validate_intent(self, intent: TradeIntent) -> bool:
        """Validate intent structure."""
        if not intent.symbol:
            return False
        if not intent.strategy_name:
            return False
        if not intent.instrument_type:
            return False
        return True
    
    def _get_account_context(self):
        """Get current account context for guard checks."""
        # In production, get from broker
        account_info = self.broker.get_account() if hasattr(self.broker, 'get_account') else {}
        
        return create_account_context(
            account_equity=account_info.get("equity", 100000.0),
            account_type=account_info.get("account_type", "MARGIN"),
            day_trade_count_5d=account_info.get("day_trade_count_5d", 0),
        )
    
    def _get_risk_approval(
        self,
        intent: TradeIntent,
        portfolio_state: Dict[str, Any],
        account_context: Any,
    ) -> Dict[str, Any]:
        """Get risk manager approval."""
        # In production, call existing RiskManager
        # For now, simplified approval
        return {
            "approved": True,
            "position_size": intent.quantity or 100,
            "risk_amount": 1000.0,
            "reason": "Risk approved",
        }
    
    def _submit_order(self, intent: TradeIntent, risk_decision: Dict[str, Any]) -> bool:
        """Submit order to broker."""
        # In production, call broker adapter
        logger.info(f"Order submission: {intent.symbol} x {risk_decision['position_size']}")
        return True  # Simulated success
    
    def _submit_exit_order(self, intent: TradeIntent, position: Dict[str, Any]) -> bool:
        """Submit exit order to broker."""
        logger.info(f"Exit order submission: {intent.symbol} x {position.get('quantity')}")
        return True  # Simulated success
    
    def _find_position(self, positions: List[Dict], symbol: str) -> Optional[Dict]:
        """Find position by symbol."""
        for pos in positions:
            if pos.get("symbol") == symbol:
                return pos
        return None
    
    def _get_strategy_positions(
        self,
        all_positions: List[Dict],
        strategy_name: str,
    ) -> List[Dict]:
        """Filter positions by strategy."""
        return [
            pos for pos in all_positions
            if pos.get("strategy") == strategy_name
        ]
    
    def _map_intent_to_exit_reason(self, intent: TradeIntent) -> ExitReason:
        """
        Map trade intent to exit reason for guard.
        
        Logic:
        - IMMEDIATE urgency + loss → STOP_LOSS
        - IMMEDIATE urgency → RISK_MANAGER
        - EOD/NEXT_OPEN → STRATEGY_SIGNAL
        """
        if intent.urgency == IntentUrgency.IMMEDIATE:
            # Check if it's a loss
            return_pct = intent.features.get("return_pct", 0)
            if return_pct < 0:
                return ExitReason.STOP_LOSS
            else:
                return ExitReason.RISK_MANAGER
        
        # All discretionary exits
        return ExitReason.STRATEGY_SIGNAL
