"""
Crypto strategy selector - PRODUCTION IMPLEMENTATION.

Selects active strategies based on current market regime.
All placeholder logic removed - fully configurable from crypto config.

RULES:
- Max 2 concurrent strategies
- Each strategy has explicit regime support
- Capital allocated evenly among selected strategies
- No voting, no ensemble logic
"""

import logging
from enum import Enum
from typing import List, Dict, Optional
from dataclasses import dataclass

from crypto.regime import MarketRegime

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Crypto strategy types (maps to actual strategy instances)."""
    LONG_TERM_TREND_FOLLOWER = "long_term_trend_follower"
    VOLATILITY_SCALED_SWING = "volatility_scaled_swing"
    MEAN_REVERSION = "mean_reversion"
    DEFENSIVE_HEDGE_SHORT = "defensive_hedge_short"
    CASH_STABLE_ALLOCATOR = "cash_stable_allocator"
    RECOVERY_REENTRY = "recovery_reentry"


@dataclass
class StrategyAllocation:
    """Strategy allocation metadata."""
    strategy_type: StrategyType
    regime: MarketRegime
    capital_allocation: float  # USD allocated to this strategy
    active: bool
    max_position_count: int  # From config
    max_risk_per_trade: float  # From config


class CryptoStrategySelector:
    """
    Selects active strategies based on regime with NO placeholder logic.
    
    All parameters loaded from crypto config.
    """
    
    # Strategy-to-regime mapping (IMMUTABLE - defined by strategy contracts)
    STRATEGY_REGIMES = {
        StrategyType.LONG_TERM_TREND_FOLLOWER: {MarketRegime.RISK_ON, MarketRegime.NEUTRAL},
        StrategyType.VOLATILITY_SCALED_SWING: {MarketRegime.NEUTRAL},
        StrategyType.MEAN_REVERSION: {MarketRegime.NEUTRAL, MarketRegime.RISK_OFF},
        StrategyType.DEFENSIVE_HEDGE_SHORT: {MarketRegime.RISK_OFF, MarketRegime.PANIC},
        StrategyType.CASH_STABLE_ALLOCATOR: {MarketRegime.PANIC},
        StrategyType.RECOVERY_REENTRY: {MarketRegime.PANIC, MarketRegime.NEUTRAL},
    }
    
    def __init__(
        self,
        max_concurrent: int,
        max_position_count: int,
        max_risk_per_trade: float,
        allocation_cap_pct: float,
    ):
        """
        Initialize strategy selector with config values.
        
        Args:
            max_concurrent: Max strategies active at once (from config)
            max_position_count: Max positions per strategy (from config)
            max_risk_per_trade: Max risk per trade as fraction (from config)
            allocation_cap_pct: Max allocation per strategy (from config)
        """
        self.max_concurrent = max_concurrent
        self.max_position_count = max_position_count
        self.max_risk_per_trade = max_risk_per_trade
        self.allocation_cap_pct = allocation_cap_pct
        self.active_strategies: List[StrategyAllocation] = []
        
        logger.info(f"CryptoStrategySelector initialized (REAL IMPLEMENTATION)")
        logger.info(f"  Max concurrent: {max_concurrent}")
        logger.info(f"  Max positions per strategy: {max_position_count}")
        logger.info(f"  Max risk per trade: {max_risk_per_trade:.2%}")
        logger.info(f"  Allocation cap per strategy: {allocation_cap_pct:.2%}")
    
    def select_strategies(
        self,
        regime: MarketRegime,
        available_capital: float,
    ) -> List[StrategyAllocation]:
        """
        Select strategies for current regime.
        
        Args:
            regime: Current market regime
            available_capital: Portfolio capital available
        
        Returns:
            List of active strategy allocations (max 2)
        """
        # Find strategies compatible with current regime
        compatible = [
            strategy_type
            for strategy_type, supported_regimes in self.STRATEGY_REGIMES.items()
            if regime in supported_regimes
        ]
        
        if not compatible:
            logger.warning(f"No strategies support regime {regime.value}")
            self.active_strategies = []
            return []
        
        # Select up to max_concurrent (deterministic order for reproducibility)
        selected = sorted(compatible, key=lambda x: x.value)[:self.max_concurrent]
        
        # Allocate capital evenly
        allocation_per_strategy = min(
            available_capital / len(selected),
            available_capital * self.allocation_cap_pct,
        )
        
        self.active_strategies = [
            StrategyAllocation(
                strategy_type=s,
                regime=regime,
                capital_allocation=allocation_per_strategy,
                active=True,
                max_position_count=self.max_position_count,
                max_risk_per_trade=self.max_risk_per_trade,
            )
            for s in selected
        ]
        
        logger.info(f"Selected {len(selected)} strategies for regime {regime.value}")
        for sa in self.active_strategies:
            logger.info(f"  - {sa.strategy_type.value}: ${sa.capital_allocation:,.2f} allocated")
        
        return self.active_strategies
    
    def get_active_strategies(self) -> List[StrategyAllocation]:
        """Get currently active strategies."""
        return self.active_strategies
    
    def get_eligible_strategies(self, regime: MarketRegime) -> List[StrategyType]:
        """Get list of strategies that support the given regime."""
        return [
            strategy_type
            for strategy_type, supported_regimes in self.STRATEGY_REGIMES.items()
            if regime in supported_regimes
        ]
