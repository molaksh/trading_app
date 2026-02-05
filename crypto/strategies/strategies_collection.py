"""
Crypto strategy collection - All 6 production strategies.

This module imports and registers all crypto trading strategies:
1. LongTermTrendFollowerStrategy
2. VolatilityScaledSwingStrategy
3. MeanReversionStrategy
4. DefensiveHedgeShortStrategy
5. CashStableAllocatorStrategy
6. RecoveryReentryStrategy

Each strategy:
- Lives in its own file under crypto/strategies/
- Implements required interface (supported_regimes, generate_signal)
- Has strict regime gating rules enforced in code
- Does NOT import swing strategy modules
"""

from crypto.strategies.long_term_trend_follower import LongTermTrendFollowerStrategy
from crypto.strategies.volatility_scaled_swing import VolatilityScaledSwingStrategy
from crypto.strategies.mean_reversion import MeanReversionStrategy
from crypto.strategies.defensive_hedge_short import DefensiveHedgeShortStrategy
from crypto.strategies.cash_stable_allocator import CashStableAllocatorStrategy
from crypto.strategies.recovery_reentry import RecoveryReentryStrategy

# Register all strategies
CRYPTO_STRATEGIES = {
    'long_term_trend_follower': LongTermTrendFollowerStrategy(),
    'volatility_scaled_swing': VolatilityScaledSwingStrategy(),
    'mean_reversion': MeanReversionStrategy(),
    'defensive_hedge_short': DefensiveHedgeShortStrategy(),
    'cash_stable_allocator': CashStableAllocatorStrategy(),
    'recovery_reentry': RecoveryReentryStrategy(),
}

__all__ = [
    "LongTermTrendFollowerStrategy",
    "VolatilityScaledSwingStrategy",
    "MeanReversionStrategy",
    "DefensiveHedgeShortStrategy",
    "CashStableAllocatorStrategy",
    "RecoveryReentryStrategy",
    "CRYPTO_STRATEGIES",
]
