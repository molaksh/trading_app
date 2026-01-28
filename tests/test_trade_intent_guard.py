"""
Unit tests for Trade Intent Guard.

Tests all rules and edge cases with clear naming and documentation.

PHASE: Future-proofing refactor
- Updated to use HoldPolicy for mode-specific behavior
- SwingHoldPolicy used for all tests (swing trading mode)
"""

import pytest
from datetime import date, timedelta

from risk.trade_intent_guard import (
    TradeIntentGuard,
    ExitReason,
    BlockReason,
    Trade,
    AccountContext,
    create_guard,
    create_trade,
    create_account_context,
)
from policies.hold_policy import SwingHoldPolicy


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def guard():
    """Standard guard with SwingHoldPolicy, manual override disabled."""
    hold_policy = SwingHoldPolicy()
    return create_guard(hold_policy=hold_policy, allow_manual_override=False)


@pytest.fixture
def guard_with_override():
    """Guard with SwingHoldPolicy, manual override enabled."""
    hold_policy = SwingHoldPolicy()
    return create_guard(hold_policy=hold_policy, allow_manual_override=True)


@pytest.fixture
def base_trade():
    """Standard trade for testing."""
    return create_trade(
        symbol="AAPL",
        entry_date=date(2026, 1, 27),
        entry_price=150.0,
        quantity=100,
        confidence=4,
    )


@pytest.fixture
def large_account():
    """Account > $25k (no PDT rules)."""
    return create_account_context(
        account_equity=50000.0,
        account_type="MARGIN",
        day_trade_count_5d=0,
    )


@pytest.fixture
def small_margin_account():
    """Margin account < $25k (PDT rules apply)."""
    return create_account_context(
        account_equity=10000.0,
        account_type="MARGIN",
        day_trade_count_5d=0,
    )


@pytest.fixture
def small_cash_account():
    """Cash account < $25k (no regulatory PDT but behavioral rules apply)."""
    return create_account_context(
        account_equity=10000.0,
        account_type="CASH",
        day_trade_count_5d=0,
    )


# =============================================================================
# TESTS: RULE 1 - MAX HOLD PERIOD (ALL ACCOUNTS)
# =============================================================================

class TestMaxHoldPeriod:
    """Max hold period rules (force exit after 20 days)."""
    
    def test_max_hold_exceeds_limit_forces_exit(self, guard, base_trade, large_account):
        """Exceeding 20-day hold forces exit regardless of reason."""
        exit_date = base_trade.entry_date + timedelta(days=21)
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=large_account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.MAX_HOLD_EXCEEDED.value
        assert decision.holding_days == 21
    
    def test_at_max_hold_boundary_allows_exit(self, guard, base_trade, large_account):
        """Exactly at max hold (20 days) allows exit."""
        exit_date = base_trade.entry_date + timedelta(days=20)
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=large_account,
        )
        
        assert decision.allowed is True
        assert decision.holding_days == 20


# =============================================================================
# TESTS: RULE 2 - RISK-REDUCING EXITS (ALL ACCOUNTS)
# =============================================================================

class TestRiskReducingExits:
    """Risk-reducing exits (STOP_LOSS, RISK_MANAGER) always allowed."""
    
    def test_stop_loss_same_day_allowed(self, guard, base_trade, small_margin_account):
        """STOP_LOSS same-day exit is allowed."""
        exit_date = base_trade.entry_date  # Same day
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STOP_LOSS,
            account_context=small_margin_account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value
    
    def test_risk_manager_same_day_allowed(self, guard, base_trade, small_margin_account):
        """RISK_MANAGER same-day exit is allowed."""
        exit_date = base_trade.entry_date  # Same day
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.RISK_MANAGER,
            account_context=small_margin_account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value
    
    def test_stop_loss_overrides_pdt_limit(self, guard, base_trade):
        """STOP_LOSS overrides PDT limit check."""
        exit_date = base_trade.entry_date  # Same day = day trade
        
        # Margin account at PDT hard limit
        account = create_account_context(
            account_equity=10000.0,
            account_type="MARGIN",
            day_trade_count_5d=3,  # Already at hard limit
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STOP_LOSS,
            account_context=account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value


# =============================================================================
# TESTS: RULE 3 - BEHAVIORAL PDT (ALL ACCOUNTS)
# =============================================================================

class TestBehavioralPDT:
    """Behavioral PDT: same-day discretionary exits blocked (all accounts)."""
    
    def test_same_day_strategy_signal_blocked_large_account(self, guard, base_trade, large_account):
        """Even large accounts cannot do same-day discretionary exits."""
        exit_date = base_trade.entry_date  # Same day
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=large_account,
        )
        
        assert decision.allowed is False
        assert decision.reason == BlockReason.SAME_DAY_DISCRETIONARY.value
    
    def test_same_day_profit_target_blocked_cash_account(self, guard, base_trade, small_cash_account):
        """Cash accounts cannot do same-day exits (behavioral rule)."""
        exit_date = base_trade.entry_date  # Same day
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=small_cash_account,
        )
        
        assert decision.allowed is False
        assert decision.reason == BlockReason.SAME_DAY_DISCRETIONARY.value
    
    def test_next_day_exit_allowed(self, guard, base_trade, large_account):
        """Day N+1 exits allowed."""
        exit_date = base_trade.entry_date + timedelta(days=1)
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=large_account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value


