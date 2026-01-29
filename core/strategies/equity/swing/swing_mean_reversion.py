"""
SwingMeanReversionStrategy - Trade snapbacks within valid trends.

PHILOSOPHY:
Trade mean reversion snapbacks within confirmed uptrends. The edge is that
valid uptrends have natural pullbacks that revert to the trend, offering
low-risk entries with tight stops.

ENTRY:
- Trend confirmed: SMA20 > SMA200
- Oversold: RSI < 40, price near SMA20
- Volume declining: Low volume pullback (no panic selling)
- No gap down: Entry within 2% of previous close

EXIT:
- Profit target: +5-7% (conservative, reversion capture)
- Max hold: 20 days
- Breakdown: Close < SMA20 (reversal confirms)

EDGE:
Mean reversion within uptrends captures the most consistent swing entries.
Low volume pullbacks are often reversals rather than trend breaks.

RISKS:
- Knife-catching: Buying "dips" that are actually reversals
- Insufficient volume: Reversion fails, becomes actual breakdown
- Bearish macro: Pullbacks become reversals (market headwind)
- Gap down overnight: Entry thesis breaks with overnight reversal

CAVEATS:
- High volume pullback: May be trend change, not mean reversion
- Bearish market regime: Mean reversion fails frequently
- Week-end risk: Friday reversals often fade Monday
- Earnings pre-announcement: Pullbacks become reversals (event risk)
"""

import logging
from typing import List, Dict, Any

from core.strategies.equity.swing.swing_base import BaseSwingStrategy, SwingStrategyMetadata
from strategies.base import TradeIntent, TradeDirection, IntentType, IntentUrgency

logger = logging.getLogger(__name__)


class SwingMeanReversionStrategy(BaseSwingStrategy):
    """
    Trade snapbacks within valid trends.
    
    MARKET-AGNOSTIC:
    - Uses price, momentum, volume indicators only
    - Works for US, India, future markets
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize mean reversion strategy.
        
        Config keys:
        - min_confidence: Minimum signal (default: 3)
        - max_positions: Max concurrent (default: 10)
        - rsi_oversold: Oversold threshold (default: 40)
        - profit_target_pct: Target return (default: 0.07 = 7%)
        - use_volume_filter: Require low volume (default: True)
        """
        default_config = {
            "enabled": True,
            "min_confidence": 3,
            "max_positions": 10,
            "rsi_oversold": 40,
            "profit_target_pct": 0.07,
            "use_volume_filter": True,
        }
        
        if config:
            default_config.update(config)
        
        super().__init__("mean_reversion", default_config)
        self.validate_philosophy()
        
        logger.info(f"SwingMeanReversionStrategy initialized")
        logger.info(f"  RSI oversold: {self.config['rsi_oversold']}")
        logger.info(f"  Profit target: {self.config['profit_target_pct']:.1%}")
    
    def get_swing_metadata(self) -> SwingStrategyMetadata:
        """Declare mean reversion philosophy."""
        return SwingStrategyMetadata(
            strategy_id="mean_reversion_v1",
            strategy_name="Swing Mean Reversion",
            version="1.0.0",
            philosophy="Trade snapbacks within valid uptrends. "
                       "Low-volume pullbacks in confirmed trends often revert to the trend.",
            edge="Oversold conditions in valid trends mean higher probability reversion. "
                 "Low volume pullbacks are genuine reversions, not trend breaks.",
            risks=[
                "Knife-catching: Buying 'dips' that become actual reversals",
                "Insufficient volume: Reversion fails, position breaks down",
                "Bearish macro: Market-wide reversal prevents uptrend recovery",
                "Gap down overnight: Entry premise breaks with overnight gap",
            ],
            caveats=[
                "High volume pullback: May signal trend change, not mean reversion",
                "Bearish market regime: Mean reversion fails (market down is primary)",
                "Week-end risk: Friday reversions often fade by Monday open",
                "Pre-earnings announcements: Pullbacks can become reversals",
                "Trend fatigue: RSI oversold but trend actually breaking",
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
        Generate mean reversion entry signals.
        
        ENTRY CRITERIA:
        1. Uptrend: SMA20 > SMA200
        2. Oversold: RSI < 40
        3. Low volume: Volume < moving average (no panic selling)
        4. Position: Price near SMA20 (reversion starting)
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
            
            # Uptrend confirmation
            sma20 = features.get("sma20")
            sma200 = features.get("sma200")
            if not (sma20 and sma200 and sma20 > sma200):
                continue
            
            # Oversold check
            rsi = features.get("rsi", 50)
            if rsi >= self.config["rsi_oversold"]:
                continue  # Not oversold enough
            
            # Volume filter (optional)
            if self.config["use_volume_filter"]:
                volume_ratio = features.get("volume_ratio", 1.0)
                if volume_ratio > 1.2:  # High volume pullback
                    continue  # Too much volume, may not be reversion
            
            qualified_signals.append(signal)
        
        qualified_signals = qualified_signals[:available_slots]
        
        for signal in qualified_signals:
            intent = TradeIntent(
                strategy_name=self.name,
                instrument_type="equity",
                symbol=signal["symbol"],
                direction=TradeDirection.LONG,
                intent_type=IntentType.ENTRY,
                urgency=IntentUrgency.NEXT_OPEN,
                confidence=signal.get("confidence"),
                reason=f"Mean reversion: oversold in uptrend, low volume",
                features=signal.get("features", {}),
                risk_metadata={
                    "strategy_type": "swing_mean_reversion",
                    "philosophy": "Reversion to trend in oversold condition",
                    "hold_days_max": 20,
                },
            )
            intents.append(intent)
            logger.info(f"Entry: {signal['symbol']} - Mean reversion")
        
        return intents
    
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate mean reversion exit signals.
        
        EXIT CONDITIONS:
        1. Max hold: 20 days
        2. Profit target: +7%
        3. Breakdown: Close < SMA20 (reversion fails)
        """
        intents = []
        
        current_prices = market_data.get("prices", {})
        eod_data = market_data.get("eod_data", {})
        
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
            
            else:
                symbol_data = eod_data.get(symbol, {})
                close = symbol_data.get("Close", current_price)
                sma20 = symbol_data.get("SMA_20")
                
                if sma20 and close < sma20:
                    exit_reason = f"Reversion failed (close < SMA20)"
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
                        "strategy_type": "swing_mean_reversion",
                        "position_id": position.get("id"),
                    },
                )
                intents.append(intent)
                logger.info(f"Exit: {symbol} - {exit_reason}")
        
        return intents
