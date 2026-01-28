"""
Unit tests for position scaling decision engine.

Tests cover:
- Hard safety enforcement (execution layer)
- Strategy qualification checks (price structure, timing, signals)
- Portfolio-level constraints
- Decision outcomes and logging
- Backward compatibility
"""

import unittest
from datetime import datetime, timedelta
from risk.scaling_policy import (
    ScalingContext,
    ScalingDecision,
    ScalingDecisionResult,
    ScalingReasonCode,
    ScalingType,
    StrategyScalingPolicy,
    count_entries,
    last_entry_price,
)
from strategies.scaling_engine import (
    should_scale_position,
    check_strategy_permits_scaling,
    check_max_entries_not_exceeded,
    check_max_position_size,
    check_pending_order_conflicts,
    check_broker_ledger_consistency,
    check_risk_budget,
    check_minimum_time_since_entry,
    check_minimum_bars_since_entry,
    check_signal_quality,
    check_price_structure,
    check_volatility_regime,
    check_execution_feasibility,
)


class TestScalingPolicyValidation(unittest.TestCase):
    """Test StrategyScalingPolicy validation."""

    def test_default_policy_no_scaling(self):
        """Default policy should have no scaling."""
        policy = StrategyScalingPolicy()
        self.assertFalse(policy.allows_multiple_entries)
        self.assertEqual(policy.max_entries_per_symbol, 1)

    def test_multi_entry_policy_validation(self):
        """Multi-entry policy should validate correctly."""
        policy = StrategyScalingPolicy(
            allows_multiple_entries=True,
            max_entries_per_symbol=3,
            max_total_position_pct=5.0,
        )
        is_valid, error = policy.validate()
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_invalid_max_entries(self):
        """Invalid max_entries should fail validation."""
        policy = StrategyScalingPolicy(
            allows_multiple_entries=True, max_entries_per_symbol=0
        )
        is_valid, error = policy.validate()
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_invalid_position_pct(self):
        """Negative position % should fail."""
        policy = StrategyScalingPolicy(
            allows_multiple_entries=True, max_total_position_pct=-1.0
        )
        is_valid, error = policy.validate()
        self.assertFalse(is_valid)


