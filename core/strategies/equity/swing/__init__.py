"""
Swing equity strategies - CANONICAL LOCATION.

This directory contains the single source of truth for all swing strategy implementations.
All swing strategies are market-agnostic and reused across markets (US, India, etc).

Philosophy implementations:
- swing_trend_pullback: Shallow pullbacks in established uptrends
- swing_momentum_breakout: Continuation on strength and volume
- swing_mean_reversion: Snapbacks within uptrends
- swing_volatility_squeeze: Expansion after Bollinger Band compression
- swing_event_driven: Post-event behavior patterns

Container:
- swing_container: Orchestrator that runs all 5 philosophies and aggregates signals
"""

# Use lazy imports to avoid circular imports
def __getattr__(name):
    """Lazy load strategy classes to avoid circular imports."""
    if name == "SwingEquityStrategy":
        from core.strategies.equity.swing.swing_container import SwingEquityStrategy
        return SwingEquityStrategy
    elif name == "BaseSwingStrategy":
        from core.strategies.equity.swing.swing_base import BaseSwingStrategy
        return BaseSwingStrategy
    elif name == "SwingStrategyMetadata":
        from core.strategies.equity.swing.swing_base import SwingStrategyMetadata
        return SwingStrategyMetadata
    elif name == "SwingTrendPullbackStrategy":
        from core.strategies.equity.swing.swing_trend_pullback import SwingTrendPullbackStrategy
        return SwingTrendPullbackStrategy
    elif name == "SwingMomentumBreakoutStrategy":
        from core.strategies.equity.swing.swing_momentum_breakout import SwingMomentumBreakoutStrategy
        return SwingMomentumBreakoutStrategy
    elif name == "SwingMeanReversionStrategy":
        from core.strategies.equity.swing.swing_mean_reversion import SwingMeanReversionStrategy
        return SwingMeanReversionStrategy
    elif name == "SwingVolatilitySqueezeStrategy":
        from core.strategies.equity.swing.swing_volatility_squeeze import SwingVolatilitySqueezeStrategy
        return SwingVolatilitySqueezeStrategy
    elif name == "SwingEventDrivenStrategy":
        from core.strategies.equity.swing.swing_event_driven import SwingEventDrivenStrategy
        return SwingEventDrivenStrategy
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "BaseSwingStrategy",
    "SwingStrategyMetadata",
    "SwingTrendPullbackStrategy",
    "SwingMomentumBreakoutStrategy",
    "SwingMeanReversionStrategy",
    "SwingVolatilitySqueezeStrategy",
    "SwingEventDrivenStrategy",
    "SwingEquityStrategy",
]
