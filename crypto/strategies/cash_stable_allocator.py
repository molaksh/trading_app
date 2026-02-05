"""
CashStableAllocatorStrategy - Preserve capital and manage cash allocation.

PHILOSOPHY:
- De-risks portfolio during downturns
- Increases cash in RISK_OFF/PANIC, deploys in RISK_ON
- Can force position flattening if equity drawdown too severe

SUPPORTED REGIMES: All (RISK_ON, NEUTRAL, RISK_OFF, PANIC)
SPECIAL BEHAVIOR: Overrides other strategies in severe stress

EDGE:
- Systematic capital preservation
- Avoids "underwater" positions
- Manages cash/equity ratio dynamically

RISKS:
- Can miss rebound if too aggressive on cash
- Needs coordinated with other strategies
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


class CashStableAllocatorStrategy(Strategy):
    """Cash allocation and stability manager (all regimes)."""
    
    def __init__(self):
        config = {
            "enabled": True,
            "risk_on_target_cash_pct": 20,   # Keep 20% cash in bull markets
            "neutral_target_cash_pct": 30,   # Keep 30% in sideways
            "risk_off_target_cash_pct": 50,  # Keep 50% in downturns
            "panic_target_cash_pct": 70,     # Keep 70% in crashes
            "max_equity_drawdown_force_flat": 0.25,  # Force flat if >25% DD
        }
        super().__init__("cash_stable_allocator", config)
        self.description = "Cash allocation and portfolio stability manager"
    
    def supported_regimes(self) -> Set[str]:
        """Works in all regimes."""
        return {"risk_on", "neutral", "risk_off", "panic"}
    
    def generate_signal(
        self,
        feature_context: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        budget: float,
        regime_state: str,
    ) -> Signal:
        """Generate cash allocation signal."""
        # Get current cash and equity
        current_cash_pct = portfolio_state.get('cash_pct', 50)
        equity_drawdown = abs(portfolio_state.get('current_drawdown_pct', 0))
        
        # Determine target cash based on regime
        target_cash = self._get_target_cash_pct(regime_state)
        
        # EXTREME GATING: Force flat if severe drawdown
        if equity_drawdown > self.config['max_equity_drawdown_force_flat']:
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0.95,
                reason=f"EMERGENCY: Drawdown {equity_drawdown:.2%} > {self.config['max_equity_drawdown_force_flat']:.2%}, force FLAT"
            )
        
        # If cash below target, signal to reduce risk (sell/close positions)
        if current_cash_pct < target_cash:
            shortfall = target_cash - current_cash_pct
            return Signal(
                intent="REDUCE",  # Signal to risk manager to reduce exposure
                suggested_size=shortfall / 100 * budget,  # Amount to move to cash
                confidence=0.6 + (shortfall / 50 * 0.4),  # Higher confidence with larger shortfall
                reason=f"Cash {current_cash_pct}% below target {target_cash}%, need to raise {shortfall}%"
            )
        
        # If cash above target, can be more aggressive
        if current_cash_pct > target_cash:
            excess = current_cash_pct - target_cash
            return Signal(
                intent="DEPLOY",  # Signal to risk manager to increase exposure
                suggested_size=excess / 100 * budget,  # Amount to deploy
                confidence=0.5,
                reason=f"Cash {current_cash_pct}% above target {target_cash}%, can deploy {excess}%"
            )
        
        return Signal("HOLD", 0, 0.5, "Cash at target allocation")
    
    def _get_target_cash_pct(self, regime: str) -> float:
        """Get target cash percentage for regime."""
        targets = {
            "risk_on": self.config['risk_on_target_cash_pct'],
            "neutral": self.config['neutral_target_cash_pct'],
            "risk_off": self.config['risk_off_target_cash_pct'],
            "panic": self.config['panic_target_cash_pct'],
        }
        return targets.get(regime, 50)
    
    def generate_entry_intents(self, market_data: Dict, portfolio_state: Dict) -> list:
        return []
    
    def generate_exit_intents(self, positions: list, market_data: Dict) -> list:
        return []
    
    def get_metadata(self):
        from strategies.registry import StrategyMetadata
        return StrategyMetadata(
            name="cash_stable_allocator",
            version="1.0",
            supported_markets=["global"],
            supported_modes=["crypto"],
            instrument_type="crypto",
        )
    
    def get_supported_instruments(self) -> list:
        return ["crypto"]
