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

# Export all strategy classes for import
from core.strategies.equity.swing.swing_base import BaseSwingStrategy, SwingStrategyMetadata
from core.strategies.equity.swing.swing_trend_pullback import SwingTrendPullbackStrategy
from core.strategies.equity.swing.swing_momentum_breakout import SwingMomentumBreakoutStrategy
from core.strategies.equity.swing.swing_mean_reversion import SwingMeanReversionStrategy
from core.strategies.equity.swing.swing_volatility_squeeze import SwingVolatilitySqueezeStrategy
from core.strategies.equity.swing.swing_event_driven import SwingEventDrivenStrategy
from core.strategies.equity.swing.swing_container import SwingEquityStrategy

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
