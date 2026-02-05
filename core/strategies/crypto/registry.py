"""
Crypto strategy registry - First-class registration of 6 canonical strategies.

MANDATORY: The crypto pod registers EXACTLY these 6 strategies:
  1. LongTermTrendFollowerStrategy
  2. VolatilityScaledSwingStrategy
  3. MeanReversionStrategy
  4. DefensiveHedgeShortStrategy
  5. CashStableAllocatorStrategy
  6. RecoveryReentryStrategy

NO wrappers, NO ensembling, NO voting.
Each strategy is independently enabled/disabled by config.
"""

import logging
from typing import Dict, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CryptoStrategyType(Enum):
    """Crypto strategy registry - canonical types."""
    TREND_FOLLOWER = "long_term_trend_follower"
    VOLATILITY_SWING = "volatility_scaled_swing"
    MEAN_REVERSION = "mean_reversion"
    DEFENSIVE_HEDGE = "defensive_hedge_short"
    STABLE_ALLOCATOR = "cash_stable_allocator"
    RECOVERY = "recovery_reentry"


@dataclass
class CryptoStrategyMetadata:
    """Metadata for a registered crypto strategy."""
    strategy_id: str                   # e.g., "long_term_trend_follower"
    strategy_name: str                 # e.g., "LongTermTrendFollowerStrategy"
    version: str                       # e.g., "1.0.0"
    
    # Regime constraints
    allowed_regimes: List[str]         # e.g., ["RISK_ON", "NEUTRAL"]
    forbidden_regimes: List[str]       # e.g., ["RISK_OFF", "PANIC"]
    
    # Configuration
    enabled: bool                      # Can be toggled by config
    allocation_pct: float              # % of portfolio if selected
    
    def __post_init__(self):
        """Validate metadata."""
        if not self.allowed_regimes:
            raise ValueError(f"{self.strategy_id}: allowed_regimes cannot be empty")
        if not self.strategy_name:
            raise ValueError(f"{self.strategy_id}: strategy_name required")


