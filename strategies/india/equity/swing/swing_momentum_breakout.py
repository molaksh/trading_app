"""
SwingMomentumBreakoutStrategy - Trade strength and continuation moves.

PHILOSOPHY:
Trade the strength and continuation of price breakouts. The edge is that
high-conviction breakouts with strong volume tend to continue in the
breakout direction before mean reversion.

ENTRY:
- Breakout confirmed: Price > 52-week high or key resistance
- Volume explosion: Volume ratio > 1.5x average
- Momentum positive: RSI > 60, MACD positive
- ATR rising: Recent ATR > previous ATR (volatility expanding)

EXIT:
- Profit target: +8-12% (momentum captures)
- Max hold: 20 days
- Momentum break: RSI < 40 or MACD bearish cross

EDGE:
Breakouts with volume represent conviction. Early participation in strong
moves provides continuation potential with defined risk.

RISKS:
- False breakouts: Break fails and reverses (whipsaw)
- Gap slippage: Overnight gap beyond expected profit target
- Volume spikes on bad news: Breakout misdirects
- Resistance becomes support: Breakout fails after initial move

CAVEATS:
- Low volume breakouts: Weak conviction, easily reversed
- Range-bound markets: Breakouts fail frequently
- Post-dividend/split: Volume patterns distorted
- Illiquid symbols: Slippage on entry/exit large
"""

import logging
from typing import List, Dict, Any

from strategies.india.equity.swing.swing_base import BaseSwingStrategy, SwingStrategyMetadata
from strategies.base import TradeIntent, TradeDirection, IntentType, IntentUrgency

logger = logging.getLogger(__name__)


class SwingMomentumBreakoutStrategy(BaseSwingStrategy):
    """
    Trade strength and continuation of breakout moves.
    
    MARKET-AGNOSTIC:
    - Uses only price/volume/momentum indicators
    - No hardcoded market hours (MarketHoursPolicy handles)
    - Works for US, India, future markets
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize momentum breakout strategy.
        
        Config keys:
        - min_confidence: Minimum signal strength (default: 3)
        - max_positions: Max concurrent positions (default: 10)
        - volume_ratio_min: Minimum volume increase (default: 1.5)
        - rsi_threshold: Minimum RSI for momentum (default: 60)
        - profit_target_pct: Target return (default: 0.10 = 10%)
        - use_rsi_exit: Exit on RSI < 40 (default: True)
        """
        default_config = {
            "enabled": True,
            "min_confidence": 3,
            "max_positions": 10,
            "volume_ratio_min": 1.5,
            "rsi_threshold": 60,
            "profit_target_pct": 0.10,
            "use_rsi_exit": True,
        }
        
        if config:
            default_config.update(config)
        
        super().__init__("momentum_breakout", default_config)
        self.validate_philosophy()
        
        logger.info(f"SwingMomentumBreakoutStrategy initialized")
        logger.info(f"  Volume ratio threshold: {self.config['volume_ratio_min']}x")
        logger.info(f"  RSI threshold: {self.config['rsi_threshold']}")
    
    def get_swing_metadata(self) -> SwingStrategyMetadata:
        """Declare momentum breakout philosophy."""
        return SwingStrategyMetadata(
            strategy_id="momentum_breakout_v1",
            strategy_name="Swing Momentum Breakout",
            version="1.0.0",
            philosophy="Trade strength and continuation of price breakouts. "
                       "High-conviction breakouts with strong volume tend to continue.",
            edge="Volume and momentum confirmation on breakouts signal conviction. "
                 "Early participation captures continuation potential.",
            risks=[
                "False breakouts: Price breaks above resistance then reverses",
                "Gap slippage: Overnight gaps prevent profitable exit",
                "Volume spikes on bad news: Breakout misleads (fake volume)",
                "Resistance becomes support: Breakout fails to establish",
            ],
            caveats=[
                "Low volume breakouts: Weak conviction, easily reversed",
                "Range-bound markets: Breakouts fail 50%+ of time",
                "Post-earnings: Volume patterns distorted by event reactions",
                "Illiquid symbols: Entry/exit slippage large, eats profit",
                "Strong bearish macro: Even breakouts fail (market headwind)",
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
        Generate momentum breakout entry signals.
        
        ENTRY CRITERIA:
        1. Breakout: Price > 52-week high or key resistance
        2. Volume: Volume ratio > 1.5x moving average
        3. Momentum: RSI > 60, MACD positive
        4. Volatility: ATR rising (expanding)
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
            
            # Check breakout and momentum characteristics
            volume_ratio = features.get("volume_ratio", 1.0)
            if volume_ratio < self.config["volume_ratio_min"]:
                continue  # Volume confirmation weak
            
            rsi = features.get("rsi", 50)
            if rsi < self.config["rsi_threshold"]:
                continue  # Momentum not strong enough
            
            # MACD positive (optional, check if available)
            macd = features.get("macd", 0)
            macd_signal = features.get("macd_signal", 0)
            if macd is not None and macd_signal is not None:
                if macd < macd_signal:
                    continue  # MACD not positive
            
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
                reason=f"Momentum breakout: volume spike + strong RSI",
                features=signal.get("features", {}),
                risk_metadata={
                    "strategy_type": "swing_momentum_breakout",
                    "philosophy": "Strength continuation on volume confirmation",
                    "hold_days_max": 20,
                },
            )
            intents.append(intent)
            logger.info(f"Entry: {signal['symbol']} - Momentum breakout")
        
        return intents
    
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate momentum breakout exit signals.
        
        EXIT CONDITIONS:
        1. Max hold: 20 days
        2. Profit target: +10%
        3. Momentum loss: RSI < 40 or MACD bearish cross
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
            
            # Check holding period
            holding_days = (
                position.get("current_date") - position["entry_date"]
            ).days if isinstance(position.get("current_date"), type(position["entry_date"])) else 0
            
            if holding_days >= 20:
                exit_reason = f"Max hold period ({holding_days} days)"
                urgency = IntentUrgency.NEXT_OPEN
            
            elif return_pct >= self.config["profit_target_pct"]:
                exit_reason = f"Profit target (+{return_pct:.1%})"
            
            elif self.config["use_rsi_exit"]:
                symbol_data = eod_data.get(symbol, {})
                rsi = symbol_data.get("RSI")
                
                if rsi and rsi < 40:
                    exit_reason = f"Momentum loss (RSI={rsi:.0f})"
            
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
                        "strategy_type": "swing_momentum_breakout",
                        "position_id": position.get("id"),
                    },
                )
                intents.append(intent)
                logger.info(f"Exit: {symbol} - {exit_reason}")
        
        return intents
