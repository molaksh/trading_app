"""
Crypto feature builders for execution and regime detection.

TWO-TIMEFRAME MODEL:
- ExecutionFeatureContext: Built from 5m candles (strategy signals, entry/exit)
- RegimeFeatureContext: Built from 4h candles (regime detection ONLY)

CRITICAL: These must NEVER be mixed. Each timeframe serves a distinct purpose.
"""

from crypto.features.execution_features import ExecutionFeatureContext, build_execution_features
from crypto.features.regime_features import RegimeFeatureContext, build_regime_features

__all__ = [
    "ExecutionFeatureContext",
    "build_execution_features",
    "RegimeFeatureContext",
    "build_regime_features",
]
