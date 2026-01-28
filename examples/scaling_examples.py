"""
Position Scaling Examples - Real-world usage patterns

Demonstrates how to:
1. Define scaling-enabled strategies
2. Evaluate scaling decisions
3. Handle BLOCK/SKIP/SCALE outcomes
4. Log and audit trail decisions
"""

from datetime import datetime, timedelta
from risk.scaling_policy import (
    ScalingContext,
    ScalingDecision,
    ScalingType,
    StrategyScalingPolicy,
)
from strategies.scaling_engine import should_scale_position


# ============================================================================
# Example 1: Pyramid Scaling Strategy
# ============================================================================


def example_pyramid_scaling():
    """
    Pyramid strategy: Add at better prices, stronger signal.
    
    Rules:
    - Max 3 entries per symbol
    - Entry price must be higher than last entry
    - No lower low since last entry
    - Wait 5+ bars between entries
    - Signal must be strong (>=4.0 confidence)
    """

    # Strategy declares scaling policy
    pyramid_policy = StrategyScalingPolicy(
        allows_multiple_entries=True,
        max_entries_per_symbol=3,
        max_total_position_pct=5.0,
        scaling_type=ScalingType.PYRAMID,
        min_bars_between_entries=5,
        min_time_between_entries_seconds=300,
        min_signal_strength_for_add=4.0,
        require_no_lower_low=True,
        require_volatility_above_median=True,
        max_atr_drawdown_multiple=2.0,
    )

    # Example 1a: First entry - no scaling check
    print("\n" + "=" * 80)
    print("PYRAMID EXAMPLE 1a: First Entry (no scaling check)")
    print("=" * 80)

    first_entry_signal = {
        "symbol": "AAPL",
        "confidence": 6.0,
        "price": 150.00,
    }
    print(f"Signal: {first_entry_signal}")
    print("Result: EXECUTE (first entry, no scaling evaluation needed)")

    # Example 1b: Good second entry
    print("\n" + "=" * 80)
    print("PYRAMID EXAMPLE 1b: Good Second Entry")
    print("=" * 80)

    context_good_add = ScalingContext(
        symbol="AAPL",
        current_signal_confidence=5.0,
        proposed_entry_price=155.00,  # ✓ Better price
        proposed_entry_size=5.0,
        current_position_qty=10.0,
        current_position_value=1500.0,
        current_price=155.00,
        atr=2.0,
        atr_rolling_median=1.5,
        bars_since_last_entry=10,  # ✓ 10 > 5 required
        minutes_since_last_entry=60,
        price_highest_since_last_entry=155.00,
        price_lowest_since_last_entry=153.00,  # ✓ No lower low below 150
        has_lower_low=False,
        has_bearish_divergence=False,
        signal_matches_position_direction=True,
        account_equity=100000.0,
        available_risk_budget=5000.0,
        proposed_risk_amount=250.0,
        strategy_name="pyramid_equity",
        scaling_policy=pyramid_policy,
        ledger_entries=[{"price": 150.00, "qty": 10.0, "status": "open", "timestamp": datetime.utcnow()}],
    )

    result = should_scale_position(context_good_add)
    result.log(context_good_add)
    print(f"Decision: {result.decision.value}")
    print(f"Reason: {result.reason_text}")

    # Example 1c: Price structure violation
    print("\n" + "=" * 80)
    print("PYRAMID EXAMPLE 1c: Price Structure Violation (worse price)")
    print("=" * 80)

    context_bad_price = ScalingContext(
        symbol="AAPL",
        current_signal_confidence=5.0,
        proposed_entry_price=148.00,  # ✗ WORSE price (pyramid needs better)
        proposed_entry_size=5.0,
        current_position_qty=10.0,
        current_position_value=1500.0,
        current_price=148.00,
        atr=2.0,
        atr_rolling_median=1.5,
        bars_since_last_entry=10,
        minutes_since_last_entry=60,
        price_highest_since_last_entry=155.00,
        price_lowest_since_last_entry=148.00,
        has_lower_low=False,
        has_bearish_divergence=False,
        signal_matches_position_direction=True,
        account_equity=100000.0,
        available_risk_budget=5000.0,
        proposed_risk_amount=250.0,
        strategy_name="pyramid_equity",
        scaling_policy=pyramid_policy,
        ledger_entries=[{"price": 150.00, "qty": 10.0, "status": "open"}],
    )

    result = should_scale_position(context_bad_price)
    result.log(context_bad_price)
    print(f"Decision: {result.decision.value}")
    print(f"Reason: {result.reason_text}")
    assert result.decision == ScalingDecision.SKIP

    # Example 1d: Lower low detected
    print("\n" + "=" * 80)
    print("PYRAMID EXAMPLE 1d: Lower Low Detected")
    print("=" * 80)

    context_lower_low = ScalingContext(
        symbol="AAPL",
        current_signal_confidence=5.0,
        proposed_entry_price=152.00,
        proposed_entry_size=5.0,
        current_position_qty=10.0,
        current_position_value=1500.0,
        current_price=152.00,
        atr=2.0,
        atr_rolling_median=1.5,
        bars_since_last_entry=10,
        minutes_since_last_entry=60,
        price_highest_since_last_entry=155.00,
        price_lowest_since_last_entry=149.00,  # ✗ Lower than 150 entry
        has_lower_low=True,
        has_bearish_divergence=False,
        signal_matches_position_direction=True,
        account_equity=100000.0,
        available_risk_budget=5000.0,
        proposed_risk_amount=250.0,
        strategy_name="pyramid_equity",
        scaling_policy=pyramid_policy,
        ledger_entries=[{"price": 150.00, "qty": 10.0, "status": "open"}],
    )

    result = should_scale_position(context_lower_low)
    result.log(context_lower_low)
    print(f"Decision: {result.decision.value}")
    assert result.decision == ScalingDecision.SKIP


