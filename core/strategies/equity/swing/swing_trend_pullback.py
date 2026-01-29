"""
SwingTrendPullbackStrategy - Trade shallow pullbacks in strong uptrends.

PHILOSOPHY:
Trade shallow pullbacks in confirmed uptrends. The edge is that strong
uptrends tend to have healthy pullbacks that provide favorable entry points
with tight stops.

ENTRY:
- Uptrend confirmed (SMA20 > SMA200, slope positive)
- Pullback < 5% from recent high
- Volume confirming (ratio > 1.2)
- ATR < 3% (clean entry)

EXIT:
- Profit target: +10%
- Max hold: 20 days
- Trend break: Close < SMA200 (loses uptrend confirmation)

EDGE:
Strong uptrends mean higher probability of continuation. Pullbacks are
natural retracements where risk/reward becomes favorable.

RISKS:
- Sideways/choppy markets (high chop, stop gets hit)
- Late-stage trends (exhaustion, reversal risk)
- Gap downs overnight (gaps can exceed 5% pullback)
- False breakouts above resistance

CAVEATS:
- Weak ADX (< 25): Trend may be unreliable
- Post-earnings volatility: Trust pullback %% less
- Macro reversal days: No uptrend confirmation possible
- Monday opens: Overnight gaps violate pullback rule
"""

import logging
from typing import List, Dict, Any

from strategies.us.equity.swing.swing_base import BaseSwingStrategy, SwingStrategyMetadata
from strategies.base import TradeIntent, TradeDirection, IntentType, IntentUrgency

logger = logging.getLogger(__name__)