class CryptoStrategyRegistry:
    """
    Registry of crypto strategies for Kraken global markets.
    
    INVARIANT: Contains exactly 6 strategies, no wrappers.
    """
    
    _registry: Dict[str, CryptoStrategyMetadata] = {}
    _initialized = False
    
    @classmethod
    def initialize(cls) -> None:
        """Initialize the crypto strategy registry with all 6 canonical strategies."""
        if cls._initialized:
            return
        
        logger.info("\n" + "="*80)
        logger.info("CRYPTO STRATEGY REGISTRY INITIALIZATION")
        logger.info("="*80)
        
        # Register all 6 canonical crypto strategies
        strategies = [
            CryptoStrategyMetadata(
                strategy_id=CryptoStrategyType.TREND_FOLLOWER.value,
                strategy_name="LongTermTrendFollowerStrategy",
                version="1.0.0",
                allowed_regimes=["RISK_ON", "NEUTRAL"],
                forbidden_regimes=["RISK_OFF", "PANIC"],
                enabled=True,
                allocation_pct=35.0,
            ),
            CryptoStrategyMetadata(
                strategy_id=CryptoStrategyType.VOLATILITY_SWING.value,
                strategy_name="VolatilityScaledSwingStrategy",
                version="1.0.0",
                allowed_regimes=["NEUTRAL"],
                forbidden_regimes=["RISK_ON", "RISK_OFF", "PANIC"],
                enabled=True,
                allocation_pct=30.0,
            ),
            CryptoStrategyMetadata(
                strategy_id=CryptoStrategyType.MEAN_REVERSION.value,
                strategy_name="MeanReversionStrategy",
                version="1.0.0",
                allowed_regimes=["NEUTRAL", "RISK_OFF"],
                forbidden_regimes=["RISK_ON", "PANIC"],
                enabled=True,
                allocation_pct=30.0,
            ),
            CryptoStrategyMetadata(
                strategy_id=CryptoStrategyType.DEFENSIVE_HEDGE.value,
                strategy_name="DefensiveHedgeShortStrategy",
                version="1.0.0",
                allowed_regimes=["RISK_OFF", "PANIC"],
                forbidden_regimes=["RISK_ON", "NEUTRAL"],
                enabled=True,
                allocation_pct=25.0,
            ),
            CryptoStrategyMetadata(
                strategy_id=CryptoStrategyType.STABLE_ALLOCATOR.value,
                strategy_name="CashStableAllocatorStrategy",
                version="1.0.0",
                allowed_regimes=["PANIC"],
                forbidden_regimes=["RISK_ON", "NEUTRAL", "RISK_OFF"],
                enabled=True,
                allocation_pct=20.0,
            ),
            CryptoStrategyMetadata(
                strategy_id=CryptoStrategyType.RECOVERY.value,
                strategy_name="RecoveryReentryStrategy",
                version="1.0.0",
                allowed_regimes=["PANIC", "NEUTRAL"],
                forbidden_regimes=["RISK_ON", "RISK_OFF"],
                enabled=True,
                allocation_pct=25.0,
            ),
        ]
        
        # Register all strategies
        for strategy_meta in strategies:
            cls._registry[strategy_meta.strategy_id] = strategy_meta
            logger.info(
                f"✓ Registered {strategy_meta.strategy_name:40} "
                f"[{strategy_meta.strategy_id:25}] "
                f"allocation={strategy_meta.allocation_pct:5.1f}% "
                f"enabled={strategy_meta.enabled}"
            )
        
        logger.info("")
        logger.info(f"Total registered crypto strategies: {len(cls._registry)}")
        logger.info("")
        
        enabled_count = sum(1 for s in cls._registry.values() if s.enabled)
        logger.info(f"Crypto strategies enabled by config: {enabled_count}/{len(cls._registry)}")
        logger.info("")
        
        logger.info("ENABLED STRATEGIES:")
        for strategy_id, metadata in cls._registry.items():
            if metadata.enabled:
                logger.info(f"  ✓ {metadata.strategy_name:40} (regimes: {', '.join(metadata.allowed_regimes)})")
        
        logger.info("")
        logger.info("="*80)
        logger.info("")
        
        cls._initialized = True
    
    @classmethod
    def get_all_strategies(cls) -> Dict[str, CryptoStrategyMetadata]:
        """Get all registered crypto strategies."""
        if not cls._initialized:
            cls.initialize()
        return cls._registry.copy()
    
    @classmethod
    def get_enabled_strategies(cls) -> Dict[str, CryptoStrategyMetadata]:
        """Get only enabled crypto strategies."""
        if not cls._initialized:
            cls.initialize()
        return {k: v for k, v in cls._registry.items() if v.enabled}
    
    @classmethod
    def get_strategies_for_regime(cls, regime: str) -> Dict[str, CryptoStrategyMetadata]:
        """Get enabled strategies compatible with a given regime."""
        if not cls._initialized:
            cls.initialize()
        
        compatible = {}
        for strategy_id, metadata in cls._registry.items():
            if not metadata.enabled:
                continue
            if regime in metadata.allowed_regimes and regime not in metadata.forbidden_regimes:
                compatible[strategy_id] = metadata
        
        return compatible
    
    @classmethod
    def validate_registration(cls) -> None:
        """
        Validate that registration invariants are met.
        
        MANDATORY CHECKS:
        1. Exactly 6 strategies registered
        2. No wrapper strategies (crypto_momentum, crypto_trend)
        3. All strategy names match expected format
        4. Regime constraints are valid
        """
        if not cls._initialized:
            cls.initialize()
        
        registry = cls._registry
        
        # Check 1: Exactly 6 strategies
        if len(registry) != 6:
            raise AssertionError(
                f"INVARIANT VIOLATION: Expected 6 crypto strategies, got {len(registry)}"
            )
        
        # Check 2: No wrapper strategies
        forbidden_names = {"crypto_momentum", "crypto_trend", "CryptoMomentumStrategy", "CryptoTrendStrategy"}
        for strategy_id, metadata in registry.items():
            if strategy_id in forbidden_names or metadata.strategy_name in forbidden_names:
                raise AssertionError(
                    f"INVARIANT VIOLATION: Wrapper strategy {strategy_id} registered. "
                    f"Only canonical 6 strategies allowed."
                )
        
        # Check 3: Strategy names match format
        expected_ids = {
            "long_term_trend_follower",
            "volatility_scaled_swing",
            "mean_reversion",
            "defensive_hedge_short",
            "cash_stable_allocator",
            "recovery_reentry",
        }
        actual_ids = set(registry.keys())
        if actual_ids != expected_ids:
            raise AssertionError(
                f"INVARIANT VIOLATION: Registered strategy IDs don't match expected set. "
                f"Expected: {expected_ids}, Got: {actual_ids}"
            )
        
        # Check 4: Regime constraints are valid
        valid_regimes = {"RISK_ON", "NEUTRAL", "RISK_OFF", "PANIC"}
        for strategy_id, metadata in registry.items():
            for regime in metadata.allowed_regimes:
                if regime not in valid_regimes:
                    raise AssertionError(
                        f"Invalid regime '{regime}' in {strategy_id}.allowed_regimes"
                    )
            for regime in metadata.forbidden_regimes:
                if regime not in valid_regimes:
                    raise AssertionError(
                        f"Invalid regime '{regime}' in {strategy_id}.forbidden_regimes"
                    )
        
        logger.info("✓ Crypto strategy registry validation passed")
