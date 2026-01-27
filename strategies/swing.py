"""
Swing Strategy - Entry/exit logic for multi-day equity positions.

STRATEGY CHARACTERISTICS:
- Instrument: Equity (stocks)
- Timeframe: 2-20 days hold period
- Direction: Long-only (can be extended to short)
- Execution: Next market open (no intraday)
- Risk: 1-2% per trade

This is an ADAPTER that wraps existing scoring/feature logic
into the new Strategy interface.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

from strategies.base import (
    Strategy,
    TradeIntent,
    TradeDirection,
    IntentType,
    IntentUrgency,
)

logger = logging.getLogger(__name__)


class SwingEquityStrategy(Strategy):
    """
    Swing trading strategy for equities.
    
    ENTRY CRITERIA (from existing rule_scorer.py):
    - Close > SMA200 (uptrend)
    - SMA20 slope > 0 (momentum)
    - Pullback < 5% (entry timing)
    - Volume ratio > 1.2 (confirmation)
    - ATR < 3% (volatility filter)
    
    EXIT CRITERIA:
    - Max holding period: 20 days
    - Profit target: +10%
    - Trend invalidation: Close < SMA200
    - Emergency: Catastrophic loss
    """
    
    def __init__(self, name: str = "swing_equity", config: Dict[str, Any] = None):
        """
        Initialize swing strategy.
        
        Config keys:
        - min_confidence: Minimum score to generate entry (default: 3)
        - max_positions: Max concurrent positions (default: 10)
        - hold_days_min: Minimum hold (default: 2)
        - hold_days_max: Maximum hold (default: 20)
        - profit_target_pct: Profit target (default: 0.10)
        """
        default_config = {
            "enabled": True,
            "min_confidence": 3,
            "max_positions": 10,
            "hold_days_min": 2,
            "hold_days_max": 20,
            "profit_target_pct": 0.10,
            "use_trend_invalidation": True,
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(name, default_config)
        
        logger.info(f"SwingEquityStrategy initialized: {self.name}")
        logger.info(f"  Min confidence: {self.config['min_confidence']}")
        logger.info(f"  Max positions: {self.config['max_positions']}")
        logger.info(f"  Hold period: {self.config['hold_days_min']}-{self.config['hold_days_max']} days")
    
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate swing entry intents.
        
        Process:
        1. Filter candidates by confidence threshold
        2. Exclude already-owned symbols
        3. Limit by max_positions
        4. Emit intents (quantity determined by risk manager)
        
        Args:
            market_data: Dict with 'signals' key containing scored symbols
            portfolio_state: Dict with 'positions' and 'buying_power'
        
        Returns:
            List of entry intents
        """
        intents = []
        
        # Get scored signals (from existing screener output)
        signals = market_data.get("signals", [])
        if not signals:
            logger.debug("No signals in market_data")
            return intents
        
        # Current positions
        current_positions = portfolio_state.get("positions", [])
        owned_symbols = {pos["symbol"] for pos in current_positions}
        
        # Max positions check
        max_positions = self.config["max_positions"]
        available_slots = max_positions - len(current_positions)
        
        if available_slots <= 0:
            logger.info(f"Max positions reached ({len(current_positions)}/{max_positions})")
            return intents
        
        # Filter by confidence
        min_confidence = self.config["min_confidence"]
        qualified_signals = [
            sig for sig in signals
            if sig.get("confidence", 0) >= min_confidence
            and sig["symbol"] not in owned_symbols
        ]
        
        # Limit to available slots
        qualified_signals = qualified_signals[:available_slots]
        
        # Create intents
        for signal in qualified_signals:
            intent = TradeIntent(
                strategy_name=self.name,
                instrument_type="equity",
                symbol=signal["symbol"],
                direction=TradeDirection.LONG,
                intent_type=IntentType.ENTRY,
                urgency=IntentUrgency.NEXT_OPEN,
                confidence=signal.get("confidence"),
                reason=f"Swing entry: confidence={signal.get('confidence')}",
                features=signal.get("features", {}),
                risk_metadata={
                    "strategy_type": "swing",
                    "hold_days_max": self.config["hold_days_max"],
                },
            )
            intents.append(intent)
            logger.info(f"Entry intent: {signal['symbol']} (confidence={signal.get('confidence')})")
        
        return intents
    
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate swing exit intents.
        
        Exit conditions (checked in order):
        1. Max holding period exceeded (FORCE EXIT)
        2. Profit target hit (TAKE PROFIT)
        3. Trend invalidation (STOP LOSS)
        
        Args:
            positions: List of positions managed by this strategy
            market_data: Current prices and indicator data
        
        Returns:
            List of exit intents
        """
        intents = []
        
        current_prices = market_data.get("prices", {})
        eod_data = market_data.get("eod_data", {})  # Full OHLC + indicators
        
        for position in positions:
            symbol = position["symbol"]
            entry_date = position["entry_date"]
            entry_price = position["entry_price"]
            current_price = current_prices.get(symbol)
            
            if current_price is None:
                logger.warning(f"No price data for {symbol}, skipping exit check")
                continue
            
            # Calculate metrics
            holding_days = (datetime.now().date() - entry_date).days
            return_pct = (current_price - entry_price) / entry_price
            
            # Exit reason tracking
            exit_reason = None
            urgency = IntentUrgency.EOD  # Default: exit at end of day
            
            # Check 1: Max holding period
            if holding_days >= self.config["hold_days_max"]:
                exit_reason = f"Max hold period ({holding_days} days)"
                urgency = IntentUrgency.NEXT_OPEN
            
            # Check 2: Profit target
            elif return_pct >= self.config["profit_target_pct"]:
                exit_reason = f"Profit target hit ({return_pct:.1%})"
                urgency = IntentUrgency.EOD
            
            # Check 3: Trend invalidation (if enabled)
            elif self.config["use_trend_invalidation"]:
                symbol_data = eod_data.get(symbol, {})
                close = symbol_data.get("Close", current_price)
                sma_200 = symbol_data.get("SMA_200")
                
                if sma_200 and close < sma_200:
                    exit_reason = "Trend invalidation (close < SMA200)"
                    urgency = IntentUrgency.EOD
            
            # Generate intent if exit condition met
            if exit_reason:
                intent = TradeIntent(
                    strategy_name=self.name,
                    instrument_type="equity",
                    symbol=symbol,
                    direction=TradeDirection.LONG,  # Closing long
                    intent_type=IntentType.EXIT,
                    urgency=urgency,
                    quantity=position.get("quantity"),
                    reason=exit_reason,
                    features={
                        "holding_days": holding_days,
                        "return_pct": return_pct,
                        "entry_price": entry_price,
                        "current_price": current_price,
                    },
                    risk_metadata={
                        "exit_type": "swing_exit",
                        "position_id": position.get("id"),
                    },
                )
                intents.append(intent)
                logger.info(f"Exit intent: {symbol} - {exit_reason}")
        
        return intents
    
    def get_strategy_type(self) -> str:
        """Strategy type identifier."""
        return "swing"
    
    def get_supported_instruments(self) -> List[str]:
        """Supported instrument types."""
        return ["equity"]
    
    def should_run(self, market_state: Dict[str, Any]) -> bool:
        """
        Swing strategy runs:
        - Entry generation: After market close (for next open)
        - Exit evaluation: During market hours or EOD
        
        Override default to allow after-hours entry generation.
        """
        if not self.enabled:
            return False
        
        # Always allow exit checks during market hours
        if market_state.get("is_open", False):
            return True
        
        # Allow entry generation after market close
        # (for next-day execution)
        return True  # Swing can run anytime
