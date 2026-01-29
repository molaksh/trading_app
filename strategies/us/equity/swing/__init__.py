"""
US Equity Swing Strategies

This module imports swing strategies from the canonical core location.
Swing strategies are market-agnostic and reused across all markets.

Market-specific configuration (policies, execution, etc.) lives here.
Strategy logic lives in core/strategies/equity/swing/
"""

# Re-export canonical swing strategies from core
from core.strategies.equity.swing import (
    SwingEquityStrategy,
    BaseSwingStrategy,
    SwingStrategyMetadata,
    SwingTrendPullbackStrategy,
    SwingMomentumBreakoutStrategy,
    SwingMeanReversionStrategy,
    SwingVolatilitySqueezeStrategy,
    SwingEventDrivenStrategy,
)

__all__ = [
    "SwingEquityStrategy",
    "BaseSwingStrategy",
    "SwingStrategyMetadata",
    "SwingTrendPullbackStrategy",
    "SwingMomentumBreakoutStrategy",
    "SwingMeanReversionStrategy",
    "SwingVolatilitySqueezeStrategy",
    "SwingEventDrivenStrategy",
]
