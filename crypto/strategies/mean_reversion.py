"""
MeanReversionStrategy - Reversion to mean in stable markets.

PHILOSOPHY:
- Exploit temporary price deviations from moving average
- Entry when price > 1.5*ATR from MA, exit on reversion
- Only in NEUTRAL regime (sideways market)

SUPPORTED REGIMES: NEUTRAL ONLY (strict gating enforced)
FORBIDDEN REGIMES: RISK_ON (uptrend), RISK_OFF (downtrend), PANIC (crashes)

EDGE:
- Works well in range-bound, low-trend markets
- Quick reversions = high win rate
- Low holding periods (1-3 days)

RISKS:
- Fails in strong trends (gets whipsawed)
- MUST be disabled in RISK_OFF/PANIC
- Regime gating is critical safety control
"""

from typing import Dict, Any, Set
from dataclasses import dataclass
from strategies.base import Strategy


@dataclass
class Signal:
    intent: str
    suggested_size: float
    confidence: float
    reason: str


class MeanReversionStrategy(Strategy):
    """Mean reversion strategy - NEUTRAL regime only."""
    
    def __init__(self):
        config = {
            "enabled": True,
            "atr_multiplier": 1.5,
            "ma_period": 20,
            "max_position_size_pct": 2.0,
            "holding_days_max": 3,
        }
        super().__init__("mean_reversion", config)
        self.description = "Mean reversion strategy (NEUTRAL regime only)"
    
    def supported_regimes(self) -> Set[str]:
        """STRICT GATING: Only NEUTRAL regime."""
        return {"neutral"}
    
    def generate_signal(
        self,
        feature_context: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        budget: float,
        regime_state: str,
    ) -> Signal:
        """Generate mean reversion signal with strict regime gating."""
        # CRITICAL GATING: If not NEUTRAL, REJECT
        if regime_state != "neutral":
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason=f"REGIME GATING: MeanReversion requires NEUTRAL, got {regime_state}"
            )
        
        # Extract mean reversion metrics
        distance_from_ma = feature_context.get('distance_from_ma', 0)
        ma_value = feature_context.get('ma_20', 0)
        current_price = feature_context.get('current_price', 0)
        
        atr = feature_context.get('atr', 0)
        threshold = atr * self.config['atr_multiplier']
        
        # Price too far above MA -> SHORT
        if distance_from_ma > threshold and current_price > ma_value:
            size = budget * (self.config['max_position_size_pct'] / 100)
            return Signal(
                intent="SHORT",
                suggested_size=size,
                confidence=0.7,
                reason=f"Price {distance_from_ma:.2f} above MA, distance>{threshold:.2f}"
            )
        
        # Price too far below MA -> LONG
        if distance_from_ma < -threshold and current_price < ma_value:
            size = budget * (self.config['max_position_size_pct'] / 100)
            return Signal(
                intent="LONG",
                suggested_size=size,
                confidence=0.7,
                reason=f"Price {distance_from_ma:.2f} below MA, distance<-{threshold:.2f}"
            )
        
        return Signal("FLAT", 0, 0, "Price within normal range")
    
    def generate_entry_intents(self, market_data: Dict, portfolio_state: Dict) -> list:
        return []
    
    def generate_exit_intents(self, positions: list, market_data: Dict) -> list:
        return []
    
    def get_metadata(self):
        from strategies.registry import StrategyMetadata
        return StrategyMetadata(
            name="mean_reversion",
            version="1.0",
            supported_markets=["global"],
            supported_modes=["crypto"],
            instrument_type="crypto",
        )
    
    def get_supported_instruments(self) -> list:
        return ["crypto"]