class TestHardSafetyEnforcement(unittest.TestCase):
    """Test execution-layer hard safety enforcement."""

    def setUp(self):
        """Set up default context."""
        self.context = ScalingContext(
            symbol="TEST",
            current_signal_confidence=5.0,
            proposed_entry_price=100.0,
            proposed_entry_size=10.0,
            current_position_qty=10.0,
            current_position_value=1000.0,
            current_price=100.0,
            account_equity=100000.0,
            available_risk_budget=5000.0,
            scaling_policy=StrategyScalingPolicy(
                allows_multiple_entries=True,
                max_entries_per_symbol=3,
                max_total_position_pct=5.0,
            ),
            ledger_entries=[{"price": 100.0, "qty": 10.0, "status": "open"}],
        )

    def test_strategy_disallows_scaling(self):
        """Should BLOCK if strategy doesn't allow scaling."""
        self.context.scaling_policy.allows_multiple_entries = False
        result = check_strategy_permits_scaling(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, ScalingDecision.BLOCK)

    def test_max_entries_exceeded(self):
        """Should BLOCK if max entries exceeded."""
        self.context.ledger_entries = [
            {"price": 100.0, "qty": 10.0, "status": "open"},
            {"price": 101.0, "qty": 10.0, "status": "open"},
            {"price": 102.0, "qty": 10.0, "status": "open"},
        ]
        result = check_max_entries_not_exceeded(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, ScalingDecision.BLOCK)
        self.assertEqual(result.reason_code, ScalingReasonCode.MAX_ENTRIES_EXCEEDED)

    def test_max_position_size_exceeded(self):
        """Should BLOCK if position would exceed max % of account."""
        self.context.proposed_entry_size = 1000.0  # Way too big
        result = check_max_position_size(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, ScalingDecision.BLOCK)

    def test_pending_buy_order_conflict(self):
        """Should BLOCK if pending BUY already exists."""
        self.context.pending_buy_orders = [
            {"symbol": "TEST", "order_type": "BUY", "qty": 5.0}
        ]
        result = check_pending_order_conflicts(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.reason_code, ScalingReasonCode.PENDING_BUY_EXISTS)

    def test_broker_ledger_mismatch(self):
        """Should BLOCK if broker qty != ledger qty."""
        self.context.current_position_qty = 15.0  # Ledger has 10
        result = check_broker_ledger_consistency(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(
            result.reason_code, ScalingReasonCode.BROKER_LEDGER_MISMATCH
        )

    def test_risk_budget_exceeded(self):
        """Should BLOCK if risk budget exceeded."""
        self.context.proposed_risk_amount = 10000.0  # Greater than available 5000
        result = check_risk_budget(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.reason_code, ScalingReasonCode.RISK_BUDGET_EXCEEDED)


class TestStrategyQualification(unittest.TestCase):
    """Test strategy-level qualification checks."""

    def setUp(self):
        """Set up context for qualification tests."""
        self.context = ScalingContext(
            symbol="TEST",
            current_signal_confidence=5.0,
            proposed_entry_price=101.0,  # Better price for pyramid
            proposed_entry_size=10.0,
            current_position_qty=10.0,
            current_position_value=1000.0,
            current_price=101.0,
            atr=2.0,
            atr_rolling_median=1.5,
            bars_since_last_entry=10,
            minutes_since_last_entry=60,
            price_highest_since_last_entry=101.0,
            price_lowest_since_last_entry=99.0,
            has_lower_low=False,
            has_bearish_divergence=False,
            signal_matches_position_direction=True,
            account_equity=100000.0,
            available_risk_budget=5000.0,
            scaling_policy=StrategyScalingPolicy(
                allows_multiple_entries=True,
                max_entries_per_symbol=3,
                scaling_type=ScalingType.PYRAMID,
                min_bars_between_entries=5,
                min_time_between_entries_seconds=300,
                min_signal_strength_for_add=3.0,
            ),
            ledger_entries=[{"price": 100.0, "qty": 10.0, "status": "open"}],
        )

    def test_minimum_time_not_met(self):
        """Should SKIP if minimum time not elapsed."""
        self.context.minutes_since_last_entry = 2  # Less than 5 minutes required
        self.context.scaling_policy.min_time_between_entries_seconds = 300
        result = check_minimum_time_since_entry(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, ScalingDecision.SKIP)

    def test_minimum_bars_not_met(self):
        """Should SKIP if minimum bars not elapsed."""
        self.context.bars_since_last_entry = 2
        self.context.scaling_policy.min_bars_between_entries = 5
        result = check_minimum_bars_since_entry(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, ScalingDecision.SKIP)

    def test_signal_quality_too_low(self):
        """Should SKIP if signal quality below threshold."""
        self.context.current_signal_confidence = 2.0
        self.context.scaling_policy.min_signal_strength_for_add = 3.0
        result = check_signal_quality(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.reason_code, ScalingReasonCode.SIGNAL_CONFIDENCE_TOO_LOW)

    def test_bearish_divergence_detected(self):
        """Should SKIP if bearish divergence found."""
        self.context.has_bearish_divergence = True
        result = check_signal_quality(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(
            result.reason_code, ScalingReasonCode.SIGNAL_QUALITY_INSUFFICIENT
        )

    def test_pyramid_price_structure_violation(self):
        """Pyramid should require entry price > last entry price."""
        self.context.proposed_entry_price = 99.0  # Less than last entry 100
        result = check_price_structure(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, ScalingDecision.SKIP)
        self.assertEqual(result.reason_code, ScalingReasonCode.PRICE_STRUCTURE_VIOLATION)

    def test_pyramid_no_lower_low_requirement(self):
        """Pyramid should SKIP if lower low detected."""
        self.context.has_lower_low = True
        self.context.scaling_policy.require_no_lower_low = True
        result = check_price_structure(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, ScalingDecision.SKIP)

    def test_average_price_structure(self):
        """Average should require entry price < last entry price."""
        self.context.scaling_policy.scaling_type = ScalingType.AVERAGE
        self.context.proposed_entry_price = 99.5  # Less than 100, good for average
        result = check_price_structure(self.context)
        self.assertIsNone(result)  # Should pass

    def test_average_drawdown_limit(self):
        """Average should SKIP if drawdown exceeds max ATR multiple."""
        self.context.scaling_policy.scaling_type = ScalingType.AVERAGE
        self.context.proposed_entry_price = 99.5
        self.context.price_lowest_since_last_entry = 95.0  # 5 dollar drawdown
        self.context.atr = 1.0
        self.context.scaling_policy.max_atr_drawdown_multiple = 2.0  # Max 2 ATR = 2.0
        result = check_price_structure(self.context)
        self.assertIsNotNone(result)  # Should fail due to excessive drawdown
        self.assertEqual(result.decision, ScalingDecision.SKIP)

    def test_volatility_regime_check(self):
        """Should SKIP if volatility below median."""
        self.context.atr = 1.0
        self.context.atr_rolling_median = 2.0
        self.context.scaling_policy.require_volatility_above_median = True
        result = check_volatility_regime(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, ScalingDecision.SKIP)


class TestExecutionFeasibility(unittest.TestCase):
    """Test execution sanity checks."""

    def setUp(self):
        self.context = ScalingContext(
            symbol="TEST",
            current_signal_confidence=5.0,
            proposed_entry_price=100.0,
            proposed_entry_size=10.0,
            current_position_qty=10.0,
            current_position_value=1000.0,
            current_price=100.0,
        )

    def test_order_size_too_small(self):
        """Should BLOCK if order size is too small."""
        self.context.proposed_entry_size = 0.001
        result = check_execution_feasibility(self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.reason_code, ScalingReasonCode.ORDER_SIZE_BELOW_MINIMUM)

    def test_order_value_too_small(self):
        """Should BLOCK if order value is below minimum."""
        self.context.proposed_entry_size = 0.05  # 0.05 * 100 = $5, below $10 min
        result = check_execution_feasibility(self.context, min_order_size=10.0)
        self.assertIsNotNone(result)


class TestMainDecisionEngine(unittest.TestCase):
    """Test main should_scale_position function."""

    def setUp(self):
        """Set up passing context."""
        self.context = ScalingContext(
            symbol="TEST",
            current_signal_confidence=6.0,
            proposed_entry_price=102.0,  # Better price
            proposed_entry_size=5.0,  # Smaller add
            current_position_qty=10.0,
            current_position_value=1000.0,
            current_price=102.0,
            atr=2.0,
            atr_rolling_median=1.5,
            bars_since_last_entry=10,
            minutes_since_last_entry=60,
            price_highest_since_last_entry=102.0,
            price_lowest_since_last_entry=99.0,
            has_lower_low=False,
            has_bearish_divergence=False,
            signal_matches_position_direction=True,
            account_equity=100000.0,
            available_risk_budget=5000.0,
            proposed_risk_amount=300.0,
            strategy_name="test_strategy",
            scaling_policy=StrategyScalingPolicy(
                allows_multiple_entries=True,
                max_entries_per_symbol=3,
                max_total_position_pct=5.0,
                scaling_type=ScalingType.PYRAMID,
                min_bars_between_entries=5,
                min_time_between_entries_seconds=300,
                min_signal_strength_for_add=3.0,
            ),
            ledger_entries=[{"price": 100.0, "qty": 10.0, "status": "open"}],
        )

    def test_scale_approved_all_checks_pass(self):
        """Should SCALE when all checks pass."""
        result = should_scale_position(self.context)
        self.assertEqual(result.decision, ScalingDecision.SCALE)

    def test_blocks_on_first_failure(self):
        """Should block on strategy disallowing scaling."""
        self.context.scaling_policy.allows_multiple_entries = False
        result = should_scale_position(self.context)
        self.assertEqual(result.decision, ScalingDecision.BLOCK)
        self.assertEqual(
            result.reason_code, ScalingReasonCode.STRATEGY_DISALLOWS_SCALING
        )

    def test_skips_on_timing_violation(self):
        """Should SKIP (not BLOCK) on timing violations."""
        self.context.bars_since_last_entry = 2
        self.context.scaling_policy.min_bars_between_entries = 5
        result = should_scale_position(self.context)
        self.assertEqual(result.decision, ScalingDecision.SKIP)
        self.assertEqual(result.reason_code, ScalingReasonCode.MINIMUM_BARS_NOT_MET)

    def test_no_scaling_policy(self):
        """Should BLOCK if no scaling policy."""
        self.context.scaling_policy = None
        result = should_scale_position(self.context)
        self.assertEqual(result.decision, ScalingDecision.BLOCK)

    def test_decision_result_logging(self):
        """Decision result should log structured event."""
        result = ScalingDecisionResult(
            decision=ScalingDecision.BLOCK,
            reason_code=ScalingReasonCode.STRATEGY_DISALLOWS_SCALING,
            reason_text="Test reason",
            current_entry_count=1,
        )
        # Should not raise
        result.log(self.context)

    def test_backward_compatibility_single_entry(self):
        """Single-entry strategies should work unchanged."""
        self.context.scaling_policy = StrategyScalingPolicy(
            allows_multiple_entries=False  # Default
        )
        result = should_scale_position(self.context)
        self.assertEqual(result.decision, ScalingDecision.BLOCK)
        # Existing position should block new entries
        self.assertEqual(
            result.reason_code, ScalingReasonCode.STRATEGY_DISALLOWS_SCALING
        )


class TestHelperFunctions(unittest.TestCase):
    """Test helper utility functions."""

    def test_count_entries(self):
        """Should count open entries only."""
        entries = [
            {"price": 100.0, "qty": 10.0, "status": "open"},
            {"price": 101.0, "qty": 10.0, "status": "open"},
            {"price": 102.0, "qty": 10.0, "status": "closed"},
        ]
        count = count_entries(entries)
        self.assertEqual(count, 2)

    def test_last_entry_price(self):
        """Should return last open entry price."""
        entries = [
            {"price": 100.0, "qty": 10.0, "status": "open"},
            {"price": 101.0, "qty": 10.0, "status": "open"},
        ]
        price = last_entry_price(entries)
        self.assertEqual(price, 101.0)

    def test_last_entry_price_no_entries(self):
        """Should return None if no open entries."""
        price = last_entry_price([])
        self.assertIsNone(price)


if __name__ == "__main__":
    unittest.main()