# ============================================================================
# Example 2: Average-Down Scaling
# ============================================================================


def example_average_down_scaling():
    """
    Average-down strategy: Add at worse prices, large positions.
    
    Rules:
    - Max 4 entries per symbol
    - Entry price must be lower than last entry (averaging down)
    - Max drawdown 2 ATRs
    - Wait 10+ bars between entries
    - Works even in low-volatility environments
    """

    average_policy = StrategyScalingPolicy(
        allows_multiple_entries=True,
        max_entries_per_symbol=4,
        max_total_position_pct=8.0,  # Larger position allowed
        scaling_type=ScalingType.AVERAGE,
        min_bars_between_entries=10,
        min_time_between_entries_seconds=600,
        min_signal_strength_for_add=2.0,  # Lenient for averaging
        require_no_lower_low=False,  # Don't care about lows for averaging
        require_volatility_above_median=False,  # Works in calm markets
        max_atr_drawdown_multiple=2.0,
    )

    print("\n" + "=" * 80)
    print("AVERAGE-DOWN EXAMPLE: Adding to Losing Position")
    print("=" * 80)

    # Bought at 100, price dropped to 95, adding more at 95
    context_average = ScalingContext(
        symbol="SPY",
        current_signal_confidence=3.0,
        proposed_entry_price=95.00,  # ✓ Lower than entry
        proposed_entry_size=15.0,
        current_position_qty=10.0,
        current_position_value=950.0,  # 10 * 95
        current_price=95.00,
        atr=1.0,
        atr_rolling_median=0.8,
        bars_since_last_entry=12,  # ✓ 12 > 10 required
        minutes_since_last_entry=120,
        price_highest_since_last_entry=100.00,  # First entry
        price_lowest_since_last_entry=94.00,  # Drawdown from 100 to 94 = 6, = 6 ATR
        has_lower_low=False,
        has_bearish_divergence=False,
        signal_matches_position_direction=True,
        account_equity=100000.0,
        available_risk_budget=8000.0,
        proposed_risk_amount=450.0,
        strategy_name="average_down_equity",
        scaling_policy=average_policy,
        ledger_entries=[{"price": 100.00, "qty": 10.0, "status": "open"}],
    )

    result = should_scale_position(context_average)
    result.log(context_average)
    print(f"Decision: {result.decision.value}")
    if result.decision == ScalingDecision.BLOCK:
        print(f"BLOCKED: {result.reason_text}")
    else:
        print(f"Result: {result.reason_text}")


# ============================================================================
# Example 3: Safety Blocks
# ============================================================================


