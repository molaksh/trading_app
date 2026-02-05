"""
Crypto strategy layer.

Selects active strategies based on regime and market conditions.
Max 2 concurrent strategies with per-strategy capital budgets.
"""

import logging
from enum import Enum
from typing import List, Dict, Optional
from dataclasses import dataclass

from crypto.regime import MarketRegime

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Crypto strategy types."""
    TREND_FOLLOWER = "trend_follower"
    VOLATILITY_SWING = "volatility_swing"
    MEAN_REVERSION = "mean_reversion"
    DEFENSIVE_HEDGE = "defensive_hedge"
    STABLE_ALLOCATOR = "stable_allocator"
    RECOVERY = "recovery"


@dataclass
class StrategyAllocation:
    """Strategy allocation and metadata."""
    strategy_type: StrategyType
    regime: MarketRegime
    capital_allocation: float  # % of portfolio
    active: bool
    max_position_count: int
    max_risk_per_trade: float


class StrategySelector:
    """
    Selects active strategies based on regime.
    
    Rules:
    - Max 2 concurrent strategies
    - Each strategy has capital budget (hard cap)
    - No voting/ensemble; selector decides
    """
    
    # Strategy-to-regime mapping
    STRATEGY_REGIMES = {
        StrategyType.TREND_FOLLOWER: [MarketRegime.RISK_ON],
        StrategyType.VOLATILITY_SWING: [MarketRegime.RISK_ON, MarketRegime.NEUTRAL],
        StrategyType.MEAN_REVERSION: [MarketRegime.NEUTRAL],
        StrategyType.DEFENSIVE_HEDGE: [MarketRegime.RISK_OFF, MarketRegime.PANIC],
        StrategyType.STABLE_ALLOCATOR: [MarketRegime.PANIC],
        StrategyType.RECOVERY: [MarketRegime.RISK_OFF],
    }
    
    def __init__(self, max_concurrent: int = 2, default_allocation: float = 0.5):
        """
        Initialize strategy selector.
        
        Args:
            max_concurrent: Max strategies active at once
            default_allocation: Default capital allocation per strategy
        """
        self.max_concurrent = max_concurrent
        self.default_allocation = default_allocation
        self.active_strategies: List[StrategyAllocation] = []
        
        logger.info(f"Strategy selector initialized (max {max_concurrent} concurrent)")
    
    def select_strategies(self, regime: MarketRegime, 
                         available_capital: float) -> List[StrategyAllocation]:
        """
        Select strategies for current regime.
        
        Args:
            regime: Current market regime
            available_capital: Portfolio capital available
        
        Returns:
            List of active strategy allocations
        """
        # Find strategies compatible with regime
        compatible = [
            s for s, regs in self.STRATEGY_REGIMES.items()
            if regime in regs
        ]
        
        # Select up to max_concurrent
        selected = compatible[:self.max_concurrent]
        
        # Allocate capital evenly
        allocation_per_strategy = available_capital / len(selected) if selected else 0.0
        
        self.active_strategies = [
            StrategyAllocation(
                strategy_type=s,
                regime=regime,
                capital_allocation=allocation_per_strategy,
                active=True,
                max_position_count=5,  # Placeholder
                max_risk_per_trade=0.02,  # Placeholder
            )
            for s in selected
        ]
        
        logger.info(f"Selected {len(selected)} strategies for regime {regime.value}")
        for sa in self.active_strategies:
            logger.info(f"  - {sa.strategy_type.value}: ${sa.capital_allocation:,.0f}")
        
        return self.active_strategies
    
    def get_active_strategies(self) -> List[StrategyAllocation]:
        """Get currently active strategies."""
        return self.active_strategies


# Placeholder strategy implementations (real strategies would have full logic)

class TrendFollowerStrategy:
    """Long-term trend following strategy (RISK_ON only)."""
    
    def generate_signals(self, market_data: Dict) -> List[Dict]:
        """Generate BUY/SELL signals based on trend."""
        # Placeholder
        return []


class VolatilitySwingStrategy:
    """Volatility-scaled swing trading (RISK_ON/NEUTRAL)."""
    
    def generate_signals(self, market_data: Dict) -> List[Dict]:
        """Generate swing trade signals."""
        # Placeholder
        return []


class MeanReversionStrategy:
    """Mean reversion strategy (NEUTRAL only)."""
    
    def generate_signals(self, market_data: Dict) -> List[Dict]:
        """Generate mean reversion signals."""
        # Placeholder
        return []


class DefensiveHedgeStrategy:
    """Defensive hedge/short strategy (RISK_OFF/PANIC, small/time-limited)."""
    
    def generate_signals(self, market_data: Dict) -> List[Dict]:
        """Generate protective/short signals."""
        # Placeholder
        return []


class StableAllocatorStrategy:
    """Cash/stable allocator (PANIC, can force flat)."""
    
    def generate_signals(self, market_data: Dict) -> List[Dict]:
        """Generate derisking signals."""
        # Placeholder
        return []


class RecoveryStrategy:
    """Recovery/re-entry strategy (PANIC→NEUTRAL transition)."""
    
    def generate_signals(self, market_data: Dict) -> List[Dict]:
        """Generate re-entry signals after panic."""
        # Placeholder
        return []