# =============================================================================
# TESTS: RULE 4 - MINIMUM HOLD PERIOD (SMALL ACCOUNTS < $25k)
# =============================================================================

class TestMinimumHoldPeriod:
    """Minimum 2-day hold for accounts < $25k (discretionary exits)."""
    
    def test_min_hold_1_day_blocked(self, guard, base_trade, small_margin_account):
        """1 day hold blocked for small accounts."""
        exit_date = base_trade.entry_date + timedelta(days=1)
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=small_margin_account,
        )
        
        assert decision.allowed is False
        assert decision.reason == BlockReason.MIN_HOLD_NOT_MET.value
        assert decision.holding_days == 1
    
    def test_min_hold_2_days_allowed(self, guard, base_trade, small_margin_account):
        """2 days hold allowed for small accounts."""
        exit_date = base_trade.entry_date + timedelta(days=2)
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=small_margin_account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value
        assert decision.holding_days == 2
    
    def test_min_hold_not_enforced_large_account(self, guard, base_trade, large_account):
        """Min hold not enforced for accounts > $25k."""
        exit_date = base_trade.entry_date + timedelta(days=1)
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=large_account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value
    
    def test_min_hold_bypass_by_stop_loss(self, guard, base_trade, small_margin_account):
        """STOP_LOSS bypasses min hold rule."""
        exit_date = base_trade.entry_date + timedelta(days=1)
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STOP_LOSS,
            account_context=small_margin_account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value


# =============================================================================
# TESTS: RULE 5 - REGULATORY PDT (MARGIN < $25k ONLY)
# =============================================================================

class TestRegulatoryPDT:
    """Regulatory PDT: 3-day trade limit in 5 days (margin < $25k only)."""
    
    def test_pdt_not_enforced_cash_account(self, guard, base_trade, small_cash_account):
        """PDT hard limit not enforced for cash accounts."""
        exit_date = base_trade.entry_date  # Day trade
        
        account = create_account_context(
            account_equity=10000.0,
            account_type="CASH",
            day_trade_count_5d=3,  # Already at limit
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STOP_LOSS,  # Allow day trade via risk exit
            account_context=account,
        )
        
        # Allowed because STOP_LOSS, not because of PDT check
        assert decision.allowed is True
    
    def test_pdt_not_enforced_large_margin(self, guard, base_trade, large_account):
        """PDT limit not enforced for margin accounts > $25k."""
        exit_date = base_trade.entry_date  # Day trade
        
        account = create_account_context(
            account_equity=50000.0,
            account_type="MARGIN",
            day_trade_count_5d=3,  # Already at limit
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=account,
        )
        
        # Blocked by behavioral PDT (same-day), not regulatory PDT
        assert decision.allowed is False
        assert decision.reason == BlockReason.SAME_DAY_DISCRETIONARY.value
    
    def test_pdt_hard_limit_blocks_exit(self, guard, base_trade, small_margin_account):
        """PDT hard limit (3) blocks day trade exit."""
        exit_date = base_trade.entry_date  # Day trade
        
        account = create_account_context(
            account_equity=10000.0,
            account_type="MARGIN",
            day_trade_count_5d=3,  # At hard limit
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.TIME_EXPIRY,
            account_context=account,
        )
        
        # Blocked by PDT hard limit
        assert decision.allowed is False
        assert decision.reason == BlockReason.PDT_LIMIT_REACHED.value
    
    def test_pdt_soft_limit_blocks_exit(self, guard, base_trade, small_margin_account):
        """PDT soft limit (2) blocks to prevent reaching hard limit (3)."""
        exit_date = base_trade.entry_date  # Day trade
        
        account = create_account_context(
            account_equity=10000.0,
            account_type="MARGIN",
            day_trade_count_5d=2,  # At soft limit
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.TIME_EXPIRY,
            account_context=account,
        )
        
        # Blocked by PDT soft limit
        assert decision.allowed is False
        assert decision.reason == BlockReason.PDT_LIMIT_AT_RISK.value
    
    def test_pdt_1_day_trade_allowed(self, guard, base_trade, small_margin_account):
        """1 day trade in 5 days allowed."""
        exit_date = base_trade.entry_date  # Day trade
        
        account = create_account_context(
            account_equity=10000.0,
            account_type="MARGIN",
            day_trade_count_5d=1,
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.TIME_EXPIRY,
            account_context=account,
        )
        
        # Allowed (1 < 2 soft limit)
        assert decision.allowed is True
    
    def test_pdt_zero_day_trades_allowed(self, guard, base_trade, small_margin_account):
        """0 day trades in 5 days allowed."""
        exit_date = base_trade.entry_date  # Day trade
        
        account = create_account_context(
            account_equity=10000.0,
            account_type="MARGIN",
            day_trade_count_5d=0,
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.TIME_EXPIRY,
            account_context=account,
        )
        
        # Allowed
        assert decision.allowed is True


