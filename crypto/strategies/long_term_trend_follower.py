"""
LongTermTrendFollowerStrategy - Pure trend-following strategy for crypto.

PHILOSOPHY:
- Follow established long-term trends without deviation
- Entry on trend confirmation, exit on trend break
- Higher holding periods than volatility-scaled swing

SUPPORTED REGIMES: RISK_ON, NEUTRAL
FORBIDDEN REGIMES: RISK_OFF, PANIC (too conservative for this strategy)

EDGE:
- Captures extended trending moves in crypto
- Lower transaction costs via reduced trading frequency
- Works well in RISK_ON (bull) and NEUTRAL (sideways with uptrend)

RISKS:
- Whipsaws in choppy/mean-reverting markets (RISK_OFF)
- Late entries on extended trends
- Panic crashes can trigger false trend breaks
"""

from typing import Dict, Any, Optional, Set
from dataclasses import dataclass
from enum import Enum
from strategies.base import Strategy, TradeIntent, IntentType, IntentUrgency, TradeDirection


class Regime(Enum):
    RISK_ON = "risk_on"
    NEUTRAL = "neutral"
    RISK_OFF = "risk_off"
    PANIC = "panic"


@dataclass
class Signal:
    """Simple signal for strategy output."""
    intent: str  # LONG, SHORT, FLAT
    suggested_size: float  # Units or notional
    confidence: float  # 0..1
    reason: str


class LongTermTrendFollowerStrategy(Strategy):
    """Pure trend-following strategy for crypto markets."""
    
    def __init__(self):
        """Initialize long-term trend follower."""
        config = {
            "enabled": True,
            "fast_ma_periods": 20,
            "slow_ma_periods": 50,
            "trend_strength_threshold": 0.5,
            "max_position_size_pct": 3.0,  # 3% of capital per signal
        }
        super().__init__("long_term_trend_follower", config)
        self.description = "Long-term trend-following strategy for crypto"
    
    def supported_regimes(self) -> Set[str]:
        """Regimes where this strategy is allowed to run."""
        return {"risk_on", "neutral"}
    
    def generate_signal(
        self,
        feature_context: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        budget: float,
        regime_state: str,
    ) -> Signal:
        """
        Generate trend-following signal.
        
        Args:
            feature_context: Computed features (returns, ATR, trend_strength, etc.)
            portfolio_state: Current positions, buying power, etc.
            budget: Allocated capital for this strategy
            regime_state: Current regime (risk_on, neutral, risk_off, panic)
        
        Returns:
            Signal with intent, size, confidence, reason
        """
        # Check regime gating
        if regime_state not in self.supported_regimes():
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason=f"Regime {regime_state} not supported (allowed: {self.supported_regimes()})"
            )
        
        # Extract features
        trend_strength = feature_context.get('trend_strength', 0)
        price_momentum = feature_context.get('momentum', 0)
        
        # Simple logic: trend strength + momentum confirmation
        if trend_strength > self.config['trend_strength_threshold'] and price_momentum > 0:
            size = budget * (self.config['max_position_size_pct'] / 100)
            confidence = min(trend_strength, 1.0)
            return Signal(
                intent="LONG",
                suggested_size=size,
                confidence=confidence,
                reason=f"Trend strength={trend_strength:.2f}, momentum={price_momentum:.2f}"
            )
        elif trend_strength > self.config['trend_strength_threshold'] and price_momentum < 0:
            # Downtrend
            size = budget * (self.config['max_position_size_pct'] / 100)
            confidence = min(trend_strength, 1.0)
            return Signal(
                intent="SHORT",
                suggested_size=size,
                confidence=confidence,
                reason=f"Downtrend, strength={trend_strength:.2f}, momentum={price_momentum:.2f}"
            )
        
        return Signal(
            intent="FLAT",
            suggested_size=0,
            confidence=0,
            reason="Trend not strong enough"
        )
    
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> list:
        """Implement base class method."""
        return []
    
    def generate_exit_intents(self, positions: list, market_data: Dict[str, Any]) -> list:
        """Implement base class method."""
        return []
    
    def get_metadata(self):
        """Get strategy metadata."""
        from strategies.registry import StrategyMetadata
        return StrategyMetadata(
            name="long_term_trend_follower",
            version="1.0",
            supported_markets=["global"],
            supported_modes=["crypto"],
            instrument_type="crypto",
        )
    
    def get_supported_instruments(self) -> list:
        """Return list of supported instrument types."""
        return ["crypto"]
