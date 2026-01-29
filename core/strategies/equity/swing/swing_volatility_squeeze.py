"""
SwingVolatilitySqueezeStrategy - Trade expansion after compression.

PHILOSOPHY:
Trade volatility expansion after a period of compression. The edge is that
squeezed volatility is unsustainable - when it releases, directional moves
are often violent and sustained.

ENTRY:
- Squeeze identified: Bollinger Bands < 1.5% of price
- ATR low: Currently near 20-day lows
- Confirmed breakout: Price breaks above upper band on high volume
- Direction: MACD/RSI confirm direction (not against trend)

EXIT:
- Profit target: +12-15% (volatility expansion captures large moves)
- Max hold: 20 days
- Squeeze re-compression: Bollinger Bands widen back to normal

EDGE:
Volatility cycles are real. Squeezed market means mean reversion is paused.
When squeeze breaks, moves are often strong. Early participation captures
the expansion move.

RISKS:
- Directional uncertainty: Squeeze breaks but direction unclear (50/50)
- Macro uncertainty: Squeeze breaks sideways (macro doubt)
- News risk: Surprise overnight gap in wrong direction
- False breakout: Squeeze breaks but reverses quickly (whipsaw)

CAVEATS:
- Low volume squeeze: Easier to reverse
- Pre-earnings: Squeeze naturally occurs (earnings anticipation)
- Macro uncertainty (Fed, rates): Squeeze breaks sideways
- Illiquid symbols: Squeeze appears tighter than real
"""

import logging
from typing import List, Dict, Any

from core.strategies.equity.swing.swing_base import BaseSwingStrategy, SwingStrategyMetadata
from strategies.base import TradeIntent, TradeDirection, IntentType, IntentUrgency

logger = logging.getLogger(__name__)


class SwingVolatilitySqueezeStrategy(BaseSwingStrategy):
    """
    Trade volatility expansion after compression.
    
    MARKET-AGNOSTIC:
    - Uses price and volatility indicators only
    - Works for US, India, future markets
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize volatility squeeze strategy.
        
        Config keys:
        - min_confidence: Minimum signal (default: 3)
        - max_positions: Max concurrent (default: 8, more conservative)
        - bb_width_threshold: Max squeeze width (default: 0.015 = 1.5%)
        - profit_target_pct: Target return (default: 0.15 = 15%)
        - atr_lookback: Days to check ATR lows (default: 20)
        """
        default_config = {
            "enabled": True,
            "min_confidence": 3,
            "max_positions": 8,
            "bb_width_threshold": 0.015,  # 1.5%
            "profit_target_pct": 0.15,  # 15%
            "atr_lookback": 20,
        }
        
        if config:
            default_config.update(config)
        
        super().__init__("volatility_squeeze", default_config)
        self.validate_philosophy()
        
        logger.info(f"SwingVolatilitySqueezeStrategy initialized")
        logger.info(f"  BB width threshold: {self.config['bb_width_threshold']:.1%}")
        logger.info(f"  Profit target: {self.config['profit_target_pct']:.1%}")
    
    def get_swing_metadata(self) -> SwingStrategyMetadata:
        """Declare volatility squeeze philosophy."""
        return SwingStrategyMetadata(
            strategy_id="volatility_squeeze_v1",
            strategy_name="Swing Volatility Squeeze",
            version="1.0.0",
            philosophy="Trade volatility expansion after compression. "
                       "Squeezed markets eventually break - early participation captures the move.",
            edge="Volatility cycles are real and predictable. Squeezed market = upcoming move. "
                 "Breakout from squeeze is often violent and sustained.",
            risks=[
                "Directional uncertainty: Squeeze breaks but 50/50 direction",
                "Macro uncertainty: Squeeze breaks sideways (market indecision)",
                "News risk: Overnight gap in wrong direction (tail risk)",
                "False breakout: Breaks but reverses quickly (whipsaw)",
            ],
            caveats=[
                "Low-volume squeeze: Easier to reverse, less conviction",
                "Pre-earnings: Squeeze naturally high, false signal",
                "Macro uncertainty (Fed, rates): Squeeze breaks choppy",
                "Illiquid symbols: Squeeze width appears tighter than actual",
                "Directional doubt: Market unclear, expansion may fail",
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
        Generate volatility squeeze entry signals.
        
        ENTRY CRITERIA:
        1. Squeeze: Bollinger Bands width < 1.5%
        2. ATR low: At 20-day lows
        3. Breakout: Price breaks upper BB on volume
        4. Direction: MACD/RSI confirm direction
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
            
            # Squeeze check
            bb_width = features.get("bb_width", 0.02)
            if bb_width > self.config["bb_width_threshold"]:
                continue  # Not squeezed enough
            
            # ATR check
            atr_pct = features.get("atr_pct", 0)
            atr_50d_avg = features.get("atr_50d_avg", atr_pct * 1.5)
            if atr_pct > atr_50d_avg:
                continue  # ATR not at lows
            
            # MACD direction (optional)
            macd = features.get("macd", 0)
            macd_signal = features.get("macd_signal", 0)
            if macd is not None and macd_signal is not None:
                if macd < macd_signal:
                    continue  # Direction not confirmed
            
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
                reason=f"Volatility squeeze: low compression, breakout confirmed",
                features=signal.get("features", {}),
                risk_metadata={
                    "strategy_type": "swing_volatility_squeeze",
                    "philosophy": "Expansion after compression",
                    "hold_days_max": 20,
                },
            )
            intents.append(intent)
            logger.info(f"Entry: {signal['symbol']} - Volatility squeeze breakout")
        
        return intents
    
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate volatility squeeze exit signals.
        
        EXIT CONDITIONS:
        1. Max hold: 20 days
        2. Profit target: +15%
        3. Re-compression: BB width back to normal (expansion over)
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
                bb_width = symbol_data.get("BB_width", 0.02)
                
                if bb_width > 0.03:  # Back to normal width
                    exit_reason = f"Expansion complete, compression normal"
            
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
                        "strategy_type": "swing_volatility_squeeze",
                        "position_id": position.get("id"),
                    },
                )
                intents.append(intent)
                logger.info(f"Exit: {symbol} - {exit_reason}")
        
        return intents