# =============================================================================
# TESTS: RULE 6 - MANUAL OVERRIDE
# =============================================================================

class TestManualOverride:
    """Manual overrides (disabled by default)."""
    
    def test_manual_override_disabled_blocks_exit(self, guard, base_trade, large_account):
        """Manual override blocked when disabled."""
        exit_date = base_trade.entry_date + timedelta(days=5)
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.MANUAL_OVERRIDE,
            account_context=large_account,
        )
        
        assert decision.allowed is False
        assert decision.reason == BlockReason.MANUAL_OVERRIDE_DISABLED.value
    
    def test_manual_override_enabled_allows_exit(self, guard_with_override, base_trade, large_account):
        """Manual override allowed when enabled."""
        exit_date = base_trade.entry_date + timedelta(days=5)
        
        decision = guard_with_override.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.MANUAL_OVERRIDE,
            account_context=large_account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value


# =============================================================================
# TESTS: INTEGRATION SCENARIOS
# =============================================================================

class TestIntegrationScenarios:
    """Real-world trading scenarios combining multiple rules."""
    
    def test_small_account_day_trade_sequence(self, guard):
        """
        Small margin account attempting to day trade when at soft limit.
        
        Scenario:
        - Account: $10k margin (PDT rules apply)
        - Already has 2 day trades in rolling 5d window
        - Attempt 3rd day trade
        
        Expected: BLOCKED (soft limit prevents 3rd)
        """
        trade = create_trade("TSLA", date(2026, 1, 27), 200.0, 50, confidence=4)
        account = create_account_context(10000.0, "MARGIN", day_trade_count_5d=2)
        
        decision = guard.can_exit_trade(
            trade=trade,
            exit_date=trade.entry_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=account,
        )
        
        assert decision.allowed is False
        assert decision.reason == BlockReason.PDT_LIMIT_AT_RISK.value
    
    def test_small_account_forced_exit_at_max_hold(self, guard):
        """
        Small account must exit after 20 days regardless of PDT rules.
        
        Scenario:
        - Account: $10k margin
        - Position held 21 days
        - Exit reason: TIME_EXPIRY
        
        Expected: ALLOWED (force exit)
        """
        trade = create_trade("AAPL", date(2026, 1, 6), 150.0, 100, confidence=3)
        account = create_account_context(10000.0, "MARGIN", day_trade_count_5d=0)
        
        decision = guard.can_exit_trade(
            trade=trade,
            exit_date=date(2026, 1, 27),  # 21 days
            exit_reason=ExitReason.TIME_EXPIRY,
            account_context=account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.MAX_HOLD_EXCEEDED.value
    
    def test_large_account_swing_trading(self, guard):
        """
        Large account swings position for profit after 5 days.
        
        Scenario:
        - Account: $100k
        - Position held 5 days
        - Exit reason: STRATEGY_SIGNAL (profit target)
        
        Expected: ALLOWED (no restrictions)
        """
        trade = create_trade("SPY", date(2026, 1, 22), 500.0, 50, confidence=5)
        account = create_account_context(100000.0, "MARGIN", day_trade_count_5d=0)
        
        decision = guard.can_exit_trade(
            trade=trade,
            exit_date=date(2026, 1, 27),  # 5 days
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=account,
        )
        
        assert decision.allowed is True
        assert decision.reason == BlockReason.ALLOWED.value


# =============================================================================
# TESTS: EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Edge cases and boundary conditions."""
    
    def test_exactly_min_equity_threshold(self, guard, base_trade):
        """Account exactly at $25k threshold."""
        # At $25k, small account rules should NOT apply
        exit_date = base_trade.entry_date + timedelta(days=1)
        
        account = create_account_context(
            account_equity=25000.0,
            account_type="MARGIN",
            day_trade_count_5d=0,
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=account,
        )
        
        # Should be allowed (at threshold, not below)
        assert decision.allowed is True
    
    def test_one_cent_below_threshold(self, guard, base_trade):
        """Account $0.01 below threshold triggers small account rules."""
        exit_date = base_trade.entry_date + timedelta(days=1)
        
        account = create_account_context(
            account_equity=24999.99,
            account_type="MARGIN",
            day_trade_count_5d=0,
        )
        
        decision = guard.can_exit_trade(
            trade=base_trade,
            exit_date=exit_date,
            exit_reason=ExitReason.STRATEGY_SIGNAL,
            account_context=account,
        )
        
        # Should be blocked (below threshold, min hold applies)
        assert decision.allowed is False
        assert decision.reason == BlockReason.MIN_HOLD_NOT_MET.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
