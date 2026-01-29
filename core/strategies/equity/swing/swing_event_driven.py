"""
SwingEventDrivenStrategy - Trade predictable post-event behavior.

PHILOSOPHY:
Trade predictable mean-reversion behavior following company events. The edge
is that events create mispricing opportunities where trader emotion exceeds
fundamental justification.

ENTRY:
- Post-event setup: Entry 1-2 days after event (earnings, FDA, etc.)
- Overreaction signal: Price moved > 2x normal daily move
- Contrarian position: Price moved opposite to fundamental direction
- Trend still valid: SMA20 > SMA200 (longer-term trend intact)

EXIT:
- Profit target: +6-8% (event reversion capture)
- Max hold: 20 days
- Event justification: If event was fundamental, longer hold needed

EDGE:
Events create emotional trading that overshoots fundamentals. Waiting 1-2
days allows initial panic to settle while thesis remains valid.

RISKS:
- Overnight gaps: Gap against position before setup completes
- Ambiguous events: Market interpretation unclear (earnings beat but forward guidance weak)
- Tail risk: Event was worse than initially priced
- Follow-on events: Second event compounds original move

CAVEATS:
- Too-early entry: Jump in before emotional reaction settles
- Misclassified event: What looked like overreaction was justified
- Company-specific tail risk: Event signals deeper problems
- No trend confirmation: Trade without confirmed trend support
"""

import logging
from typing import List, Dict, Any

from core.strategies.equity.swing.swing_base import BaseSwingStrategy, SwingStrategyMetadata
from strategies.base import TradeIntent, TradeDirection, IntentType, IntentUrgency

logger = logging.getLogger(__name__)