def example_safety_blocks():
    """
    Demonstrate hard safety blocks.
    
    These are non-negotiable and always result in BLOCK.
    """

    policy = StrategyScalingPolicy(
        allows_multiple_entries=True,
        max_entries_per_symbol=3,
        max_total_position_pct=5.0,
    )

    # Example 3a: Max entries exceeded
    print("\n" + "=" * 80)
    print("SAFETY BLOCK 3a: Max Entries Exceeded")
    print("=" * 80)

    context = ScalingContext(
        symbol="TSLA",
        current_signal_confidence=7.0,
        proposed_entry_price=220.00,
        proposed_entry_size=10.0,
        current_position_qty=30.0,
        current_position_value=6600.0,
        current_price=220.00,
        account_equity=100000.0,
        available_risk_budget=5000.0,
        proposed_risk_amount=400.0,
        strategy_name="scalable_strategy",
        scaling_policy=policy,
        ledger_entries=[
            {"price": 200.00, "qty": 10.0, "status": "open"},
            {"price": 210.00, "qty": 10.0, "status": "open"},
            {"price": 220.00, "qty": 10.0, "status": "open"},
        ],
    )

    result = should_scale_position(context)
    result.log(context)
    print(f"Decision: {result.decision.value}")
    print(f"Reason: {result.reason_code.value}")
    assert result.decision == ScalingDecision.BLOCK

    # Example 3b: Pending order conflict
    print("\n" + "=" * 80)
    print("SAFETY BLOCK 3b: Pending Buy Order Exists")
    print("=" * 80)

    context = ScalingContext(
        symbol="MSFT",
        current_signal_confidence=6.0,
        proposed_entry_price=300.00,
        proposed_entry_size=5.0,
        current_position_qty=10.0,
        current_position_value=3000.0,
        current_price=300.00,
        account_equity=100000.0,
        available_risk_budget=5000.0,
        proposed_risk_amount=300.0,
        strategy_name="scalable_strategy",
        scaling_policy=policy,
        ledger_entries=[{"price": 300.00, "qty": 10.0, "status": "open"}],
        pending_buy_orders=[
            {"symbol": "MSFT", "order_type": "BUY", "qty": 5.0}
        ],
    )

    result = should_scale_position(context)
    result.log(context)
    print(f"Decision: {result.decision.value}")
    assert result.decision == ScalingDecision.BLOCK

    # Example 3c: Broker/Ledger mismatch
    print("\n" + "=" * 80)
    print("SAFETY BLOCK 3c: Broker/Ledger Quantity Mismatch")
    print("=" * 80)

    context = ScalingContext(
        symbol="GOOGL",
        current_signal_confidence=6.0,
        proposed_entry_price=140.00,
        proposed_entry_size=5.0,
        current_position_qty=15.0,  # ✗ Broker has 15
        current_position_value=2100.0,
        current_price=140.00,
        account_equity=100000.0,
        available_risk_budget=5000.0,
        proposed_risk_amount=300.0,
        strategy_name="scalable_strategy",
        scaling_policy=policy,
        ledger_entries=[{"price": 140.00, "qty": 10.0, "status": "open"}],  # ✗ Ledger has 10
    )

    result = should_scale_position(context)
    result.log(context)
    print(f"Decision: {result.decision.value}")
    assert result.decision == ScalingDecision.BLOCK
    print(f"Debug: {result.debug_info}")


# ============================================================================
# Example 4: Backward Compatibility
# ============================================================================


def example_backward_compatibility():
    """
    Existing single-entry strategies continue to work unchanged.
    """

    # Old-style single-entry strategy (no scaling_policy)
    single_entry_policy = StrategyScalingPolicy()  # Defaults to single-entry

    print("\n" + "=" * 80)
    print("BACKWARD COMPATIBILITY: Single-Entry Strategy")
    print("=" * 80)

    context = ScalingContext(
        symbol="XYZ",
        current_signal_confidence=5.0,
        proposed_entry_price=50.00,
        proposed_entry_size=20.0,
        current_position_qty=20.0,
        current_position_value=1000.0,
        current_price=50.00,
        account_equity=100000.0,
        available_risk_budget=5000.0,
        proposed_risk_amount=200.0,
        strategy_name="legacy_swing",
        scaling_policy=single_entry_policy,
        ledger_entries=[{"price": 50.00, "qty": 20.0, "status": "open"}],
    )

    result = should_scale_position(context)
    result.log(context)
    print(f"Decision: {result.decision.value}")
    assert result.decision == ScalingDecision.BLOCK
    print("✓ Single-entry strategies work unchanged")


# ============================================================================
# Run Examples
# ============================================================================


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "Position Scaling Decision Engine - Examples".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")

    example_pyramid_scaling()
    example_average_down_scaling()
    example_safety_blocks()
    example_backward_compatibility()

    print("\n" + "=" * 80)
    print("All examples completed successfully!")
    print("=" * 80)
