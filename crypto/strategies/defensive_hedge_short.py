"""
DefensiveHedgeShortStrategy - Short hedge positions in downturns.

PHILOSOPHY:
- Protective short positions to reduce portfolio heat during crises
- Used as hedge, NOT primary strategy
- Time-limited hooks (max 1-3 days) and size-limited (max 1% of portfolio)

SUPPORTED REGIMES: RISK_OFF, PANIC ONLY (strict gating enforced)
FORBIDDEN REGIMES: RISK_ON, NEUTRAL (offensive phases)

EDGE:
- Offsets losses during market crashes
- Quick exit once crisis passes
- Low cost if not triggered

RISKS:
- Can be very wrong if market reverses quickly (need tight stops)
- Size must be capped to avoid over-hedging
- Time limits prevent "stuck" hedges
- STRICT gating: only in RISK_OFF/PANIC
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


class DefensiveHedgeShortStrategy(Strategy):
    """Defensive short hedge for crisis periods (RISK_OFF/PANIC only)."""
    
    def __init__(self):
        config = {
            "enabled": True,
            "max_position_size_pct": 1.0,  # Max 1% of capital
            "max_holding_days": 3,  # Auto-exit after 3 days
            "short_trigger_drawdown_pct": 0.10,  # Trigger if >10% portfolio drawdown
            "stop_loss_pct": 5.0,  # Exit short if price up 5%
        }
        super().__init__("defensive_hedge_short", config)
        self.description = "Defensive short hedge (RISK_OFF/PANIC only, time/size limited)"
    
    def supported_regimes(self) -> Set[str]:
        """STRICT GATING: Only RISK_OFF and PANIC."""
        return {"risk_off", "panic"}
    
    def generate_signal(
        self,
        feature_context: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        budget: float,
        regime_state: str,
    ) -> Signal:
        """Generate defensive short signal with strict regime/size/time gating."""
        # CRITICAL GATING #1: Regime check
        if regime_state not in self.supported_regimes():
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason=f"REGIME GATING: DefensiveHedge requires RISK_OFF/PANIC, got {regime_state}"
            )
        
        # CRITICAL GATING #2: Size cap
        max_size = budget * (self.config['max_position_size_pct'] / 100)
        
        # Extract portfolio drawdown
        portfolio_drawdown = portfolio_state.get('current_drawdown_pct', 0)
        days_in_position = portfolio_state.get('hedge_days_held', 0)
        
        # CRITICAL GATING #3: Time limit - auto exit after max days
        if days_in_position >= self.config['max_holding_days']:
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason=f"TIME LIMIT: Hedge held for {days_in_position} days (max {self.config['max_holding_days']}), EXIT"
            )
        
        # Trigger short hedge if significant drawdown
        if abs(portfolio_drawdown) > self.config['short_trigger_drawdown_pct']:
            confidence = min(abs(portfolio_drawdown) / 0.20, 1.0)  # Scale by severity
            return Signal(
                intent="SHORT",
                suggested_size=max_size,  # Use capped size
                confidence=confidence,
                reason=f"Portfolio drawdown {portfolio_drawdown:.2%}, hedge triggered, size capped at {max_size}"
            )
        
        return Signal("FLAT", 0, 0, "Drawdown below threshold, no hedge needed")
    
    def generate_entry_intents(self, market_data: Dict, portfolio_state: Dict) -> list:
        return []
    
    def generate_exit_intents(self, positions: list, market_data: Dict) -> list:
        return []
    
    def get_metadata(self):
        from strategies.registry import StrategyMetadata
        return StrategyMetadata(
            name="defensive_hedge_short",
            version="1.0",
            supported_markets=["global"],
            supported_modes=["crypto"],
            instrument_type="crypto",
        )
    
    def get_supported_instruments(self) -> list:
        return ["crypto"]
