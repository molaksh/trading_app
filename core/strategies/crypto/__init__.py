"""
Crypto trading strategies for Kraken global markets.

CANONICAL CRYPTO STRATEGIES (6 first-class registered strategies):
  1. LongTermTrendFollowerStrategy
  2. VolatilityScaledSwingStrategy
  3. MeanReversionStrategy
  4. DefensiveHedgeShortStrategy
  5. CashStableAllocatorStrategy
  6. RecoveryReentryStrategy

Each strategy is independently enabled/disabled by config.
Max 2 concurrent strategies per regime.
No wrappers, no ensembling.
"""

from core.strategies.crypto.registry import CryptoStrategyRegistry

# Initialize registry on import
CryptoStrategyRegistry.initialize()

__all__ = [
    "CryptoStrategyRegistry",
]
