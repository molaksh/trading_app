"""
VolatilityScaledSwingStrategy - Swing-trading with volatility scaling.

PHILOSOPHY:
- Swing trades scaled to volatility regime
- Smaller position sizes in high-vol, larger in low-vol
- 2-5 day holding periods with profit/loss targets

SUPPORTED REGIMES: NEUTRAL, RISK_ON
FORBIDDEN REGIMES: RISK_OFF, PANIC (volatility too high)

EDGE:
- Adapts position sizing to market conditions
- Tighter stops in high-vol regimes
- Works in stable (NEUTRAL) and bull (RISK_ON) markets
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


class VolatilityScaledSwingStrategy(Strategy):
    """Swing strategy with volatility-based position sizing."""
    
    def __init__(self):
        config = {
            "enabled": True,
            "lookback_periods": 14,
            "vol_threshold_high": 0.04,  # 4% daily volatility
            "vol_threshold_low": 0.01,   # 1% daily volatility
            "profit_target_pct": 5.0,
            "loss_limit_pct": 2.0,
        }
        super().__init__("volatility_scaled_swing", config)
        self.description = "Swing trading with volatility scaling"
    
    def supported_regimes(self) -> Set[str]:
        return {"neutral", "risk_on"}
    
    def generate_signal(
        self,
        feature_context: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        budget: float,
        regime_state: str,
    ) -> Signal:
        if regime_state not in self.supported_regimes():
            return Signal("FLAT", 0, 0, f"Regime {regime_state} not supported")
        
        volatility = feature_context.get('realized_volatility', 0.02)
        mean_reversion_signal = feature_context.get('mean_reversion_score', 0)
        
        # Scale position size inversely to volatility
        vol_scale = self._compute_vol_scale(volatility)
        
        if mean_reversion_signal > 0.6:
            size = budget * vol_scale * 0.02  # 2% base allocation
            return Signal(
                intent="LONG",
                suggested_size=size,
                confidence=min(mean_reversion_signal, 1.0),
                reason=f"Mean reversion signal={mean_reversion_signal:.2f}, vol_scale={vol_scale:.2f}"
            )
        
        return Signal("FLAT", 0, 0, "No swing signal")
    
    def _compute_vol_scale(self, volatility: float) -> float:
        """Scale position size by volatility (inverse relationship)."""
        if volatility > self.config['vol_threshold_high']:
            return 0.5  # 50% of normal size in high vol
        elif volatility > self.config['vol_threshold_low']:
            return 1.0  # Normal size
        else:
            return 1.5  # 150% in low vol
    
    def generate_entry_intents(self, market_data: Dict, portfolio_state: Dict) -> list:
        return []
    
    def generate_exit_intents(self, positions: list, market_data: Dict) -> list:
        return []
    
    def get_metadata(self):
        from strategies.registry import StrategyMetadata
        return StrategyMetadata(
            name="volatility_scaled_swing",
            version="1.0",
            supported_markets=["global"],
            supported_modes=["crypto"],
            instrument_type="crypto",
        )
    
    def get_supported_instruments(self) -> list:
        return ["crypto"]
