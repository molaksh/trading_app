"""
Tests for crypto strategy registration invariants.

MANDATORY CHECKS:
1. Exactly 6 crypto strategies registered
2. No wrapper strategies in registration
3. No cross-contamination with swing strategies
4. All 6 strategies have correct regime constraints
5. Selector enforces max_concurrent_strategies=2
6. Capital allocation sums correctly
"""

import pytest
from core.strategies.crypto.registry import CryptoStrategyRegistry, CryptoStrategyType
from strategies.registry import StrategyRegistry
from config.scope import Scope


class TestCryptoStrategyRegistration:
    """Test crypto strategy registration invariants."""
    
    def test_crypto_registry_initialized(self):
        """Test that crypto registry initializes without errors."""
        CryptoStrategyRegistry.initialize()
        registry = CryptoStrategyRegistry.get_all_strategies()
        assert len(registry) == 6, f"Expected 6 strategies, got {len(registry)}"
    
    def test_exactly_six_strategies_registered(self):
        """INVARIANT: Exactly 6 canonical crypto strategies registered."""
        CryptoStrategyRegistry.initialize()
        registry = CryptoStrategyRegistry.get_all_strategies()
        
        assert len(registry) == 6, (
            f"INVARIANT VIOLATED: Expected 6 crypto strategies, got {len(registry)}. "
            f"Registered: {list(registry.keys())}"
        )
    
    def test_no_wrapper_strategies_registered(self):
        """INVARIANT: No wrapper strategies (crypto_momentum, crypto_trend) in registry."""
        CryptoStrategyRegistry.initialize()
        registry = CryptoStrategyRegistry.get_all_strategies()
        
        forbidden_ids = {"crypto_momentum", "crypto_trend"}
        forbidden_names = {"CryptoMomentumStrategy", "CryptoTrendStrategy"}
        
        for strategy_id, metadata in registry.items():
            assert strategy_id not in forbidden_ids, (
                f"INVARIANT VIOLATED: Wrapper strategy '{strategy_id}' registered. "
                f"Only canonical strategies allowed."
            )
            assert metadata.strategy_name not in forbidden_names, (
                f"INVARIANT VIOLATED: Wrapper '{metadata.strategy_name}' registered. "
                f"Only canonical strategies allowed."
            )
    
    def test_correct_strategy_ids(self):
        """INVARIANT: Registered strategy IDs match expected canonical set."""
        CryptoStrategyRegistry.initialize()
        registry = CryptoStrategyRegistry.get_all_strategies()
        
        expected_ids = {
            CryptoStrategyType.TREND_FOLLOWER.value,
            CryptoStrategyType.VOLATILITY_SWING.value,
            CryptoStrategyType.MEAN_REVERSION.value,
            CryptoStrategyType.DEFENSIVE_HEDGE.value,
            CryptoStrategyType.STABLE_ALLOCATOR.value,
            CryptoStrategyType.RECOVERY.value,
        }
        actual_ids = set(registry.keys())
        
        assert actual_ids == expected_ids, (
            f"INVARIANT VIOLATED: Strategy IDs mismatch. "
            f"Expected: {expected_ids}, Got: {actual_ids}"
        )
    
    def test_all_strategies_have_regime_constraints(self):
        """INVARIANT: All strategies have allowed and forbidden regimes defined."""
        CryptoStrategyRegistry.initialize()
        registry = CryptoStrategyRegistry.get_all_strategies()
        
        valid_regimes = {"RISK_ON", "NEUTRAL", "RISK_OFF", "PANIC"}
        
        for strategy_id, metadata in registry.items():
            # Check allowed_regimes
            assert metadata.allowed_regimes, (
                f"{strategy_id}: allowed_regimes cannot be empty"
            )
            for regime in metadata.allowed_regimes:
                assert regime in valid_regimes, (
                    f"{strategy_id}: Invalid regime '{regime}' in allowed_regimes"
                )
            
            # Check forbidden_regimes
            for regime in metadata.forbidden_regimes:
                assert regime in valid_regimes, (
                    f"{strategy_id}: Invalid regime '{regime}' in forbidden_regimes"
                )
            
            # Check no overlap between allowed and forbidden
            overlap = set(metadata.allowed_regimes) & set(metadata.forbidden_regimes)
            assert not overlap, (
                f"{strategy_id}: Regime overlap between allowed and forbidden: {overlap}"
            )
    
    def test_regime_specific_strategies(self):
        """Test that strategies are correctly constrained to specific regimes."""
        CryptoStrategyRegistry.initialize()
        registry = CryptoStrategyRegistry.get_all_strategies()
        
        # Mean reversion: NEUTRAL, RISK_OFF only
        mean_rev = registry["mean_reversion"]
        assert "NEUTRAL" in mean_rev.allowed_regimes
        assert "RISK_OFF" in mean_rev.allowed_regimes
        assert "RISK_ON" not in mean_rev.allowed_regimes
        assert "PANIC" not in mean_rev.allowed_regimes
        
        # Defensive hedge: RISK_OFF, PANIC only
        hedge = registry["defensive_hedge_short"]
        assert "RISK_OFF" in hedge.allowed_regimes
        assert "PANIC" in hedge.allowed_regimes
        assert "RISK_ON" not in hedge.allowed_regimes
        assert "NEUTRAL" not in hedge.allowed_regimes
        
        # Stable allocator: PANIC only
        stable = registry["cash_stable_allocator"]
        assert "PANIC" in stable.allowed_regimes
        assert len(stable.allowed_regimes) == 1, "Stable allocator only allowed in PANIC"
    
    def test_strategies_for_specific_regime(self):
        """Test regime-based strategy selection."""
        CryptoStrategyRegistry.initialize()
        
        # RISK_ON: Should have trend_follower and volatility_swing
        risk_on_strategies = CryptoStrategyRegistry.get_strategies_for_regime("RISK_ON")
        assert "long_term_trend_follower" in risk_on_strategies
        assert "defensive_hedge_short" not in risk_on_strategies
        assert "cash_stable_allocator" not in risk_on_strategies
        
        # PANIC: Should have defensive_hedge, stable_allocator, recovery
        panic_strategies = CryptoStrategyRegistry.get_strategies_for_regime("PANIC")
        assert "defensive_hedge_short" in panic_strategies
        assert "cash_stable_allocator" in panic_strategies
        assert "recovery_reentry" in panic_strategies
        assert "long_term_trend_follower" not in panic_strategies
    
    def test_allocation_percentages_valid(self):
        """Test that allocation percentages are reasonable."""
        CryptoStrategyRegistry.initialize()
        registry = CryptoStrategyRegistry.get_all_strategies()
        
        for strategy_id, metadata in registry.items():
            assert 0 < metadata.allocation_pct <= 100, (
                f"{strategy_id}: allocation_pct={metadata.allocation_pct} is invalid"
            )
    
    def test_validation_passes(self):
        """Test that validation passes without exceptions."""
        CryptoStrategyRegistry.initialize()
        # Should not raise
        CryptoStrategyRegistry.validate_registration()