class SwingEventDrivenStrategy(BaseSwingStrategy):
    """
    Trade post-event mean reversion.
    
    MARKET-AGNOSTIC:
    - Uses price, volume, and event classification only
    - Works for US, India, future markets (with different events)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize event-driven strategy.
        
        Config keys:
        - min_confidence: Minimum signal (default: 3)
        - max_positions: Max concurrent (default: 5, conservative)
        - event_types: List of event types to trade (default: all common)
        - days_after_event_min: Wait before entry (default: 1)
        - days_after_event_max: Latest entry (default: 2)
        - price_move_threshold: Overreaction threshold (default: 2.0x normal daily)
        - profit_target_pct: Target return (default: 0.08 = 8%)
        """
        default_config = {
            "enabled": True,
            "min_confidence": 3,
            "max_positions": 5,
            "event_types": [
                "earnings",
                "fda_approval",
                "product_launch",
                "acquisition",
                "guidance_cut",
            ],
            "days_after_event_min": 1,
            "days_after_event_max": 2,
            "price_move_threshold": 2.0,  # 2x normal daily move
            "profit_target_pct": 0.08,
        }
        
        if config:
            default_config.update(config)
        
        super().__init__("event_driven", default_config)
        self.validate_philosophy()
        
        logger.info(f"SwingEventDrivenStrategy initialized")
        logger.info(f"  Event types: {self.config['event_types']}")
        logger.info(f"  Days after event: {self.config['days_after_event_min']}-{self.config['days_after_event_max']}")
    
    def get_swing_metadata(self) -> SwingStrategyMetadata:
        """Declare event-driven philosophy."""
        return SwingStrategyMetadata(
            strategy_id="event_driven_v1",
            strategy_name="Swing Event Driven",
            version="1.0.0",
            philosophy="Trade post-event mean reversion. "
                       "Events create emotional overshoots that revert when sentiment settles.",
            edge="Events cause overreaction and mispricing. Waiting 1-2 days allows "
                 "initial panic to settle while fundamental thesis remains intact.",
            risks=[
                "Overnight gaps: Gap against position before setup fully established",
                "Ambiguous events: Market interpretation unclear (mixed signals)",
                "Tail risk: Event was worse than initially priced (fundamental)",
                "Follow-on events: Second event compounds original move direction",
            ],
            caveats=[
                "Too-early entry: Emotional reaction not yet settled",
                "Misclassified event: Overreaction was actually justified reversal",
                "Company-specific risk: Event signals deeper, ongoing problems",
                "No trend support: Relying only on event, not macro trend",
                "Earnings surprise: Guidance cut harder than earnings miss",
            ],
            supported_modes=["swing"],
            supported_instruments=["equity"],
            supported_markets=["us", "india"],
        )
    
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate event-driven entry signals.
        
        ENTRY CRITERIA:
        1. Post-event: 1-2 days after event
        2. Overreaction: Price moved > 2x normal daily move
        3. Contrarian: Entry opposite to emotional direction
        4. Trend: SMA20 > SMA200 (trend still valid)
        """
        intents = []
        
        signals = market_data.get("signals", [])
        current_positions = portfolio_state.get("positions", [])
        owned_symbols = {pos["symbol"] for pos in current_positions}
        
        max_positions = self.config["max_positions"]
        available_slots = max_positions - len(current_positions)
        
        if available_slots <= 0:
            return intents
        
        min_confidence = self.config["min_confidence"]
        
        qualified_signals = []
        for signal in signals:
            if signal.get("confidence", 0) < min_confidence:
                continue
            
            if signal["symbol"] in owned_symbols:
                continue
            
            features = signal.get("features", {})
            
            # Event check
            event_type = features.get("event_type")
            if event_type not in self.config["event_types"]:
                continue  # Not a tracked event
            
            # Days since event
            days_since_event = features.get("days_since_event", 0)
            if not (
                self.config["days_after_event_min"] <= days_since_event <= self.config["days_after_event_max"]
            ):
                continue  # Not in setup window
            
            # Overreaction check
            price_move_pct = abs(features.get("price_move_pct", 0))
            normal_daily_move = features.get("normal_daily_move_pct", 0.02)
            
            if price_move_pct < (normal_daily_move * self.config["price_move_threshold"]):
                continue  # Move not large enough to be overreaction
            
            # Trend check (optional)
            sma20 = features.get("sma20")
            sma200 = features.get("sma200")
            if sma20 and sma200:
                if sma20 < sma200:
                    continue  # Downtrend, avoid event-driven
            
            qualified_signals.append(signal)
        
        qualified_signals = qualified_signals[:available_slots]
        
        for signal in qualified_signals:
            event_type = signal.get("features", {}).get("event_type", "unknown")
            intent = TradeIntent(
                strategy_name=self.name,
                instrument_type="equity",
                symbol=signal["symbol"],
                direction=TradeDirection.LONG,
                intent_type=IntentType.ENTRY,
                urgency=IntentUrgency.NEXT_OPEN,
                confidence=signal.get("confidence"),
                reason=f"Event-driven: post-{event_type} reversion setup",
                features=signal.get("features", {}),
                risk_metadata={
                    "strategy_type": "swing_event_driven",
                    "philosophy": "Post-event mean reversion",
                    "event_type": event_type,
                    "hold_days_max": 20,
                },
            )
            intents.append(intent)
            logger.info(f"Entry: {signal['symbol']} - Event-driven ({event_type})")
        
        return intents
    
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate event-driven exit signals.
        
        EXIT CONDITIONS:
        1. Max hold: 20 days
        2. Profit target: +8%
        3. Event thesis broken: No reversion after 5 days (setup failed)
        """
        intents = []
        
        current_prices = market_data.get("prices", {})
        
        for position in positions:
            symbol = position["symbol"]
            entry_price = position["entry_price"]
            current_price = current_prices.get(symbol)
            
            if current_price is None:
                continue
            
            return_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            exit_reason = None
            urgency = IntentUrgency.EOD
            
            holding_days = (
                position.get("current_date") - position["entry_date"]
            ).days if isinstance(position.get("current_date"), type(position["entry_date"])) else 0
            
            if holding_days >= 20:
                exit_reason = f"Max hold ({holding_days} days)"
                urgency = IntentUrgency.NEXT_OPEN
            
            elif return_pct >= self.config["profit_target_pct"]:
                exit_reason = f"Profit target (+{return_pct:.1%})"
            
            elif holding_days > 5 and return_pct < 0:
                exit_reason = f"Event thesis broken (no reversion after 5 days)"
                urgency = IntentUrgency.EOD
            
            if exit_reason:
                intent = TradeIntent(
                    strategy_name=self.name,
                    instrument_type="equity",
                    symbol=symbol,
                    direction=TradeDirection.LONG,
                    intent_type=IntentType.EXIT,
                    urgency=urgency,
                    quantity=position.get("quantity"),
                    reason=exit_reason,
                    features={
                        "holding_days": holding_days,
                        "return_pct": return_pct,
                    },
                    risk_metadata={
                        "strategy_type": "swing_event_driven",
                        "position_id": position.get("id"),
                    },
                )
                intents.append(intent)
                logger.info(f"Exit: {symbol} - {exit_reason}")
        
        return intents
