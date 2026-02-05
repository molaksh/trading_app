"""
RecoveryReentryStrategy - Re-entry after crash recovery.

PHILOSOPHY:
- Wait for PANIC→NEUTRAL regime transition before re-entering
- Entry only on confirmation that crash is over
- Aggressive sizing to capitalize on recovery

SUPPORTED REGIMES: PANIC→NEUTRAL transition ONLY
TRIGGER: Previous regime=PANIC, current regime=NEUTRAL (with confirmation)
FORBIDDEN: Direct entry in PANIC, no entry in RISK_OFF without recovery

EDGE:
- Catches post-crash recoveries (highest alpha period)
- Disciplined entry (waits for confirmation)
- Often precedes strong rallies

RISKS:
- Can miss the recovery start if confirmation too strict
- Needs regime state history to detect transition
- Must have confirmation hook to avoid false signals
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


class RecoveryReentryStrategy(Strategy):
    """Re-entry strategy for PANIC→NEUTRAL recovery transitions."""
    
    def __init__(self):
        config = {
            "enabled": True,
            "max_position_size_pct": 5.0,  # Aggressive sizing on recovery
            "confirmation_bars": 5,  # Need 5 bars of upside after transition
            "recovery_move_pct": 0.05,  # Need 5% recovery move
            "lookback_regime_bars": 10,  # Check last 10 bars for regime change
        }
        super().__init__("recovery_reentry", config)
        self.description = "Recovery reentry (PANIC→NEUTRAL transitions only)"
    
    def supported_regimes(self) -> Set[str]:
        """Special: Only triggers on PANIC→NEUTRAL transition."""
        return {"neutral"}  # Can only execute in NEUTRAL, but only after PANIC
    
    def generate_signal(
        self,
        feature_context: Dict[str, Any],
        portfolio_state: Dict[str, Any],
        budget: float,
        regime_state: str,
    ) -> Signal:
        """Generate recovery reentry signal (PANIC→NEUTRAL transition only)."""
        # Must be in NEUTRAL regime
        if regime_state != "neutral":
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason=f"RecoveryReentry only in NEUTRAL, got {regime_state}"
            )
        
        # Check for PANIC→NEUTRAL transition
        regime_history = feature_context.get('regime_history', [])  # Last N regimes
        
        # Need at least 2 bars history to detect transition
        if len(regime_history) < 2:
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason="Insufficient regime history to detect PANIC→NEUTRAL transition"
            )
        
        # Check if previous regime was PANIC (transition indicator)
        if regime_history[-2] != "panic":
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason=f"Previous regime was {regime_history[-2]}, not PANIC (no transition)"
            )
        
        # Confirm recovery with price action
        recovery_move = feature_context.get('recovery_move_pct', 0)
        confirmation_bars = feature_context.get('bars_since_transition', 0)
        
        # Validation checks
        if recovery_move < self.config['recovery_move_pct']:
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason=f"Recovery move {recovery_move:.2%} < threshold {self.config['recovery_move_pct']:.2%}"
            )
        
        if confirmation_bars < self.config['confirmation_bars']:
            return Signal(
                intent="FLAT",
                suggested_size=0,
                confidence=0,
                reason=f"Need {self.config['confirmation_bars']} bars confirmation, got {confirmation_bars}"
            )
        
        # All checks passed: generate aggressive long signal
        size = budget * (self.config['max_position_size_pct'] / 100)
        confidence = min(0.5 + recovery_move / 0.10, 1.0)  # Scale by recovery strength
        
        return Signal(
            intent="LONG",
            suggested_size=size,
            confidence=confidence,
            reason=f"PANIC→NEUTRAL transition confirmed: recovery {recovery_move:.2%}, {confirmation_bars} bars"
        )
    
    def generate_entry_intents(self, market_data: Dict, portfolio_state: Dict) -> list:
        return []
    
    def generate_exit_intents(self, positions: list, market_data: Dict) -> list:
        return []
    
    def get_metadata(self):
        from strategies.registry import StrategyMetadata
        return StrategyMetadata(
            name="recovery_reentry",
            version="1.0",
            supported_markets=["global"],
            supported_modes=["crypto"],
            instrument_type="crypto",
        )
    
    def get_supported_instruments(self) -> list:
        return ["crypto"]