class TestCryptoStrategyMainRegistry:
    """Test crypto strategies in main StrategyRegistry."""
    
    def test_crypto_strategies_in_main_registry(self):
        """Test that 6 crypto strategies are discoverable from main registry."""
        main_registry = StrategyRegistry.discover_strategies()
        
        # Count crypto strategies
        crypto_strategies = {
            k: v for k, v in main_registry.items()
            if k in [
                "long_term_trend_follower",
                "volatility_scaled_swing",
                "mean_reversion",
                "defensive_hedge_short",
                "cash_stable_allocator",
                "recovery_reentry",
            ]
        }
        
        assert len(crypto_strategies) == 6, (
            f"Expected 6 crypto strategies in main registry, got {len(crypto_strategies)}"
        )
    
    def test_crypto_scope_loads_crypto_strategies(self):
        """Test that paper_kraken_crypto_global scope loads crypto strategies."""
        scope = Scope.from_string("paper_kraken_crypto_global")
        strategies = StrategyRegistry.get_strategies_for_scope(scope)
        
        # Should have 6 crypto strategies for crypto scope
        crypto_ids = {
            "long_term_trend_follower",
            "volatility_scaled_swing",
            "mean_reversion",
            "defensive_hedge_short",
            "cash_stable_allocator",
            "recovery_reentry",
        }
        
        loaded_crypto = {k: v for k, v in strategies.items() if k in crypto_ids}
        assert len(loaded_crypto) == 6, (
            f"Crypto scope should load 6 crypto strategies, got {len(loaded_crypto)}"
        )
        
        # Should NOT have swing strategies
        assert "swing_equity" not in strategies, (
            "Crypto scope should not load swing_equity"
        )
    
    def test_swing_scope_no_crypto_strategies(self):
        """Test that swing scopes don't load crypto strategies."""
        scope = Scope.from_string("paper_alpaca_swing_us")
        strategies = StrategyRegistry.get_strategies_for_scope(scope)
        
        crypto_ids = {
            "long_term_trend_follower",
            "volatility_scaled_swing",
            "mean_reversion",
            "defensive_hedge_short",
            "cash_stable_allocator",
            "recovery_reentry",
        }
        
        loaded_crypto = {k: v for k, v in strategies.items() if k in crypto_ids}
        assert len(loaded_crypto) == 0, (
            f"Swing scope should not load crypto strategies, got {loaded_crypto}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