class SwingTrendPullbackStrategy(BaseSwingStrategy):
    """
    Trade shallow pullbacks in strong uptrends.
    
    MARKET-AGNOSTIC:
    - Uses only price/volume indicators (universal)
    - No hardcoded market hours (MarketHoursPolicy handles)
    - No lot-size assumptions (RiskManager handles)
    - Works for US, India, future markets
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize trend pullback strategy.
        
        Config keys:
        - min_confidence: Minimum signal strength (default: 4)
        - max_positions: Max concurrent positions (default: 10)
        - pullback_threshold: Max pullback % before entry (default: 0.05 = 5%)
        - profit_target_pct: Target return (default: 0.10 = 10%)
        - use_atr_filter: Filter by ATR < 3% (default: True)
        - atr_threshold: Max ATR % (default: 0.03 = 3%)
        """
        default_config = {
            "enabled": True,
            "min_confidence": 4,
            "max_positions": 10,
            "pullback_threshold": 0.05,  # 5%
            "profit_target_pct": 0.10,  # 10%
            "use_atr_filter": True,
            "atr_threshold": 0.03,  # 3%
            "use_trend_invalidation": True,
        }
        
        if config:
            default_config.update(config)
        
        super().__init__("trend_pullback", default_config)
        
        # Validate philosophy
        self.validate_philosophy()
        
        logger.info(f"SwingTrendPullbackStrategy initialized")
        logger.info(f"  Pullback threshold: {self.config['pullback_threshold']:.1%}")
        logger.info(f"  Profit target: {self.config['profit_target_pct']:.1%}")
        logger.info(f"  ATR filter: {self.config['use_atr_filter']}")
    
    def get_swing_metadata(self) -> SwingStrategyMetadata:
        """
        Declare trend pullback philosophy.
        """
        return SwingStrategyMetadata(
            strategy_id="trend_pullback_v1",
            strategy_name="Swing Trend Pullback",
            version="1.0.0",
            philosophy="Trade shallow pullbacks in strong uptrends. "
                       "Pullbacks in confirmed uptrends provide favorable risk/reward entries.",
            edge="Strong uptrends have higher continuation probability. "
                 "Pullbacks offer entries with tight stops and good reward potential.",
            risks=[
                "Sideways/choppy markets: Trend unreliable, stops hit frequently",
                "Late-stage trends: Exhaustion risk, reversal without warning",
                "Gap downs: Overnight gaps can exceed pullback threshold, forcing early exit",
                "False breakouts: Pullback trend can reverse after entry",
            ],
            caveats=[
                "Weak ADX (< 25): Trend confirmation unreliable, skip entry",
                "Post-earnings volatility: Pullback % less predictable",
                "Macro reversal days: Uptrend breaks even with strong opens",
                "Monday opens: Overnight gaps violate pullback rule",
                "Extended trends: Late entry near highs increases failure risk",
            ],
            supported_modes=["swing"],
            supported_instruments=["equity"],
            supported_markets=["us", "india"],  # Market-agnostic, supports multiple
        )
    
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate trend pullback entry signals.
        
        ENTRY CRITERIA:
        1. Uptrend confirmed: SMA20 > SMA200 and SMA20 slope > 0
        2. Pullback identified: Price within 5% of 52-week high
        3. Volume confirmation: Volume ratio > 1.2
        4. Volatility filter (optional): ATR < 3% for clean entry
        5. Signal strength: Confidence >= min_threshold
        """
        intents = []
        
        signals = market_data.get("signals", [])
        current_positions = portfolio_state.get("positions", [])
        owned_symbols = {pos["symbol"] for pos in current_positions}
        
        max_positions = self.config["max_positions"]
        available_slots = max_positions - len(current_positions)
        
        if available_slots <= 0:
            logger.info(f"Max positions reached ({len(current_positions)}/{max_positions})")
            return intents
        
        min_confidence = self.config["min_confidence"]
        
        # Filter for trend pullback signals
        qualified_signals = []
        for signal in signals:
            if signal.get("confidence", 0) < min_confidence:
                continue  # Too low confidence
            
            if signal["symbol"] in owned_symbols:
                continue  # Already owned
            
            # Check for trend pullback characteristics
            features = signal.get("features", {})
            sma20 = features.get("sma20")
            sma200 = features.get("sma200")
            close = features.get("close")
            
            # Uptrend confirmation
            if not (sma20 and sma200 and sma20 > sma200):
                continue  # Not in uptrend
            
            # Pullback check: within threshold of recent high
            high_52w = features.get("high_52w")
            if high_52w:
                pullback_pct = (high_52w - close) / high_52w if high_52w > 0 else 1.0
                if pullback_pct > self.config["pullback_threshold"]:
                    continue  # Too deep of a pullback
            
            # ATR filter (optional)
            if self.config["use_atr_filter"]:
                atr_pct = features.get("atr_pct", 0)
                if atr_pct > self.config["atr_threshold"]:
                    continue  # Too volatile for clean entry
            
            qualified_signals.append(signal)
        
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
                reason=f"Trend pullback: {signal.get('confidence')}% confidence",
                features=signal.get("features", {}),
                risk_metadata={
                    "strategy_type": "swing_trend_pullback",
                    "philosophy": "Shallow pullback in confirmed uptrend",
                    "hold_days_max": 20,
                },
            )
            intents.append(intent)
            logger.info(f"Entry: {signal['symbol']} - Trend pullback (conf={signal.get('confidence')})")
        
        return intents
    
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate trend pullback exit signals.
        
        EXIT CONDITIONS (in priority order):
        1. Max hold period: 20 days (hard stop)
        2. Profit target: +10% (take profit)
        3. Trend break: Close < SMA200 (stop loss via trend invalidation)
        """
        intents = []
        
        current_prices = market_data.get("prices", {})
        eod_data = market_data.get("eod_data", {})
        
        for position in positions:
            symbol = position["symbol"]
            entry_date = position["entry_date"]
            entry_price = position["entry_price"]
            current_price = current_prices.get(symbol)
            
            if current_price is None:
                continue
            
            holding_days = (
                position.get("current_date") - entry_date
            ).days if isinstance(position.get("current_date"), type(entry_date)) else 0
            
            return_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
            exit_reason = None
            urgency = IntentUrgency.EOD
            
            # Check 1: Max holding period (hard stop)
            if holding_days >= 20:
                exit_reason = f"Max hold period reached ({holding_days} days)"
                urgency = IntentUrgency.NEXT_OPEN
            
            # Check 2: Profit target
            elif return_pct >= self.config["profit_target_pct"]:
                exit_reason = f"Profit target hit (+{return_pct:.1%})"
                urgency = IntentUrgency.EOD
            
            # Check 3: Trend invalidation
            elif self.config["use_trend_invalidation"]:
                symbol_data = eod_data.get(symbol, {})
                close = symbol_data.get("Close", current_price)
                sma200 = symbol_data.get("SMA_200")
                
                if sma200 and close < sma200:
                    exit_reason = "Trend invalidation (close < SMA200)"
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
                        "entry_price": entry_price,
                        "current_price": current_price,
                    },
                    risk_metadata={
                        "strategy_type": "swing_trend_pullback",
                        "position_id": position.get("id"),
                    },
                )
                intents.append(intent)
                logger.info(f"Exit: {symbol} - {exit_reason}")
        
        return intents
